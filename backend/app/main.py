"""Entry point dell'applicazione FastAPI."""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import api_router
from app.config import settings
from app.db import get_db
from app.i18n.messages import validation_message
from app.services import observability_metrics

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "API per la raccolta e deduplicazione di annunci per numero di telefono, "
        "con gestione media e arricchimento AI."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registra metriche HTTP usando il template FastAPI della route come label:
# UUID e altri valori presenti negli URL non diventano serie ad alta cardinalita.
instrumentator = Instrumentator(
    should_ignore_untemplated=True,
    excluded_handlers=["/metrics"],
    should_instrument_requests_inprogress=True,
    inprogress_name="lavoro_esterno_http_requests_inprogress",
    inprogress_labels=True,
).instrument(app, metric_namespace="lavoro_esterno")

app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(RequestValidationError)
async def italian_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Mantiene il contratto FastAPI traducendo soltanto il testo leggibile."""

    details = []
    for error in exc.errors():
        translated = dict(error)
        translated["msg"] = validation_message(str(error.get("type", "")))
        # L'input può contenere segreti o dati personali: non deve essere
        # riflesso nella risposta di errore.
        translated.pop("input", None)
        translated.pop("ctx", None)
        details.append(translated)
    return JSONResponse(status_code=422, content={"detail": details})


@app.get("/api/v1/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Endpoint di health-check, usato da orchestratori/load balancer."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@app.get("/metrics", include_in_schema=False)
async def metrics(db: AsyncSession = Depends(get_db)) -> Response:
    """Metriche interne Prometheus; nginx non inoltra questo percorso all'API."""

    try:
        await observability_metrics.refresh_scrape_metrics(db)
    except Exception:
        # Una indisponibilita DB non deve nascondere le metriche HTTP/API: il
        # collector espone il proprio stato e conserva l'ultimo snapshot valido.
        logger.exception("Impossibile aggiornare le metriche Prometheus degli scraping")
        observability_metrics.mark_scrape_collector_failed()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
