"""Create one encrypted run payload and scoped webhook deliveries."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.integrations import (
    ScrapeRunPayload,
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEndpointSource,
)
from app.services.integration_crypto import encrypt_json


def enqueue_run_webhooks(session: Session, source, run, collection, outcome: dict) -> list[str]:
    items = []
    if collection is not None:
        for item in collection.ads:
            data = dict(item.normalized)
            data["listingPageNumber"] = item.listing_page_number
            data["persistenceOutcome"] = item.persistence_outcome
            items.append(data)
    payload = {
        "schemaVersion": 1,
        "eventType": "scrape.run.finished",
        "eventId": str(uuid.uuid4()),
        "source": {
            "id": str(source.id),
            "name": source.name,
            "slug": source.slug,
            "countryCode": source.country_code,
        },
        "run": {
            "id": str(run.id),
            "status": run.status,
            "itemsFound": outcome.get("items_found", 0),
            "itemsNew": outcome.get("items_new", 0),
            "itemsUpdated": outcome.get("items_updated", 0),
            "itemsUnchanged": outcome.get("items_unchanged", 0),
            "errorsCount": run.errors_count,
            "pagesVisited": run.pages_visited,
            "paginationStopReason": run.pagination_stop_reason,
        },
        "items": items,
        "errors": [
            {"code": error.code, "message": error.message[:500]}
            for error in outcome.get("errors", [])
        ],
    }
    session.add(ScrapeRunPayload(scrape_run_id=run.id, payload_encrypted=encrypt_json(payload)))
    endpoint_ids = (
        session.execute(
            select(WebhookEndpoint.id)
            .outerjoin(
                WebhookEndpointSource, WebhookEndpointSource.endpoint_id == WebhookEndpoint.id
            )
            .where(
                WebhookEndpoint.enabled.is_(True),
                or_(
                    WebhookEndpoint.all_sources.is_(True),
                    WebhookEndpointSource.source_id == source.id,
                ),
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    deliveries = [WebhookDelivery(endpoint_id=item, scrape_run_id=run.id) for item in endpoint_ids]
    session.add_all(deliveries)
    session.flush()
    return [str(item.id) for item in deliveries]
