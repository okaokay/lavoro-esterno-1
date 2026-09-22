"""Validation helpers for portable source configuration documents."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.proxies import ProxyPool
from app.models.sources import Source
from app.schemas.sources import (
    SourceImportPreviewEntry,
    SourceImportPreviewResult,
    SourceTransferItem,
)


def _validation_messages(exc: ValidationError) -> list[str]:
    messages: list[str] = []
    for error in exc.errors(include_url=False):
        location = ".".join(str(part) for part in error["loc"])
        prefix = f"{location}: " if location else ""
        messages.append(f"{prefix}{error['msg']}")
    return messages


async def preview_source_document(
    db: AsyncSession, document: dict[str, Any]
) -> SourceImportPreviewResult:
    global_errors: list[str] = []
    document_format = document.get("format")
    version = document.get("version")
    raw_sources = document.get("sources")
    exported_at = document.get("exportedAt", document.get("exported_at"))

    if document_format != "lavoro-esterno-sources":
        global_errors.append("Formato file non supportato.")
    if type(version) is not int or version != 1:
        global_errors.append("Versione file non supportata.")
    try:
        if not isinstance(exported_at, str):
            raise ValueError
        datetime.fromisoformat(exported_at.replace("Z", "+00:00"))
    except ValueError:
        global_errors.append("Data di esportazione mancante o non valida.")
    if not isinstance(raw_sources, list) or not raw_sources:
        global_errors.append("Il documento deve contenere almeno una fonte.")
        raw_sources = []
    raw_slugs = [item.get("slug") for item in raw_sources if isinstance(item, dict)]
    duplicate_slugs = {slug for slug, count in Counter(raw_slugs).items() if slug and count > 1}

    valid_items: list[SourceTransferItem] = []
    parsed_by_index: dict[int, SourceTransferItem] = {}
    errors_by_index: dict[int, list[str]] = {}
    for index, raw_item in enumerate(raw_sources):
        try:
            item = SourceTransferItem.model_validate(raw_item)
            if item.slug in duplicate_slugs:
                errors_by_index[index] = [f"Lo slug '{item.slug}' è duplicato nel documento."]
                continue
            parsed_by_index[index] = item
            valid_items.append(item)
        except ValidationError as exc:
            errors_by_index[index] = _validation_messages(exc)

    slugs = [item.slug for item in valid_items]
    pool_names = {item.proxy_pool_name for item in valid_items if item.proxy_pool_name}
    existing_slugs = (
        set((await db.execute(select(Source.slug).where(Source.slug.in_(slugs)))).scalars().all())
        if slugs
        else set()
    )
    existing_pools = (
        set(
            (await db.execute(select(ProxyPool.name).where(ProxyPool.name.in_(pool_names))))
            .scalars()
            .all()
        )
        if pool_names
        else set()
    )

    entries: list[SourceImportPreviewEntry] = []
    for index, raw_item in enumerate(raw_sources):
        item = parsed_by_index.get(index)
        errors = errors_by_index.get(index, [])
        if item is None:
            entries.append(
                SourceImportPreviewEntry(
                    index=index,
                    slug=raw_item.get("slug") if isinstance(raw_item, dict) else None,
                    name=raw_item.get("name") if isinstance(raw_item, dict) else None,
                    status="invalid",
                    errors=errors,
                )
            )
            continue

        proxy_status = "none"
        warnings: list[str] = []
        if item.proxy_pool_name:
            proxy_status = "resolved" if item.proxy_pool_name in existing_pools else "missing"
            if proxy_status == "missing":
                warnings.append(
                    f"Pool proxy '{item.proxy_pool_name}' non trovato: la fonte resterà senza pool."
                )
        entries.append(
            SourceImportPreviewEntry(
                index=index,
                slug=item.slug,
                name=item.name,
                status="conflict" if item.slug in existing_slugs else "new",
                proxy_pool_status=proxy_status,
                proxy_pool_name=item.proxy_pool_name,
                warnings=warnings,
            )
        )

    return SourceImportPreviewResult(
        valid=not global_errors and not errors_by_index,
        format=document_format if isinstance(document_format, str) else None,
        version=version if type(version) is int else None,
        entries=entries,
        global_errors=global_errors,
    )
