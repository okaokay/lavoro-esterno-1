"""Endpoint di ricerca per numero di telefono (via hash di lookup)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.advertisement import Advertisement
from app.models.record import Record
from app.models.users import User
from app.schemas.search import PhoneSearchRequest, PhoneSearchResult
from app.security.deps import get_current_user
from app.services.phone_crypto import phone_lookup_hash

router = APIRouter()


@router.post("", response_model=list[PhoneSearchResult])
async def search_by_phone(
    payload: PhoneSearchRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[PhoneSearchResult]:
    """Cerca un Record per numero di telefono.

    Il confronto avviene interamente tramite `phone_lookup_hash` (HMAC
    deterministico): il numero in chiaro non viene mai usato in una query SQL,
    né salvato in log applicativi.
    """
    lookup_hash = phone_lookup_hash(payload.phone)

    result = await db.execute(select(Record).where(Record.phone_lookup_hash == lookup_hash))
    record = result.scalar_one_or_none()
    if record is None:
        return []

    count_result = await db.execute(
        select(func.count()).select_from(Advertisement).where(Advertisement.record_id == record.id)
    )
    advertisement_count = count_result.scalar_one()

    return [
        PhoneSearchResult(
            record_id=record.id,
            canonical_ad_id=record.canonical_ad_id,
            advertisement_count=advertisement_count,
        )
    ]
