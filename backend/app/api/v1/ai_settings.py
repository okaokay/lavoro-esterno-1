"""Configurazione Admin-only dei provider usati per i riepiloghi."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.ai_settings import AIProviderConfig, AISettings
from app.models.users import User
from app.schemas.ai_settings import (
    AIModelCatalogRead,
    AIProviderConfigRead,
    AIProviderConfigUpdate,
    AIProviderTestRead,
    AISettingsRead,
    AISettingsUpdate,
)
from app.security.deps import require_admin_with_2fa, require_role
from app.security.redis_client import get_redis
from app.services.ai_config import (
    PROVIDER_NAMES,
    REMOTE_PROVIDERS,
    runtime_config,
    validate_custom_ai_endpoint,
)
from app.services.ai_credentials import encrypt_ai_credential
from app.services.audit import log_action
from app.services.summary_generator import ProviderError, create_summary_provider

router = APIRouter()

_OPTION_KEYS = {
    "openai": {"organization", "project"},
    "openrouter": {"site_url", "app_name"},
}


def _provider_read(row: AIProviderConfig, active: str) -> AIProviderConfigRead:
    return AIProviderConfigRead(
        provider=row.provider,
        display_name=row.display_name,
        model=row.model_name,
        enabled=row.enabled,
        active=row.provider == active,
        base_url=row.base_url,
        credential_configured=row.api_key_encrypted is not None,
        options={str(k): str(v) for k, v in (row.config_json or {}).items()},
        revision=row.revision,
        last_tested_at=row.last_tested_at,
        last_test_success=row.last_test_success,
    )


async def _read_all(db: AsyncSession) -> tuple[AISettings, list[AIProviderConfig]]:
    ai = await db.get(AISettings, 1)
    if ai is None:
        raise HTTPException(503, "Configurazione AI assente: applicare le migrazioni.")
    rows = list(
        (
            await db.execute(select(AIProviderConfig).order_by(AIProviderConfig.display_name))
        ).scalars()
    )
    return ai, rows


@router.get("/ai-settings", response_model=AISettingsRead)
async def get_ai_settings(
    db: AsyncSession = Depends(get_db), _admin: User = Depends(require_role("admin"))
) -> AISettingsRead:
    """Restituisce la configurazione AI globale senza esporre credenziali."""
    ai, providers = await _read_all(db)
    return AISettingsRead(
        active_provider=ai.active_provider,
        prompt_version=ai.prompt_version,
        user_daily_request_limit=ai.user_daily_request_limit,
        provider_requests_per_minute=ai.provider_requests_per_minute,
        global_daily_token_budget=ai.global_daily_token_budget,
        revision=ai.revision,
        providers=[_provider_read(row, ai.active_provider) for row in providers],
    )


@router.patch("/ai-settings", response_model=AISettingsRead)
async def update_ai_settings(
    payload: AISettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> AISettingsRead:
    """Aggiorna limiti e provider attivo con controllo di revisione."""
    ai, providers = await _read_all(db)
    if payload.expected_revision != ai.revision:
        raise HTTPException(status.HTTP_409_CONFLICT, "Impostazioni modificate da un altro Admin.")
    values = {row.provider: row for row in providers}
    active = payload.active_provider or ai.active_provider
    target = values.get(active)
    budget = (
        payload.global_daily_token_budget
        if payload.global_daily_token_budget is not None
        else ai.global_daily_token_budget
    )
    if target is None or not target.enabled or not target.model_name:
        raise HTTPException(422, "Il provider selezionato non e abilitato o non ha un modello.")
    if active in REMOTE_PROVIDERS:
        if target.api_key_encrypted is None or target.last_test_success is not True:
            raise HTTPException(422, "Il provider remoto richiede credenziali e un test riuscito.")
        if budget <= 0:
            raise HTTPException(422, "Impostare un budget token positivo per i provider cloud.")
    changes = {}
    for attr in (
        "active_provider",
        "user_daily_request_limit",
        "provider_requests_per_minute",
        "global_daily_token_budget",
    ):
        value = getattr(payload, attr)
        if value is not None and value != getattr(ai, attr):
            changes[attr] = value
            setattr(ai, attr, value)
    if changes:
        ai.revision += 1
        await log_action(
            db,
            user_id=admin.id,
            action="update_ai_settings",
            entity_type="ai_settings",
            entity_id="1",
            details={"changed_fields": sorted(changes)},
        )
        await db.commit()
    return await get_ai_settings(db, admin)


async def _provider_or_404(db: AsyncSession, provider: str) -> AIProviderConfig:
    if provider not in PROVIDER_NAMES:
        raise HTTPException(404, "Provider AI non trovato.")
    row = (
        await db.execute(select(AIProviderConfig).where(AIProviderConfig.provider == provider))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Provider AI non trovato.")
    return row


@router.patch("/ai-settings/providers/{provider}", response_model=AIProviderConfigRead)
async def update_ai_provider(
    provider: str,
    payload: AIProviderConfigUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> AIProviderConfigRead:
    """Aggiorna un provider conservando la chiave cifrata quando non sostituita."""
    row = await _provider_or_404(db, provider)
    ai = await db.get(AISettings, 1)
    if payload.expected_revision != row.revision:
        raise HTTPException(409, "Provider modificato da un altro Admin.")
    if provider != "custom_openai" and payload.base_url is not None:
        raise HTTPException(422, "L'endpoint e modificabile solo per il provider custom.")
    if provider == "ollama" and (payload.api_key or payload.clear_credential):
        raise HTTPException(422, "Ollama locale non usa API key.")
    if payload.options is not None:
        unexpected = set(payload.options) - _OPTION_KEYS.get(provider, set())
        if unexpected:
            raise HTTPException(422, f"Opzioni non ammesse: {', '.join(sorted(unexpected))}.")
    changed = []
    configuration_changed = False
    if payload.model is not None and payload.model.strip() != row.model_name:
        row.model_name = payload.model.strip()
        changed.append("model")
        configuration_changed = True
    if payload.base_url is not None:
        try:
            url = validate_custom_ai_endpoint(str(payload.base_url))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if url != row.base_url:
            row.base_url = url
            changed.append("base_url")
            configuration_changed = True
    if payload.api_key is not None:
        try:
            row.api_key_encrypted = encrypt_ai_credential(payload.api_key)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        changed.append("credential")
        configuration_changed = True
    elif payload.clear_credential and row.api_key_encrypted is not None:
        row.api_key_encrypted = None
        row.enabled = False
        changed.extend(["credential", "enabled"])
    if payload.options is not None and payload.options != (row.config_json or {}):
        row.config_json = payload.options
        changed.append("options")
        configuration_changed = True
    if configuration_changed:
        row.last_test_success = None
        if provider in REMOTE_PROVIDERS and row.enabled:
            row.enabled = False
            changed.append("enabled")
    if payload.enabled is not None and not configuration_changed and payload.enabled != row.enabled:
        if (
            payload.enabled
            and provider in REMOTE_PROVIDERS
            and (row.api_key_encrypted is None or row.last_test_success is not True)
        ):
            raise HTTPException(
                422, "Prima di abilitare il provider salvare la chiave ed eseguire un test."
            )
        row.enabled = payload.enabled
        changed.append("enabled")
    if changed:
        row.revision += 1
        await log_action(
            db,
            user_id=admin.id,
            action="update_ai_provider",
            entity_type="ai_provider",
            entity_id=provider,
            details={"changed_fields": sorted(set(changed))},
        )
        await db.commit()
        await db.refresh(row)
    return _provider_read(row, ai.active_provider)


@router.get("/ai-settings/providers/{provider}/models", response_model=AIModelCatalogRead)
async def list_ai_models(
    provider: str,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
) -> AIModelCatalogRead:
    """Elenca i modelli del provider usando la cache salvo refresh esplicito."""
    row = await _provider_or_404(db, provider)
    if provider in REMOTE_PROVIDERS and row.api_key_encrypted is None:
        raise HTTPException(422, "Configurare prima la API key del provider.")
    cache = get_redis()
    key = f"ai:model-catalog:{provider}:{row.revision}"
    cached = None if refresh else await cache.get(key)
    if cached:
        return AIModelCatalogRead(provider=provider, models=json.loads(cached), cached=True)
    try:
        models = await asyncio.to_thread(create_summary_provider(runtime_config(row)).list_models)
    except (ProviderError, RuntimeError, ValueError) as exc:
        raise HTTPException(502, str(exc)) from exc
    # Un catalogo vuoto durante il pull iniziale di Ollama non deve nascondere
    # per cinque minuti un modello che diventa disponibile pochi secondi dopo.
    ttl = settings.AI_MODEL_CATALOG_TTL_SECONDS if models else 5
    await cache.setex(key, ttl, json.dumps(models))
    return AIModelCatalogRead(provider=provider, models=models, cached=False)


@router.post("/ai-settings/providers/{provider}/test", response_model=AIProviderTestRead)
async def test_ai_provider(
    provider: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> AIProviderTestRead:
    """Verifica connettività e output strutturato del provider configurato."""
    row = await _provider_or_404(db, provider)
    if not row.model_name or (provider in REMOTE_PROVIDERS and row.api_key_encrypted is None):
        raise HTTPException(422, "Configurare modello e credenziali prima del test.")
    started = time.perf_counter()
    try:
        await asyncio.to_thread(
            create_summary_provider(runtime_config(row)).generate_structured,
            {
                "advertisements": [
                    {
                        "source_ref": "source-1",
                        "title": "Test",
                        "description": "Synthetic connectivity test.",
                    }
                ],
                "forum_snippets": [],
            },
        )
        success, message = True, "Connessione e output strutturato verificati."
    except (ProviderError, RuntimeError, ValueError) as exc:
        success, message = False, str(exc)
    row.last_tested_at = datetime.now(UTC)
    row.last_test_success = success
    await log_action(
        db,
        user_id=admin.id,
        action="test_ai_provider",
        entity_type="ai_provider",
        entity_id=provider,
        details={"success": success},
    )
    await db.commit()
    return AIProviderTestRead(
        provider=provider,
        success=success,
        latency_ms=round((time.perf_counter() - started) * 1000),
        message=message,
    )
