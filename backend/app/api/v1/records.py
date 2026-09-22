"""Endpoint di lettura/ricerca per i Record e i loro dati collegati
(annunci, media, storico, riepilogo AI).

Il modulo espone due famiglie di endpoint:

1. Endpoint "legacy", allineati 1:1 al modello ORM (`GET /records/{id}` nella
   sua forma originaria, `POST /records/search`): risposte snake_case.
2. Endpoint "view", pensati per la UI (`frontend/src/routes/records/*`) e
   consumati da `frontend/src/api/records.ts` SENZA alcun mapping
   snake->camel lato client: rispondono quindi in camelCase (vedi
   `app/schemas/common.py:CamelModel`). `GET /records/{record_id}` è stato
   convertito in questa seconda famiglia (vedi `get_record_overview`),
   perché è quello che la UI usa davvero per la tab "Overview": il vecchio
   `RecordDetail` (annuncio-per-annuncio, snake_case) non copriva i campi
   che la UI mostra (titolo/descrizione canonici, confidence, tag...).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.db import get_db
from app.models.advertisement import Advertisement
from app.models.advertisement_versions import AdvertisementVersion
from app.models.ai_settings import AIProviderConfig, AISettings
from app.models.audit_log import AuditLog
from app.models.canonical_history import CanonicalHistory
from app.models.media import Media
from app.models.media_classification_history import MediaClassificationHistory
from app.models.record import Record
from app.models.sources import Source
from app.models.summary_generation_jobs import SummaryGenerationJob
from app.models.summary_versions import SummaryVersion
from app.models.users import User
from app.schemas.records import (
    AdvertisementVersionRead,
    CustomFieldGroupRead,
    CustomFieldValueRead,
    RecordAiSummaryRead,
    RecordAiSummaryVersionRead,
    RecordDetail,
    RecordHistoryEventRead,
    RecordMediaRead,
    RecordOccurrenceDetailRead,
    RecordOccurrenceRead,
    RecordOverviewRead,
    RecordSearchRequest,
    RecordSearchResponseRead,
    RecordSearchResultRead,
    SourceUsedRead,
    SummaryGenerationJobRead,
)
from app.security.deps import get_current_user, require_role
from app.services.audit import log_action
from app.services.media_storage import presigned_media_url
from app.services.phone_crypto import decrypt_phone, mask_phone, phone_lookup_hash
from app.services.record_search import (
    VERIFIED_CONFIDENCE_THRESHOLD,
    confidence_to_status,
    looks_like_full_phone,
)

router = APIRouter()


def _tags_from_custom_fields(custom_fields: dict) -> list[str]:
    raw_tags = custom_fields.get("tags")
    tag_values = raw_tags if isinstance(raw_tags, list) else [raw_tags]
    return list(
        dict.fromkeys(
            value.strip() for value in tag_values if isinstance(value, str) and value.strip()
        )
    )


def _has_custom_field_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_custom_field_value(item) for item in value)
    if isinstance(value, dict):
        return any(_has_custom_field_value(item) for item in value.values())
    return False


def _aggregate_custom_fields(
    rows: list[tuple[Advertisement, uuid.UUID, str, str]],
    canonical_ad_id: uuid.UUID | None,
) -> list[CustomFieldGroupRead]:
    """Raggruppa i campi di tutte le occorrenze senza perdere la provenienza.

    Un duplicato e definito dalla stessa chiave, dallo stesso valore JSON e
    dalla stessa fonte. L'annuncio canonico viene considerato per primo cosi,
    in caso di duplicato, e quello a fornire il riferimento conservato.
    """
    groups: dict[str, list[CustomFieldValueRead]] = {}
    seen: dict[str, set[tuple[uuid.UUID, str]]] = {}
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            row[0].id != canonical_ad_id,
            row[2].casefold(),
            str(row[0].id),
        ),
    )
    for advertisement, source_id, source_name, source_code in ordered_rows:
        for name, value in (advertisement.custom_fields or {}).items():
            if not _has_custom_field_value(value):
                continue
            serialized = json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            duplicate_key = (source_id, serialized)
            field_seen = seen.setdefault(name, set())
            if duplicate_key in field_seen:
                continue
            field_seen.add(duplicate_key)
            groups.setdefault(name, []).append(
                CustomFieldValueRead(
                    value=value,
                    source_id=source_id,
                    source_name=source_name,
                    source_code=source_code,
                    advertisement_id=advertisement.id,
                    is_canonical=advertisement.id == canonical_ad_id,
                )
            )
    return [
        CustomFieldGroupRead(name=name, values=values)
        for name, values in sorted(groups.items(), key=lambda item: item[0])
    ]


def _tags_from_groups(groups: list[CustomFieldGroupRead]) -> list[str]:
    tags: list[str] = []
    for group in groups:
        if group.name != "tags":
            continue
        for entry in group.values:
            raw_values = entry.value if isinstance(entry.value, list) else [entry.value]
            tags.extend(
                value.strip() for value in raw_values if isinstance(value, str) and value.strip()
            )
    return list(dict.fromkeys(tags))


def _safe_decrypt_phone(encrypted: bytes) -> str:
    """Decifra il telefono per la visualizzazione, senza far fallire
    l'intera risposta se un singolo record ha un blob corrotto/illeggibile
    (difesa in profondità: preferiamo mostrare un placeholder a un 500)."""
    try:
        return decrypt_phone(encrypted)
    except Exception:  # noqa: BLE001 - difesa deliberatamente ampia, vedi docstring
        return "N/D"


def _phone_for_user(encrypted: bytes, user: User) -> tuple[str, str]:
    phone = _safe_decrypt_phone(encrypted)
    if user.role == "admin" or user.can_view_clear_phone:
        return phone, "clear"
    return mask_phone(phone), "masked"


async def _get_record_or_404(db: AsyncSession, record_id: uuid.UUID) -> Record:
    record = await db.get(Record, record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record non trovato.")
    return record


# ---------------------------------------------------------------------------
# GET /records/search — ricerca paginata (usata da frontend/src/api/records.ts)
# ---------------------------------------------------------------------------
# NOTA D'ORDINE ROUTE: questa route deve essere registrata PRIMA di
# `GET /{record_id}` qui sotto. FastAPI risolve le route nell'ordine di
# dichiarazione: se "/{record_id}" precedesse "/search", una richiesta a
# "/records/search" verrebbe intercettata da "/{record_id}" con
# record_id="search", fallendo la validazione UUID con un 422 invece di
# raggiungere questo handler.
@router.get("/search", response_model=RecordSearchResponseRead)
async def search_records(
    response: Response,
    phone: str | None = Query(None, description="Numero di telefono (intero) da cercare."),
    source: str | None = Query(None, description="Slug o nome della fonte."),
    status_filter: str | None = Query(
        None, alias="status", description="verified | unverified | flagged"
    ),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecordSearchResponseRead:
    """Ricerca paginata di record, con filtri combinabili.

    Sostituisce/estende il vecchio `POST /records/search` (lookup esatto per
    telefono, mantenuto sotto per compatibilità) con l'endpoint realmente
    atteso dalla UI: `frontend/src/api/records.ts:searchRecords` chiama
    `GET /records/search?phone=...&source=...&status=...&date_from=...
    &date_to=...&page=...&page_size=...` aspettandosi una lista paginata.
    """
    # Subquery di aggregazione per annuncio: occorrenze, fonti distinte,
    # prima/ultima apparizione. Un Record può avere zero annunci solo in una
    # finestra temporale transitoria (appena creato, prima dell'associazione
    # del primo annuncio): usiamo un JOIN (non LEFT JOIN) deliberatamente,
    # perché un record "vuoto" non ha comunque nulla di sensato da mostrare
    # nei risultati di ricerca (titolo canonico, date...).
    ad_agg = (
        select(
            Advertisement.record_id.label("record_id"),
            func.count(Advertisement.id).label("occurrences_count"),
            func.count(func.distinct(Advertisement.source_id)).label("sources_count"),
            func.min(Advertisement.first_seen_at).label("first_seen_at"),
            func.max(Advertisement.last_seen_at).label("last_seen_at"),
        )
        .group_by(Advertisement.record_id)
        .subquery()
    )

    canonical_ad = aliased(Advertisement)

    base_stmt = (
        select(
            Record.id,
            Record.phone_encrypted,
            canonical_ad.title,
            canonical_ad.confidence,
            ad_agg.c.occurrences_count,
            ad_agg.c.sources_count,
            ad_agg.c.first_seen_at,
            ad_agg.c.last_seen_at,
        )
        .join(ad_agg, ad_agg.c.record_id == Record.id)
        .outerjoin(canonical_ad, canonical_ad.id == Record.canonical_ad_id)
    )

    conditions = []

    if phone:
        # Vedi app/services/record_search.py:looks_like_full_phone per la
        # motivazione: un filtro "phone" che non sembra un numero completo
        # viene silenziosamente ignorato (non esiste modo di fare una
        # ricerca a prefisso sull'hash di lookup), la ricerca prosegue sugli
        # altri criteri invece di restituire un errore o un risultato vuoto.
        if looks_like_full_phone(phone):
            conditions.append(Record.phone_lookup_hash == phone_lookup_hash(phone))

    if source:
        source_exists = (
            select(Advertisement.id)
            .join(Source, Source.id == Advertisement.source_id)
            .where(
                Advertisement.record_id == Record.id,
                or_(Source.slug == source, Source.name == source),
            )
        )
        conditions.append(source_exists.exists())

    if date_from:
        conditions.append(ad_agg.c.last_seen_at >= date_from)
    if date_to:
        conditions.append(ad_agg.c.first_seen_at <= date_to)

    if status_filter == "verified":
        conditions.append(canonical_ad.confidence >= VERIFIED_CONFIDENCE_THRESHOLD)
    elif status_filter == "unverified":
        conditions.append(
            or_(
                canonical_ad.confidence < VERIFIED_CONFIDENCE_THRESHOLD,
                canonical_ad.confidence.is_(None),
            )
        )
    elif status_filter == "flagged":
        # Nessun meccanismo di segnalazione manuale è implementato oggi (vedi
        # app/services/record_search.py): nessun record può avere questo
        # status, quindi la query restituisce correttamente zero risultati
        # invece di ignorare il filtro.
        conditions.append(false())

    if conditions:
        base_stmt = base_stmt.where(and_(*conditions))

    total = (await db.execute(select(func.count()).select_from(base_stmt.subquery()))).scalar_one()

    page_stmt = (
        base_stmt.order_by(ad_agg.c.last_seen_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    rows = (await db.execute(page_stmt)).all()

    visibility = "clear" if user.role == "admin" or user.can_view_clear_phone else "masked"
    results = [
        RecordSearchResultRead(
            id=row.id,
            phone=_phone_for_user(row.phone_encrypted, user)[0],
            phone_visibility=visibility,
            canonical_title=row.title or "(Senza titolo)",
            sources_count=row.sources_count or 0,
            occurrences_count=row.occurrences_count or 0,
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at,
            status=confidence_to_status(row.confidence),
        )
        for row in rows
    ]

    response.headers["Cache-Control"] = "no-store"
    if visibility == "clear" and results:
        await log_action(
            db,
            user_id=user.id,
            action="view_clear_phone",
            entity_type="record_search",
            details={"record_ids": [str(item.id) for item in results], "count": len(results)},
        )
        await db.commit()

    return RecordSearchResponseRead(results=results, total=total, page=page, page_size=page_size)


@router.post("/search", response_model=RecordDetail | None)
async def search_record_by_phone(
    payload: RecordSearchRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RecordDetail | None:
    """Lookup legacy: un Record esatto dato un numero di telefono completo.

    Non risulta usato da `frontend/src/api/*.ts` (che usa esclusivamente
    `GET /records/search`, sopra): lo lasciamo per compatibilità con
    eventuali altri consumatori dell'API (es. script interni, `/docs`) dato
    che resta un'operazione legittima e già correttamente implementata
    (hash di lookup, mai il numero in chiaro).
    """
    lookup_hash = phone_lookup_hash(payload.phone)

    result = await db.execute(
        select(Record)
        .options(selectinload(Record.advertisements))
        .where(Record.phone_lookup_hash == lookup_hash)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None
    return RecordDetail.model_validate(record)


@router.get("/{record_id}", response_model=RecordOverviewRead)
async def get_record_overview(
    record_id: uuid.UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecordOverviewRead:
    """Dettaglio di un Record per la tab "Overview" (vedi
    `frontend/src/routes/records/RecordOverviewTab.tsx`)."""
    record = await _get_record_or_404(db, record_id)

    agg_row = (
        await db.execute(
            select(
                func.count(Advertisement.id),
                func.count(func.distinct(Advertisement.source_id)),
                func.min(Advertisement.first_seen_at),
                func.max(Advertisement.last_seen_at),
            ).where(Advertisement.record_id == record_id)
        )
    ).one()
    occurrences_count, sources_count, first_seen_at, last_seen_at = agg_row

    canonical_ad = (
        await db.get(Advertisement, record.canonical_ad_id) if record.canonical_ad_id else None
    )
    confidence = canonical_ad.confidence if canonical_ad else None

    phone, visibility = _phone_for_user(record.phone_encrypted, user)
    response.headers["Cache-Control"] = "no-store"
    if visibility == "clear":
        await log_action(
            db,
            user_id=user.id,
            action="view_clear_phone",
            entity_type="record",
            entity_id=str(record.id),
            details={"count": 1},
        )
        await db.commit()
    custom_rows = (
        await db.execute(
            select(Advertisement, Source.id, Source.name, Source.slug)
            .join(Source, Source.id == Advertisement.source_id)
            .where(Advertisement.record_id == record_id)
        )
    ).all()
    custom_field_groups = _aggregate_custom_fields(custom_rows, record.canonical_ad_id)
    custom_fields = canonical_ad.custom_fields or {} if canonical_ad else {}
    tags = _tags_from_groups(custom_field_groups)
    return RecordOverviewRead(
        id=record.id,
        phone=phone,
        phone_visibility=visibility,
        canonical_title=(canonical_ad.title if canonical_ad else None) or "(Senza titolo)",
        canonical_description=(canonical_ad.description if canonical_ad else None) or "",
        confidence_score=round((confidence or 0.0) * 100, 1),
        sources_count=sources_count or 0,
        occurrences_count=occurrences_count or 0,
        # Fallback su created_at del Record se non ha ancora annunci (caso
        # limite: record appena creato, non dovrebbe normalmente accadere
        # dato che un record nasce sempre da almeno un annuncio scrapato).
        first_seen_at=first_seen_at or record.created_at,
        last_seen_at=last_seen_at or record.updated_at,
        status=confidence_to_status(confidence),
        tags=tags,
        custom_fields=custom_fields,
        custom_field_groups=custom_field_groups,
        content_revision=record.content_revision,
    )


@router.get("/{record_id}/occurrences", response_model=list[RecordOccurrenceRead])
async def get_record_occurrences(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RecordOccurrenceRead]:
    """Tutti gli annunci (`Advertisement`) collegati al record, con il flag
    `isCanonical` per l'annuncio attualmente selezionato come canonico."""
    record = await _get_record_or_404(db, record_id)

    stmt = (
        select(Advertisement, Source.name, Source.slug)
        .join(Source, Source.id == Advertisement.source_id)
        .where(Advertisement.record_id == record_id)
        .order_by(Advertisement.scraped_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    return [
        RecordOccurrenceRead(
            id=ad.id,
            source_name=source_name,
            source_code=source_slug,
            title=ad.title or "(Senza titolo)",
            url=ad.source_url,
            scraped_at=ad.scraped_at,
            is_canonical=(ad.id == record.canonical_ad_id),
            match_confidence=round(ad.confidence * 100, 1),
            custom_fields=ad.custom_fields or {},
            revision=ad.revision,
            last_changed_at=ad.last_changed_at,
            has_updates=ad.revision > 1,
            listing_page_number=ad.listing_page_number,
        )
        for ad, source_name, source_slug in rows
    ]


@router.get(
    "/{record_id}/occurrences/{advertisement_id}/versions",
    response_model=list[AdvertisementVersionRead],
)
async def get_occurrence_versions(
    record_id: uuid.UUID,
    advertisement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[AdvertisementVersionRead]:
    """Restituisce la cronologia immutabile di un'occorrenza del record."""
    await _get_record_or_404(db, record_id)
    advertisement = await db.get(Advertisement, advertisement_id)
    if advertisement is None or advertisement.record_id != record_id:
        raise HTTPException(status_code=404, detail="Occorrenza non trovata.")
    versions = (
        (
            await db.execute(
                select(AdvertisementVersion)
                .where(AdvertisementVersion.advertisement_id == advertisement_id)
                .order_by(AdvertisementVersion.revision.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        AdvertisementVersionRead(
            id=version.id,
            advertisement_id=version.advertisement_id,
            revision=version.revision,
            scrape_run_id=version.scrape_run_id,
            changed_fields=version.changed_fields or [],
            snapshot=version.snapshot_json or {},
            created_at=version.created_at,
        )
        for version in versions
    ]


def _media_object_url(media: Media, *, variant: str) -> str:
    """Short-lived MinIO URL; the original remains immutable."""
    if variant == "thumbnail":
        key = media.thumbnail_object_key or media.display_object_key or media.original_object_key
    elif variant == "display":
        key = media.display_object_key or media.derived_object_key or media.original_object_key
    else:
        key = media.original_object_key
    return presigned_media_url(key)


@router.get("/{record_id}/media", response_model=list[RecordMediaRead])
async def get_record_media(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RecordMediaRead]:
    """Tutti i media associati agli annunci del record."""
    await _get_record_or_404(db, record_id)

    stmt = (
        select(Media, Source.name)
        .join(Advertisement, Advertisement.id == Media.advertisement_id)
        .join(Source, Source.id == Advertisement.source_id)
        .where(Advertisement.record_id == record_id)
        .where(Media.is_current.is_(True))
        .order_by(Media.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    results: list[RecordMediaRead] = []
    for media, source_name in rows:
        # Scelta "fail-safe" deliberata: solo la classificazione "safe"
        # esplicita produce sensitivity="safe". Un media "unclassified" (non
        # ancora passato dal classificatore) viene trattato come "explicit"
        # anziché "safe": in un contesto sensibile come questo, è preferibile
        # sovra-proteggere un contenuto non ancora verificato piuttosto che
        # rischiare di mostrarlo come sicuro per default.
        sensitivity = "safe" if media.classification == "safe" else "explicit"
        media_type = "video" if media.mime_type.startswith("video/") else "image"
        results.append(
            RecordMediaRead(
                id=media.id,
                url=_media_object_url(media, variant="display"),
                thumbnail_url=_media_object_url(media, variant="thumbnail"),
                type=media_type,
                sensitivity=sensitivity,
                source_name=source_name,
                added_at=media.created_at,
                classification=media.classification,
                classification_confidence=media.classification_confidence,
                safety_signals=media.safety_signals or {},
                review_status=media.review_status,
                processing_status=media.processing_status,
                display_url=_media_object_url(media, variant="display"),
                original_url=_media_object_url(media, variant="original"),
            )
        )
    return results


@router.get(
    "/{record_id}/occurrences/{advertisement_id}",
    response_model=RecordOccurrenceDetailRead,
)
async def get_occurrence_detail(
    record_id: uuid.UUID,
    advertisement_id: uuid.UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecordOccurrenceDetailRead:
    """Riepilogo completo e lazy di una singola occorrenza."""
    record = await _get_record_or_404(db, record_id)
    row = (
        await db.execute(
            select(Advertisement, Source)
            .join(Source, Source.id == Advertisement.source_id)
            .where(
                Advertisement.id == advertisement_id,
                Advertisement.record_id == record_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Occorrenza non trovata.")
    advertisement, source = row
    phone, visibility = _phone_for_user(record.phone_encrypted, user)
    response.headers["Cache-Control"] = "no-store"
    media_rows = (
        (
            await db.execute(
                select(Media)
                .where(
                    Media.advertisement_id == advertisement.id,
                    Media.is_current.is_(True),
                )
                .order_by(Media.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    media = [
        RecordMediaRead(
            id=item.id,
            url=_media_object_url(item, variant="display"),
            thumbnail_url=_media_object_url(item, variant="thumbnail"),
            type="video" if item.mime_type.startswith("video/") else "image",
            sensitivity="safe" if item.classification == "safe" else "explicit",
            source_name=source.name,
            added_at=item.created_at,
            classification=item.classification,
            classification_confidence=item.classification_confidence,
            safety_signals=item.safety_signals or {},
            review_status=item.review_status,
            processing_status=item.processing_status,
            display_url=_media_object_url(item, variant="display"),
            original_url=_media_object_url(item, variant="original"),
        )
        for item in media_rows
    ]
    return RecordOccurrenceDetailRead(
        id=advertisement.id,
        source_name=source.name,
        source_code=source.slug,
        country_code=source.country_code,
        title=advertisement.title or "(Senza titolo)",
        description=advertisement.description or "",
        url=advertisement.source_url,
        phone=phone,
        phone_visibility=visibility,
        listing_page_number=advertisement.listing_page_number,
        status=advertisement.status,
        match_confidence=round(advertisement.confidence * 100, 1),
        first_seen_at=advertisement.first_seen_at,
        last_seen_at=advertisement.last_seen_at,
        scraped_at=advertisement.scraped_at,
        last_changed_at=advertisement.last_changed_at,
        custom_fields=advertisement.custom_fields or {},
        media=media,
    )


def _audit_detail(row: AuditLog) -> str:
    if row.details_json:
        return json.dumps(row.details_json, ensure_ascii=False)
    return f"{row.entity_type} {row.entity_id or ''}".strip()


@router.get("/{record_id}/history", response_model=list[RecordHistoryEventRead])
async def get_record_history(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RecordHistoryEventRead]:
    """Storico "unificato" del record.

    Non esiste una singola tabella di storico per Record: uniamo tre fonti
    diverse, ciascuna già pensata per tracciare un aspetto specifico:

    - `canonical_history`: cambi dell'annuncio canonico (automatici o
      override manuale di un operatore).
    - `media_classification_history`: riclassificazioni dei media collegati
      agli annunci del record (automatiche dal classificatore o manuali).
    - `audit_log`: azioni generiche esplicitamente audit-loggate che
      referenziano questo record come entità (es. rigenerazione riepilogo
      AI, vedi `POST /records/{id}/ai-summary/regenerate`).

    I tre elenchi vengono normalizzati sulla stessa forma e poi ordinati
    insieme per data decrescente.
    """
    await _get_record_or_404(db, record_id)

    canonical_rows = (
        await db.execute(
            select(CanonicalHistory, User.email)
            .outerjoin(User, User.id == CanonicalHistory.overridden_by_user_id)
            .where(CanonicalHistory.record_id == record_id)
        )
    ).all()

    media_rows = (
        await db.execute(
            select(MediaClassificationHistory, User.email)
            .join(Media, Media.id == MediaClassificationHistory.media_id)
            .join(Advertisement, Advertisement.id == Media.advertisement_id)
            .outerjoin(User, User.id == MediaClassificationHistory.changed_by_user_id)
            .where(Advertisement.record_id == record_id)
        )
    ).all()

    audit_rows = (
        await db.execute(
            select(AuditLog, User.email)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(AuditLog.entity_type == "record", AuditLog.entity_id == str(record_id))
        )
    ).all()

    version_rows = (
        (
            await db.execute(
                select(AdvertisementVersion)
                .join(Advertisement, Advertisement.id == AdvertisementVersion.advertisement_id)
                .where(
                    Advertisement.record_id == record_id,
                    AdvertisementVersion.revision > 1,
                )
            )
        )
        .scalars()
        .all()
    )

    events: list[RecordHistoryEventRead] = []

    for row, overridden_by_email in canonical_rows:
        is_manual_override = row.overridden_by_user_id is not None
        actor = "admin" if is_manual_override else "system"
        actor_label = (
            overridden_by_email
            if (is_manual_override and overridden_by_email)
            else "Regola automatica"
        )
        events.append(
            RecordHistoryEventRead(
                id=f"canonical:{row.id}",
                actor=actor,
                actor_label=actor_label,
                action="Cambio annuncio canonico",
                detail=row.reason,
                occurred_at=row.created_at,
            )
        )

    for row, changed_by_email in media_rows:
        actor = "admin" if row.manual_override else "ai"
        actor_label = (
            changed_by_email
            if (row.manual_override and changed_by_email)
            else "Classificatore automatico"
        )
        detail = f"{row.previous_classification or 'n/d'} -> {row.new_classification}"
        if row.confidence is not None:
            detail += f" (confidence={row.confidence:.2f})"
        events.append(
            RecordHistoryEventRead(
                id=f"media:{row.id}",
                actor=actor,
                actor_label=actor_label,
                action="Riclassificazione media",
                detail=detail,
                occurred_at=row.created_at,
            )
        )

    for row, actor_email in audit_rows:
        actor = "admin" if actor_email else "system"
        actor_label = actor_email or "Sistema"
        events.append(
            RecordHistoryEventRead(
                id=f"audit:{row.id}",
                actor=actor,
                actor_label=actor_label,
                action=row.action,
                detail=_audit_detail(row),
                occurred_at=row.created_at,
            )
        )

    for row in version_rows:
        fields = ", ".join(row.changed_fields) or "contenuto"
        events.append(
            RecordHistoryEventRead(
                id=f"advertisement:{row.id}",
                actor="system",
                actor_label="Scraper",
                action=f"Occorrenza aggiornata (revisione {row.revision})",
                detail=f"Campi modificati: {fields}",
                occurred_at=row.created_at,
            )
        )

    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return events


def _summary_version_fields(version: SummaryVersion, current_revision: int) -> dict:
    """Campi comuni tra `RecordAiSummaryRead` (ultima versione) e
    `RecordAiSummaryVersionRead` (voce di storico) — evita di duplicare il
    parsing di `summary_json` nei due endpoint che lo consumano."""
    payload = version.summary_json or {}
    forum_information = payload.get("forum_information", [])
    forum_chatter = [
        entry.get("snippet", "")
        for entry in forum_information
        if isinstance(entry, dict) and entry.get("snippet")
    ]
    # SummaryPayload.sources è una semplice lista di URL (vedi
    # app/services/summary_generator.py): non porta un "nome fonte"
    # separato. Usiamo l'URL anche come nome finché il generatore non
    # produrrà una struttura più ricca (es. {name, url}).
    sources_used = [SourceUsedRead(name=url, url=url) for url in payload.get("sources", []) if url]
    return {
        "generated_at": version.created_at,
        "executive_synthesis": payload.get("summary", ""),
        "unverified_claims": payload.get("unverified_claims", []),
        "forum_chatter": forum_chatter,
        "sources_used": sources_used,
        "provider": version.model_provider,
        "model": version.model_name,
        "record_content_revision": version.record_content_revision,
        "is_stale": version.record_content_revision < current_revision,
    }


def _summary_version_to_schema(
    version: SummaryVersion, current_revision: int
) -> RecordAiSummaryRead:
    return RecordAiSummaryRead(**_summary_version_fields(version, current_revision))


def _summary_version_to_versioned_schema(
    version: SummaryVersion, current_revision: int
) -> RecordAiSummaryVersionRead:
    return RecordAiSummaryVersionRead(
        **_summary_version_fields(version, current_revision), version=version.version
    )


@router.get("/{record_id}/ai-summary/versions", response_model=list[RecordAiSummaryVersionRead])
async def get_record_ai_summary_versions(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RecordAiSummaryVersionRead]:
    """Storico COMPLETO delle versioni del riepilogo AI (a differenza di
    `GET /{record_id}/ai-summary`, che restituisce solo l'ultima): permette
    alla UI di offrire un selettore storico invece di mostrare solo il
    riepilogo più recente (`frontend/src/routes/records/
    RecordAiSummaryTab.tsx`). Ordinate dalla più recente alla più vecchia.
    """
    record = await _get_record_or_404(db, record_id)

    stmt = (
        select(SummaryVersion)
        .where(SummaryVersion.record_id == record_id)
        .order_by(SummaryVersion.version.desc())
    )
    versions = (await db.execute(stmt)).scalars().all()
    return [_summary_version_to_versioned_schema(v, record.content_revision) for v in versions]


@router.get(
    "/{record_id}/ai-summary",
    response_model=RecordAiSummaryRead,
    responses={204: {"description": "Nessun riepilogo AI ancora generato per questo record."}},
)
async def get_record_ai_summary(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Ultima versione del riepilogo AI per il record.

    Se non è mai stato generato nessun riepilogo, rispondiamo 204 No
    Content invece di 404: `frontend/src/api/client.ts` mappa esplicitamente
    uno `status === 204` a `undefined`, e
    `frontend/src/routes/records/RecordAiSummaryTab.tsx` già gestisce
    `summary.data` falsy mostrando "No AI summary available" — un 404
    verrebbe invece trattato come errore di query (`summary.isError`),
    mostrando un messaggio di errore fuorviante per uno stato in realtà
    normale ("non ancora generato").
    """
    record = await _get_record_or_404(db, record_id)

    stmt = (
        select(SummaryVersion)
        .where(SummaryVersion.record_id == record_id)
        .order_by(SummaryVersion.version.desc())
        .limit(1)
    )
    version = (await db.execute(stmt)).scalar_one_or_none()
    if version is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return _summary_version_to_schema(version, record.content_revision)


@router.post(
    "/{record_id}/ai-summary/regenerate",
    response_model=SummaryGenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_record_ai_summary(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> SummaryGenerationJobRead:
    """Accoda un job persistente; nessun provider viene chiamato dal processo API."""
    record = await _get_record_or_404(db, record_id)
    ai = await db.get(AISettings, 1)
    if ai is None:
        raise HTTPException(status_code=503, detail="Configurazione AI non inizializzata.")
    provider = (
        await db.execute(
            select(AIProviderConfig).where(AIProviderConfig.provider == ai.active_provider)
        )
    ).scalar_one_or_none()
    if provider is None or not provider.enabled or not provider.model_name:
        raise HTTPException(status_code=503, detail="Provider AI attivo non disponibile.")
    job = SummaryGenerationJob(
        record_id=record_id,
        requested_by_user_id=user.id,
        status="pending",
        model_name=provider.model_name,
        model_provider=provider.provider,
        provider_config_revision=provider.revision,
        prompt_version=ai.prompt_version,
        input_hash="pending-" + uuid.uuid4().hex,
        record_content_revision=record.content_revision,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    from app.workers.tasks_ai import generate_summary

    generate_summary.delay(str(job.id))
    return SummaryGenerationJobRead.model_validate(job, from_attributes=True)


@router.get("/{record_id}/ai-summary/jobs/{job_id}", response_model=SummaryGenerationJobRead)
async def get_summary_generation_job(
    record_id: uuid.UUID,
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SummaryGenerationJobRead:
    """Restituisce un job AI solo se appartiene al record richiesto."""
    job = await db.get(SummaryGenerationJob, job_id)
    if job is None or job.record_id != record_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job AI non trovato.")
    return SummaryGenerationJobRead.model_validate(job, from_attributes=True)
