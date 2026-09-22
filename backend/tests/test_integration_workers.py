"""Focused tests for webhook privacy and proxy-feed safe diagnostics."""

from app.workers.tasks_proxy_feeds import _safe_sync_error
from app.workers.tasks_webhooks import _apply_phone_policy, _safe_delivery_error


def test_phone_policies_are_applied_without_mutating_unrelated_fields() -> None:
    masked = {"items": [{"phone": "+39 333 123 4567", "title": "Titolo"}]}
    _apply_phone_policy(masked, "masked")
    assert masked["items"] == [{"phone": "***4567", "title": "Titolo"}]

    excluded = {"items": [{"phone_raw": "3331234567", "title": "Titolo"}]}
    _apply_phone_policy(excluded, "excluded")
    assert excluded["items"] == [{"title": "Titolo"}]


def test_transport_errors_do_not_persist_destination_urls() -> None:
    webhook_error = RuntimeError("ConnectError https://secret.example/path")
    feed_error = RuntimeError("GET https://feed.example/token returned 500")

    assert _safe_delivery_error(webhook_error) == "delivery_failed"
    assert _safe_sync_error(feed_error) == "feed_download_failed"
    assert _safe_delivery_error(RuntimeError("http_503")) == "http_503"
    assert _safe_sync_error(ValueError("feed_too_large")) == "feed_too_large"
