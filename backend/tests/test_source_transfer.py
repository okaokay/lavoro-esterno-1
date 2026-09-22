from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app import main
from app.api.v1.sources import export_sources, import_sources
from app.db import get_db
from app.models.audit_log import AuditLog
from app.models.proxies import ProxyPool
from app.models.sources import Source
from app.schemas.sources import (
    SourceExportRequest,
    SourceImportApplyRequest,
    SourceTransferDocument,
)
from app.security.deps import get_current_user
from app.services.source_transfer import preview_source_document


class _Scalars:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class _Result:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def scalars(self) -> _Scalars:
        return _Scalars(self.values)


class _FakeSession:
    def __init__(self, results: list[list[object]], *, fail_flush: bool = False) -> None:
        self.results = list(results)
        self.fail_flush = fail_flush
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _statement: object) -> _Result:
        return _Result(self.results.pop(0))

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        if self.fail_flush:
            raise IntegrityError("insert", {}, Exception("duplicate"))

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _item(slug: str, *, pool: str | None = None, name: str | None = None) -> dict:
    return {
        "name": name or slug,
        "slug": slug,
        "baseUrl": f"https://{slug}.example",
        "priority": "high",
        "scrapeConfig": {
            "startUrls": [f"https://{slug}.example/list"],
            "adLinkSelector": ".ad",
            "fields": {"phone": {"selector": ".phone", "attribute": "text"}},
        },
        "proxyPoolName": pool,
        "watermarkRemoval": {"enabled": False, "regions": []},
    }


def _document(*items: dict) -> SourceTransferDocument:
    return SourceTransferDocument.model_validate(
        {
            "format": "lavoro-esterno-sources",
            "version": 1,
            "exportedAt": "2026-09-10T12:00:00Z",
            "sources": list(items),
        }
    )


@pytest.mark.asyncio
async def test_preview_reports_conflicts_invalid_items_and_missing_pool() -> None:
    db = _FakeSession([["existing"], []])
    preview = await preview_source_document(
        db,  # type: ignore[arg-type]
        {
            "format": "lavoro-esterno-sources",
            "version": 1,
            "exportedAt": "2026-09-10T12:00:00Z",
            "sources": [_item("existing", pool="Mexico"), {"slug": "broken"}],
        },
    )

    assert preview.valid is False
    assert preview.entries[0].status == "conflict"
    assert preview.entries[0].proxy_pool_status == "missing"
    assert preview.entries[0].warnings
    assert preview.entries[1].status == "invalid"
    assert preview.entries[1].errors


@pytest.mark.asyncio
async def test_import_creates_disabled_source_and_preserves_existing_runtime_state() -> None:
    existing = Source(
        id=uuid.uuid4(),
        name="Old name",
        slug="existing",
        base_url="https://old.example",
        priority="low",
        status="healthy",
        enabled=True,
        automatic_scraping_enabled=True,
        scrape_interval_minutes=60,
        next_scrape_at=datetime.now(UTC),
    )
    untouched = Source(
        id=uuid.uuid4(),
        name="Keep me",
        slug="untouched",
        base_url="https://untouched.example",
        priority="medium",
        status="degraded",
        enabled=True,
    )
    pool = ProxyPool(id=uuid.uuid4(), name="Mexico", enabled=True)
    db = _FakeSession([[existing, untouched], [pool]])

    result = await import_sources(
        SourceImportApplyRequest(
            document=_document(
                _item("existing", pool="Missing", name="Updated"),
                _item("untouched", name="Must not be applied"),
                _item("new_source", pool="Mexico"),
            ),
            conflict_actions={"existing": "update", "untouched": "skip"},
        ),
        db=db,  # type: ignore[arg-type]
        user=SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
    )

    created = next(value for value in db.added if isinstance(value, Source))
    audit = next(value for value in db.added if isinstance(value, AuditLog))
    assert result.created == 1
    assert result.updated == 1
    assert result.skipped == 1
    assert result.warnings
    assert created.enabled is False
    assert created.status == "offline"
    assert created.automatic_scraping_enabled is False
    assert created.proxy_pool_id == pool.id
    assert existing.name == "Updated"
    assert existing.enabled is True
    assert existing.status == "healthy"
    assert existing.automatic_scraping_enabled is True
    assert existing.scrape_interval_minutes == 60
    assert existing.proxy_pool_id is None
    assert untouched.name == "Keep me"
    assert untouched.status == "degraded"
    assert audit.action == "import_sources"
    assert "scrapeConfig" not in str(audit.details_json)
    assert db.commits == 1


@pytest.mark.asyncio
async def test_import_requires_conflict_choice_and_rolls_back_concurrent_collision() -> None:
    existing = Source(id=uuid.uuid4(), name="Existing", slug="existing", base_url="https://x.test")
    with pytest.raises(HTTPException) as missing_action:
        await import_sources(
            SourceImportApplyRequest(document=_document(_item("existing"))),
            db=_FakeSession([[existing]]),  # type: ignore[arg-type]
            user=SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
        )
    assert missing_action.value.status_code == 422

    failing_db = _FakeSession([[]], fail_flush=True)
    with pytest.raises(HTTPException) as collision:
        await import_sources(
            SourceImportApplyRequest(document=_document(_item("new_source"))),
            db=failing_db,  # type: ignore[arg-type]
            user=SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
        )
    assert collision.value.status_code == 409
    assert failing_db.rollbacks == 1
    assert failing_db.commits == 0


@pytest.mark.asyncio
async def test_export_contains_portable_fields_only_and_audits() -> None:
    pool = ProxyPool(id=uuid.uuid4(), name="Mexico", enabled=True)
    source = Source(
        id=uuid.uuid4(),
        name="Source",
        slug="source",
        base_url="https://source.example",
        priority="medium",
        status="degraded",
        enabled=True,
        proxy_pool_id=pool.id,
        watermark_removal_enabled=False,
        watermark_regions=[],
    )
    db = _FakeSession([[source], [pool]])
    document = await export_sources(
        SourceExportRequest(scope="all"),
        db=db,  # type: ignore[arg-type]
        user=SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
    )

    exported = document.model_dump(mode="json", by_alias=True)["sources"][0]
    assert exported["proxyPoolName"] == "Mexico"
    assert set(exported) == {
        "name",
        "slug",
            "baseUrl",
            "countryCode",
            "priority",
        "scrapeConfig",
        "proxyPoolName",
        "watermarkRemoval",
    }
    assert any(
        isinstance(value, AuditLog) and value.action == "export_sources" for value in db.added
    )
    assert db.commits == 1


@pytest.mark.parametrize("role", ["viewer", "operator"])
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("export", {"scope": "all", "sourceIds": []}),
        ("import/preview", {"document": {}}),
        (
            "import",
            {
                "document": {
                    "format": "lavoro-esterno-sources",
                    "version": 1,
                    "exportedAt": "2026-09-10T12:00:00Z",
                    "sources": [_item("new_source")],
                },
                "conflictActions": {},
            },
        ),
    ],
)
def test_source_transfer_routes_are_admin_only(role: str, path: str, body: dict) -> None:
    async def fake_db():
        yield _FakeSession([])

    async def user() -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), role=role)

    main.app.dependency_overrides[get_db] = fake_db
    main.app.dependency_overrides[get_current_user] = user
    try:
        with TestClient(main.app) as client:
            response = client.post(f"/api/v1/sources/{path}", json=body)
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()
