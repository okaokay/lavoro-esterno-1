"""Aggrega tutti i modelli ORM sotto un unico registry (`Base`).

Importare questo pacchetto (invece dei singoli moduli) garantisce che
`Base.metadata` contenga TUTTE le tabelle: è quello che Alembic usa come
`target_metadata` in migrations/env.py per l'autogenerate.

L'ordine di import qui non è rilevante per le FK grazie a `use_alter=True`
sulla FK circolare record<->advertisement (vedi app/models/record.py); lo
manteniamo comunque in un ordine "logico" (entità base prima, entità di
audit/derivate dopo) per leggibilità.
"""

from app.models.advertisement import Advertisement
from app.models.advertisement_versions import AdvertisementVersion
from app.models.ai_settings import AIProviderConfig, AISettings
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.canonical_history import CanonicalHistory
from app.models.export_jobs import ExportJob, ExportJobRecord
from app.models.integrations import (
    IngestionSettings,
    ScrapeRunPayload,
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEndpointSource,
)
from app.models.media import Media
from app.models.media_classification_history import MediaClassificationHistory
from app.models.operations import (
    MediaClassifierSettings,
    NotificationEvent,
    NotificationRead,
    SourcePriorityRecalculationJob,
)
from app.models.privacy import ErasureRequest, SuppressionEntry
from app.models.proxies import (
    ProxyEndpoint,
    ProxyFeed,
    ProxyPool,
    ProxyPoolMember,
    ScrapeRunProxyAttempt,
)
from app.models.record import Record
from app.models.scrape_errors import ScrapeError
from app.models.scrape_runs import ScrapeRun
from app.models.sources import Source
from app.models.summary_generation_jobs import SummaryGenerationJob
from app.models.summary_versions import SummaryVersion
from app.models.users import User

__all__ = [
    "Base",
    "AISettings",
    "AIProviderConfig",
    "User",
    "Source",
    "Record",
    "Advertisement",
    "AdvertisementVersion",
    "Media",
    "CanonicalHistory",
    "ScrapeRun",
    "ScrapeError",
    "MediaClassificationHistory",
    "MediaClassifierSettings",
    "SourcePriorityRecalculationJob",
    "NotificationEvent",
    "NotificationRead",
    "SummaryVersion",
    "SummaryGenerationJob",
    "ExportJob",
    "ExportJobRecord",
    "IngestionSettings",
    "WebhookEndpoint",
    "WebhookEndpointSource",
    "ScrapeRunPayload",
    "WebhookDelivery",
    "ErasureRequest",
    "SuppressionEntry",
    "ProxyPool",
    "ProxyEndpoint",
    "ProxyFeed",
    "ProxyPoolMember",
    "ScrapeRunProxyAttempt",
    "AuditLog",
]
