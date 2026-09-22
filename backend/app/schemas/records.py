"""Schemi Pydantic per Record, Advertisement e riepiloghi (SummaryVersion)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CamelModel

CustomFieldObject = dict[str, str]
CustomFieldValue = str | list[str] | CustomFieldObject | list[CustomFieldObject] | None


class AdvertisementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    source_url: str
    title: str | None
    description: str | None
    custom_fields: dict[str, CustomFieldValue] = Field(default_factory=dict)
    first_seen_at: datetime
    last_seen_at: datetime
    scraped_at: datetime
    confidence: float
    status: str


class RecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    canonical_ad_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    content_revision: int = 0


class RecordDetail(RecordRead):
    advertisements: list[AdvertisementRead] = Field(default_factory=list)


class RecordSearchRequest(BaseModel):
    """Ricerca di un Record a partire da un numero di telefono.

    Il numero viene normalizzato e trasformato in hash di lookup lato
    server (mai confrontato in chiaro con quanto salvato su DB): vedi
    app/services/phone_crypto.py.
    """

    phone: str = Field(
        description="Numero di telefono in un formato qualsiasi (verrà normalizzato)."
    )


class SummaryPayloadSchema(BaseModel):
    """Rispecchia la struttura salvata in `summary_versions.summary_json`
    (vedi app/services/summary_generator.py:SummaryPayload)."""

    summary: str
    advertisement_information: list[dict[str, Any]] = Field(default_factory=list)
    forum_information: list[dict[str, Any]] = Field(default_factory=list)
    unverified_claims: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class SummaryVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    record_id: uuid.UUID
    version: int
    summary_json: SummaryPayloadSchema
    model_name: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Schemi "view" per gli endpoint consumati direttamente da
# frontend/src/api/records.ts (nessun mapping snake->camel lato client: vedi
# app/schemas/common.py:CamelModel). Sono volutamente distinti da
# RecordRead/RecordDetail sopra, che rispecchiano invece 1:1 le colonne del
# modello ORM `Record` e sono usati da endpoint più "grezzi"
# (GET/POST /records/search legacy).
# ---------------------------------------------------------------------------


class RecordSearchResultRead(CamelModel):
    """Una riga dei risultati di `GET /records/search` (ricerca paginata).

    Rispecchia `frontend/src/types/index.ts:RecordSearchResult`.
    """

    id: uuid.UUID
    phone: str
    phone_visibility: str
    canonical_title: str
    sources_count: int
    occurrences_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    status: str


class RecordSearchResponseRead(CamelModel):
    """Busta di paginazione per `GET /records/search`, rispecchia
    `frontend/src/types/index.ts:RecordSearchResponse`."""

    results: list[RecordSearchResultRead]
    total: int
    page: int
    page_size: int


class CustomFieldValueRead(CamelModel):
    """Valore custom raccolto da una specifica fonte/occorrenza."""

    value: CustomFieldValue
    source_id: uuid.UUID
    source_name: str
    source_code: str
    advertisement_id: uuid.UUID
    is_canonical: bool


class CustomFieldGroupRead(CamelModel):
    """Tutti i valori valorizzati di una chiave custom nel Record."""

    name: str
    values: list[CustomFieldValueRead] = Field(default_factory=list)


class RecordOverviewRead(CamelModel):
    """Dettaglio di un Record per la tab "Overview" della UI, rispecchia
    `frontend/src/types/index.ts:RecordOverview`."""

    id: uuid.UUID
    phone: str
    phone_visibility: str
    canonical_title: str
    canonical_description: str
    confidence_score: float
    sources_count: int
    occurrences_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    status: str
    tags: list[str] = Field(default_factory=list)
    # Compatibilita con i client precedenti: snapshot del solo annuncio canonico.
    custom_fields: dict[str, CustomFieldValue] = Field(default_factory=dict)
    custom_field_groups: list[CustomFieldGroupRead] = Field(default_factory=list)
    content_revision: int = 0


class RecordOccurrenceRead(CamelModel):
    """Un singolo annuncio (`Advertisement`) collegato al record, per la tab
    "Occurrences" della UI. Rispecchia `RecordOccurrence`."""

    id: uuid.UUID
    source_name: str
    source_code: str
    title: str
    url: str
    scraped_at: datetime
    is_canonical: bool
    match_confidence: float
    custom_fields: dict[str, CustomFieldValue] = Field(default_factory=dict)
    revision: int = 1
    last_changed_at: datetime
    has_updates: bool = False
    listing_page_number: int | None = None


class AdvertisementVersionRead(CamelModel):
    id: uuid.UUID
    advertisement_id: uuid.UUID
    revision: int
    scrape_run_id: uuid.UUID | None = None
    changed_fields: list[str] = Field(default_factory=list)
    snapshot: dict[str, Any]
    created_at: datetime


class RecordMediaRead(CamelModel):
    """Un media collegato (tramite gli annunci) al record. Rispecchia
    `RecordMedia`."""

    id: uuid.UUID
    url: str
    thumbnail_url: str
    type: str
    sensitivity: str
    source_name: str
    added_at: datetime
    classification: str
    classification_confidence: float | None = None
    safety_signals: dict = Field(default_factory=dict)
    review_status: str
    processing_status: str
    display_url: str
    original_url: str


class RecordOccurrenceDetailRead(CamelModel):
    id: uuid.UUID
    source_name: str
    source_code: str
    country_code: str | None = None
    title: str
    description: str
    url: str
    phone: str
    phone_visibility: str
    listing_page_number: int | None = None
    status: str
    match_confidence: float
    first_seen_at: datetime
    last_seen_at: datetime
    scraped_at: datetime
    last_changed_at: datetime
    custom_fields: dict[str, CustomFieldValue] = Field(default_factory=dict)
    media: list[RecordMediaRead] = Field(default_factory=list)


class RecordHistoryEventRead(CamelModel):
    """Evento di storico "unificato" (canonical_history +
    media_classification_history + audit_log). Rispecchia
    `RecordHistoryEvent`."""

    id: str
    actor: str
    actor_label: str
    action: str
    detail: str
    occurred_at: datetime


class SourceUsedRead(CamelModel):
    name: str
    url: str


class RecordAiSummaryRead(CamelModel):
    """Ultima versione del riepilogo AI di un record. Rispecchia
    `RecordAiSummary`."""

    generated_at: datetime | None
    executive_synthesis: str
    unverified_claims: list[str] = Field(default_factory=list)
    forum_chatter: list[str] = Field(default_factory=list)
    sources_used: list[SourceUsedRead] = Field(default_factory=list)
    provider: str = "openai"
    model: str = "legacy"
    record_content_revision: int = 0
    is_stale: bool = False


class RecordAiSummaryVersionRead(RecordAiSummaryRead):
    """Una singola voce dello storico versioni (`GET /records/{id}/
    ai-summary/versions`): stessa forma di `RecordAiSummaryRead` più
    `version`, per popolare un selettore storico nella UI (`frontend/src/
    routes/records/RecordAiSummaryTab.tsx`)."""

    version: int


class SummaryGenerationJobRead(CamelModel):
    id: uuid.UUID
    record_id: uuid.UUID
    status: str
    provider: str = Field(validation_alias="model_provider", serialization_alias="provider")
    model: str = Field(validation_alias="model_name", serialization_alias="model")
    provider_config_revision: int | None = None
    result_version: int | None = None
    cache_hit: bool = False
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    record_content_revision: int = 0
