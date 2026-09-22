"""Configurazione centralizzata dell'applicazione.

Tutte le variabili sono lette dall'ambiente (o da un file .env, gestito da un
task separato che crea `.env.example` a livello di repository: qui definiamo
solo la struttura tipizzata e i default utili per lo sviluppo locale).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Impostazioni applicative, validate a runtime da Pydantic Settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Database -----------------------------------------------------
    # URL "canonico" in stile SQLAlchemy; il driver asyncpg viene forzato
    # a runtime in app.db se l'URL usa lo schema generico "postgresql://".
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://lavoro_esterno:lavoro_esterno@localhost:5432/lavoro_esterno",
        description="Connection string PostgreSQL (driver asyncpg per runtime async).",
    )
    # Variante sincrona usata da Alembic (psycopg2), che non supporta async.
    DATABASE_URL_SYNC: str | None = Field(
        default=None,
        description="Override opzionale per la connection string sincrona (Alembic).",
    )

    # --- Redis (broker/backend Celery e cache) -------------------------
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="URL di connessione a Redis, usato come broker/backend Celery.",
    )

    # --- MinIO (object storage per i media) -----------------------------
    MINIO_ENDPOINT: str = Field(
        default="localhost:9000", description="Host:porta dell'endpoint MinIO/S3."
    )
    MINIO_ACCESS_KEY: str = Field(default="minioadmin", description="Access key MinIO.")
    MINIO_SECRET_KEY: str = Field(default="minioadmin", description="Secret key MinIO.")
    MINIO_BUCKET: str = Field(
        default="lavoro-esterno-media", description="Bucket per i media raccolti."
    )
    MINIO_SECURE: bool = Field(
        default=False, description="Usa TLS per la connessione a MinIO (True in produzione)."
    )
    MINIO_PUBLIC_ENDPOINT: str | None = Field(
        default=None,
        description="Endpoint MinIO raggiungibile dal browser per gli URL presigned.",
    )
    MINIO_REGION: str = Field(
        default="us-east-1",
        min_length=1,
        description="Regione S3 condivisa da MinIO e client per firmare URL senza I/O.",
    )
    MINIO_PRESIGNED_TTL_MINUTES: int = Field(default=15, ge=1, le=60)

    # --- Media -----------------------------------------------------------
    MEDIA_IMAGE_MAX_BYTES: int = Field(default=15 * 1024 * 1024, ge=1)
    MEDIA_VIDEO_MAX_BYTES: int = Field(default=100 * 1024 * 1024, ge=1)
    MEDIA_IMAGE_MAX_PIXELS: int = Field(default=40_000_000, ge=1)
    MEDIA_VIDEO_MAX_SECONDS: int = Field(default=300, ge=1)
    MEDIA_ORPHAN_GRACE_HOURS: int = Field(default=24, ge=1)
    MEDIA_EXPLICIT_THRESHOLD: float = Field(default=0.65, ge=0, le=1)
    MEDIA_SAFE_THRESHOLD: float = Field(default=0.20, ge=0, le=1)

    # --- Riepiloghi AI --------------------------------------------------
    AI_CREDENTIAL_ENCRYPTION_KEY: str | None = Field(
        default=None,
        description="Chiave AES-256 base64 dedicata alle credenziali dei provider AI.",
    )
    OLLAMA_ENDPOINT: str = Field(default="http://ollama:11434")
    AI_CUSTOM_ENDPOINT_ALLOWLIST: str = Field(
        default="",
        description="Host custom privati consentiti, separati da virgola; vuoto blocca la LAN.",
    )
    AI_MODEL_CATALOG_TTL_SECONDS: int = Field(default=300, ge=30, le=3600)
    AI_MAX_OUTPUT_TOKENS: int = Field(default=2000, ge=100, le=10000)
    AI_PROVIDER_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0, le=300)
    # Compatibilita temporanea: non sono piu la fonte runtime dei provider.
    OPENAI_API_KEY: str | None = Field(default=None, description="API key OpenAI server-side.")
    OPENAI_MODEL: str = Field(default="gpt-5.6-luna")
    OPENAI_PROMPT_VERSION: str = Field(default="summary-v2-it")
    OPENAI_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0, le=300)
    AI_MAX_INPUT_CHARS: int = Field(default=100_000, ge=1)

    # --- Proxy scraper ---------------------------------------------------
    PROXY_CREDENTIAL_ENCRYPTION_KEY: str | None = Field(
        default=None, description="Chiave AES-256 base64 dedicata alle credenziali proxy."
    )
    PROXY_PRIVATE_HOST_ALLOWLIST: str = Field(
        default="", description="Host proxy privati consentiti, separati da virgola."
    )
    PROXY_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=10)
    INTEGRATION_ENCRYPTION_KEY: str | None = Field(
        default="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        description="Chiave AES-256 base64 per originali ripuliti, webhook e header dei feed.",
    )

    # --- Scheduling scraper -----------------------------------------------
    SCRAPE_PENDING_RETRY_MINUTES: int = Field(default=2, ge=1, le=60)
    SCRAPE_STALE_HOURS: int = Field(default=6, ge=1, le=72)
    SCRAPE_SCHEDULER_BATCH_SIZE: int = Field(default=100, ge=1, le=1000)

    # --- JWT (autenticazione) -------------------------------------------
    JWT_SECRET_KEY: str = Field(
        default="dev-insecure-secret-change-me",
        description="Chiave simmetrica per firmare i JWT access/refresh (HS256).",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="Algoritmo di firma JWT.")
    JWT_ACCESS_TTL_MINUTES: int = Field(
        default=15, description="Durata di validità del token di accesso, in minuti."
    )
    JWT_REFRESH_TTL_DAYS: int = Field(
        default=14, description="Durata di validità del token di refresh, in giorni."
    )

    # --- Rate limiting / lockout login e 2FA (protezione brute-force) ----
    LOGIN_MAX_ATTEMPTS: int = Field(
        default=5, description="Tentativi di login (password) falliti prima del lockout account."
    )
    LOGIN_LOCKOUT_MINUTES: int = Field(
        default=15, description="Durata del lockout dopo LOGIN_MAX_ATTEMPTS tentativi falliti."
    )
    MFA_MAX_ATTEMPTS: int = Field(
        default=5,
        description="Tentativi di verifica 2FA (TOTP/backup code) falliti prima del lockout.",
    )
    MFA_LOCKOUT_MINUTES: int = Field(
        default=15, description="Durata del lockout dopo MFA_MAX_ATTEMPTS tentativi 2FA falliti."
    )

    # --- Policy password ---------------------------------------------------
    # Solo complessità minima, nessuna scadenza forzata (decisione di prodotto).
    PASSWORD_MIN_LENGTH: int = Field(
        default=12, description="Lunghezza minima richiesta per le password (creazione/cambio)."
    )

    # --- Cifratura telefono (privacy / GDPR) ----------------------------
    # Chiave AES-256 (32 byte) codificata base64, usata per cifrare a riposo
    # il numero di telefono. Deve essere diversa da PHONE_HMAC_SECRET: la prima
    # cifra il dato (reversibile con la chiave), la seconda produce un hash di
    # lookup deterministico ma NON invertibile.
    PHONE_ENCRYPTION_KEY: str = Field(
        default="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        description="Chiave AES-256-GCM (32 byte, base64) per cifrare il numero di telefono.",
    )
    PHONE_HMAC_SECRET: str = Field(
        default="dev-insecure-hmac-secret-change-me",
        description="Chiave segreta HMAC-SHA256 per l'hash di lookup deterministico del telefono.",
    )

    # --- Retention dati (pulizia periodica, vedi app/workers/tasks_maintenance.py) --
    # Nessuna scadenza automatica per dati "vivi" (record/advertisement/media):
    # la retention di questi resta sospesa a una validazione legale/GDPR
    # definitiva (vedi docs/SICUREZZA.md). Qui solo dati accessori/di log, per
    # cui una retention di default è una scelta operativa ragionevole e
    # reversibile (i valori sono configurabili via env, non un vincolo fisso).
    AUDIT_LOG_RETENTION_DAYS: int = Field(
        default=365, description="Giorni di conservazione di audit_log prima della cancellazione."
    )
    SCRAPE_ERROR_RETENTION_DAYS: int = Field(
        default=90,
        description="Giorni di conservazione di scrape_errors prima della cancellazione.",
    )
    EXPORT_RETENTION_DAYS: int = Field(
        default=7,
        description=(
            "Giorni dopo i quali un pacchetto di export viene rimosso da MinIO "
            "(la riga export_jobs resta, per audit, ma perde object_key)."
        ),
    )
    ADVERTISEMENT_RETENTION_DAYS: int = Field(default=365, ge=0)
    MEDIA_RETENTION_DAYS: int = Field(default=180, ge=0)
    TECHNICAL_LOG_RETENTION_DAYS: int = Field(default=90, ge=0)
    EXPORT_MAX_RECORDS: int = Field(default=1_000, ge=1, le=100_000)
    EXPORT_MAX_UNCOMPRESSED_BYTES: int = Field(default=2 * 1024 * 1024 * 1024, ge=1)
    EXPORT_ORPHAN_GRACE_HOURS: int = Field(default=24, ge=1)
    NOTIFICATION_RETENTION_DAYS: int = Field(default=90, ge=0)

    # --- CORS -------------------------------------------------------------
    CORS_ORIGIN: str = Field(
        default="http://localhost:5173",
        description=(
            "Origin consentita per le richieste CORS del frontend (lista separata da virgole)."
        ),
    )

    # --- Applicazione -------------------------------------------------------
    APP_NAME: str = Field(default="Lavoro Esterno API", description="Nome applicazione.")
    ENVIRONMENT: str = Field(
        default="development",
        description="Ambiente di esecuzione (development/staging/production).",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Espande CORS_ORIGIN (stringa CSV) in una lista di origin per FastAPI CORSMiddleware."""
        return [origin.strip() for origin in self.CORS_ORIGIN.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Restituisce un'istanza cacheata delle impostazioni (evita di ri-parsare l'ambiente)."""
    return Settings()


settings = get_settings()
