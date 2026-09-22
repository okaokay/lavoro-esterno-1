"""Configurazione dell'app Celery: broker/backend Redis, code separate per
dominio (scraping/media/ai) e scheduling via Celery Beat.

Code separate per dominio permettono di scalare/limitare la concorrenza in
modo indipendente (es. lo scraping va rate-limitato per non violare i ToS
delle fonti, la classificazione media può essere CPU/GPU-bound, l'AI può
dipendere da rate limit di un provider esterno).
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "lavoro_esterno",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.tasks_scraper",
        "app.workers.tasks_media",
        "app.workers.tasks_ai",
        "app.workers.tasks_exports",
        "app.workers.tasks_privacy",
        "app.workers.tasks_maintenance",
        "app.workers.tasks_operations",
        "app.workers.tasks_webhooks",
        "app.workers.tasks_proxy_feeds",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Eventi necessari a celery-exporter per stato worker, code, tempi di
    # attesa/esecuzione e risultati dei task.
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_track_started=True,
    task_routes={
        "app.workers.tasks_scraper.dispatch_due_source_scrapes": {"queue": "maintenance"},
        "app.workers.tasks_scraper.*": {"queue": "scraping"},
        "app.workers.tasks_media.*": {"queue": "media"},
        "app.workers.tasks_ai.*": {"queue": "ai"},
        "app.workers.tasks_exports.*": {"queue": "exports"},
        "app.workers.tasks_privacy.*": {"queue": "maintenance"},
        # I task di manutenzione (pulizia retention) sono leggeri e poco
        # frequenti (una volta al giorno): li instradiamo sulla coda
        # "scraping" già esistente invece di introdurre un servizio Celery
        # dedicato solo per questo in docker-compose.yml (vedi
        # worker-scraper: `-Q scraping,maintenance`).
        "app.workers.tasks_maintenance.*": {"queue": "maintenance"},
        "app.workers.tasks_operations.*": {"queue": "maintenance"},
        "app.workers.tasks_webhooks.*": {"queue": "webhooks"},
        "app.workers.tasks_proxy_feeds.*": {"queue": "maintenance"},
    },
)

# Celery Beat: dispatcher scraping ogni minuto e manutenzioni notturne.
celery_app.conf.beat_schedule = {
    "dispatch-due-source-scrapes": {
        "task": "app.workers.tasks_scraper.dispatch_due_source_scrapes",
        "schedule": 60.0,
    },
    "dispatch-due-proxy-feeds": {
        "task": "app.workers.tasks_proxy_feeds.dispatch_due_proxy_feeds",
        "schedule": 60.0,
    },
    "cleanup-expired-data-nightly": {
        "task": "app.workers.tasks_maintenance.cleanup_expired_data",
        "schedule": crontab(hour=3, minute=0),
    },
    "cleanup-orphan-media-nightly": {
        "task": "app.workers.tasks_maintenance.cleanup_orphan_media_objects",
        "schedule": crontab(hour=4, minute=0),
    },
    "configure-media-lifecycle-daily": {
        "task": "app.workers.tasks_maintenance.configure_media_lifecycle",
        "schedule": crontab(hour=4, minute=30),
    },
}
