"""Accesso centralizzato alla configurazione AI persistita."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.ai_settings import AIProviderConfig, AISettings
from app.services.ai_credentials import decrypt_ai_credential

PROVIDER_NAMES = {
    "ollama": "Ollama locale",
    "openai": "OpenAI",
    "anthropic": "Anthropic / Claude",
    "google": "Google Gemini",
    "groq": "Groq",
    "mistral": "Mistral",
    "openrouter": "OpenRouter",
    "custom_openai": "OpenAI-compatible personalizzato",
}
REMOTE_PROVIDERS = frozenset(PROVIDER_NAMES) - {"ollama"}


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    provider: str
    model: str
    base_url: str | None
    api_key: str | None
    options: dict = field(default_factory=dict)
    revision: int = 1


def load_active_runtime_config(session: Session) -> tuple[AISettings, ProviderRuntimeConfig]:
    ai = session.get(AISettings, 1)
    if ai is None:
        raise RuntimeError("Configurazione AI non inizializzata: applicare le migrazioni.")
    provider = session.execute(
        select(AIProviderConfig).where(AIProviderConfig.provider == ai.active_provider)
    ).scalar_one_or_none()
    if provider is None or not provider.enabled or not provider.model_name.strip():
        raise RuntimeError("Il provider AI attivo non e configurato o abilitato.")
    return ai, runtime_config(provider)


def runtime_config(provider: AIProviderConfig) -> ProviderRuntimeConfig:
    base_url = settings.OLLAMA_ENDPOINT if provider.provider == "ollama" else provider.base_url
    if provider.provider == "custom_openai":
        if not base_url:
            raise ValueError("Endpoint custom non configurato.")
        base_url = validate_custom_ai_endpoint(base_url)
    return ProviderRuntimeConfig(
        provider=provider.provider,
        model=provider.model_name,
        base_url=base_url,
        api_key=decrypt_ai_credential(provider.api_key_encrypted),
        options=provider.config_json or {},
        revision=provider.revision,
    )


def validate_custom_ai_endpoint(value: str) -> str:
    """Blocca credenziali in URL e destinazioni SSRF, anche al momento dell'uso."""
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("L'endpoint custom deve essere un URL HTTPS senza credenziali.")
    allowlist = {
        item.strip().lower()
        for item in settings.AI_CUSTOM_ENDPOINT_ALLOWLIST.split(",")
        if item.strip()
    }
    if parsed.hostname.lower() not in allowlist:
        try:
            addresses = {
                result[4][0] for result in socket.getaddrinfo(parsed.hostname, parsed.port or 443)
            }
        except socket.gaierror as exc:
            raise ValueError("Host dell'endpoint custom non risolvibile.") from exc
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ValueError("Endpoint custom privato o riservato non consentito.")
    return value.rstrip("/")
