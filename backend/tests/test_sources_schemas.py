"""Test di validazione per gli schemi di configurazione delle fonti
(`app/schemas/sources.py`), in particolare `ScrapeConfigInput` — la
validazione qui è l'unica barriera prima che una configurazione venga
salvata su `Source.scrape_config` e usata da `GenericScraper` per
eseguire richieste HTTP reali (vedi PROGETTO.md § 4)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.sources import (
    ScrapeConfigInput,
    SourceCreate,
    SourceExportRequest,
    SourceTransferDocument,
)
from app.schemas.sources import TestConfigResult as ConfigTestResult

_VALID_FIELDS = {
    "phone": {"selector": ".phone", "attribute": "text"},
    "title": {"selector": ".title", "attribute": "text"},
}


def test_scrape_config_requires_phone_field() -> None:
    with pytest.raises(ValidationError, match="phone"):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields={"title": {"selector": ".title"}},
        )


def test_scrape_config_accepts_valid_input() -> None:
    config = ScrapeConfigInput(
        start_urls=["https://example.com/listing"],
        ad_link_selector=".ad",
        fields=_VALID_FIELDS,
    )
    assert config.max_pages == 3  # default
    assert config.rate_limit_seconds == 2.0  # default
    assert config.fetch_mode == "http"
    assert config.fields["phone"].extraction_mode == "value"
    assert config.max_pages_enabled is True
    assert config.max_ads_per_run_enabled is True


def test_new_limit_flags_accept_disabled_unbounded_mode() -> None:
    config = ScrapeConfigInput.model_validate(
        {
            "startUrls": ["https://example.com/listing"],
            "adLinkSelector": ".ad",
            "fields": _VALID_FIELDS,
            "maxPagesEnabled": False,
            "maxAdsPerRunEnabled": False,
        }
    )

    assert config.max_pages_enabled is False
    assert config.max_ads_per_run_enabled is False
    dumped = config.model_dump(by_alias=True)
    assert dumped["maxPagesEnabled"] is False
    assert dumped["maxAdsPerRunEnabled"] is False


def test_scrape_config_accepts_key_value_field() -> None:
    config = ScrapeConfigInput(
        start_urls=["https://example.com/listing"],
        ad_link_selector=".ad",
        fields={
            **_VALID_FIELDS,
            "details": {
                "extractionMode": "keyValue",
                "containerSelector": ".detail",
                "keySelector": ".key",
                "valueSelector": ".value",
            },
        },
    )

    assert config.fields["details"].container_selector == ".detail"


def test_scrape_config_rejects_incomplete_key_value_field() -> None:
    with pytest.raises(ValidationError, match="keySelector.*valueSelector"):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields={
                **_VALID_FIELDS,
                "details": {
                    "extractionMode": "keyValue",
                    "containerSelector": ".detail",
                },
            },
        )


def test_scrape_config_accepts_poster_video_field() -> None:
    config = ScrapeConfigInput(
        start_urls=["https://example.com/listing"],
        ad_link_selector=".ad",
        fields={
            **_VALID_FIELDS,
            "clips": {
                "extractionMode": "posterVideo",
                "containerSelector": ".clip",
                "posterSelector": "img",
                "posterAttribute": "src",
                "videoSelector": "a",
                "videoAttribute": "href",
            },
        },
    )

    assert config.fields["clips"].extraction_mode == "posterVideo"


def test_scrape_config_accepts_structured_paginated_items() -> None:
    config = ScrapeConfigInput.model_validate(
        {
            "startUrls": ["https://example.com/listing"],
            "adLinkSelector": ".ad",
            "fetchMode": "dynamic",
            "fields": {
                **_VALID_FIELDS,
                "reviews": {
                    "extractionMode": "items",
                    "multiple": True,
                    "containerSelector": ".review",
                    "itemFields": {
                        "author": {"selector": ".author", "attribute": "text"},
                        "rating": {"selector": ".rating", "attribute": "text"},
                    },
                    "pagination": {"nextSelector": "button.more"},
                },
            },
        }
    )

    reviews = config.fields["reviews"]
    assert reviews.item_fields["author"].selector == ".author"
    assert reviews.pagination is not None
    assert reviews.pagination.max_pages == 10
    assert reviews.pagination.max_items == 1000
    assert (
        config.model_dump(by_alias=True)["fields"]["reviews"]["pagination"]["nextSelector"]
        == "button.more"
    )


def test_scrape_config_supports_mixed_css_and_xpath_selector_types() -> None:
    config = ScrapeConfigInput.model_validate(
        {
            "startUrls": ["https://example.com/list"],
            "adLinkSelector": "//article//a",
            "adLinkSelectorType": "xpath",
            "nextPageSelector": "a.next",
            "nextPageSelectorType": "css",
            "fetchMode": "dynamic",
            "waitSelector": "//*[@data-loaded]",
            "waitSelectorType": "xpath",
            "fields": {
                "phone": {
                    "selector": "//span[@data-phone]",
                    "selectorType": "xpath",
                },
                "reviews": {
                    "extractionMode": "items",
                    "multiple": True,
                    "containerSelector": "//article[@class='review']",
                    "containerSelectorType": "xpath",
                    "itemFields": {
                        "text": {
                            "selector": ".//p",
                            "selectorType": "xpath",
                        }
                    },
                    "pagination": {
                        "nextSelector": "//button[@aria-label='Next']",
                        "nextSelectorType": "xpath",
                    },
                },
            },
        }
    )

    dumped = config.model_dump(mode="json", by_alias=True)
    assert dumped["adLinkSelectorType"] == "xpath"
    assert dumped["nextPageSelectorType"] == "css"
    assert dumped["waitSelectorType"] == "xpath"
    assert dumped["fields"]["phone"]["selectorType"] == "xpath"
    assert dumped["fields"]["reviews"]["containerSelectorType"] == "xpath"
    assert dumped["fields"]["reviews"]["itemFields"]["text"]["selectorType"] == "xpath"
    assert dumped["fields"]["reviews"]["pagination"]["nextSelectorType"] == "xpath"


def test_scrape_config_defaults_legacy_selectors_to_css_and_rejects_unknown_type() -> None:
    config = ScrapeConfigInput(
        start_urls=["https://example.com/list"],
        ad_link_selector="a.ad",
        fields={"phone": {"selector": ".phone"}},
    )
    assert config.ad_link_selector_type == "css"
    assert config.next_page_selector_type == "css"
    assert config.wait_selector_type == "css"
    assert config.fields["phone"].selector_type == "css"

    with pytest.raises(ValidationError):
        ScrapeConfigInput.model_validate(
            {
                "startUrls": ["https://example.com/list"],
                "adLinkSelector": "//a",
                "adLinkSelectorType": "xquery",
                "fields": {"phone": {"selector": ".phone"}},
            }
        )


def test_scrape_config_rejects_field_pagination_in_http_mode() -> None:
    with pytest.raises(ValidationError, match="dynamic.*stealth"):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields={
                **_VALID_FIELDS,
                "comments": {
                    "selector": ".comment",
                    "multiple": True,
                    "pagination": {"nextSelector": "button.more"},
                },
            },
        )


def test_scrape_config_rejects_paginated_scalar_and_invalid_limits() -> None:
    with pytest.raises(ValidationError, match="multiple=true"):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fetch_mode="dynamic",
            fields={
                **_VALID_FIELDS,
                "comments": {
                    "selector": ".comment",
                    "pagination": {"nextSelector": "button.more"},
                },
            },
        )
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fetch_mode="dynamic",
            fields={
                **_VALID_FIELDS,
                "comments": {
                    "selector": ".comment",
                    "multiple": True,
                    "pagination": {
                        "nextSelector": "button.more",
                        "maxPages": 51,
                        "maxItems": 5001,
                    },
                },
            },
        )


def test_scrape_config_rejects_items_for_standard_field() -> None:
    with pytest.raises(ValidationError, match="campo standard 'phone'"):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fetch_mode="dynamic",
            fields={
                "phone": {
                    "extractionMode": "items",
                    "multiple": True,
                    "containerSelector": ".phone",
                    "itemFields": {"value": {"selector": ".value"}},
                }
            },
        )


def test_scrape_config_rejects_pagination_for_scalar_standard_field() -> None:
    with pytest.raises(ValidationError, match="standard scalare 'phone'"):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fetch_mode="dynamic",
            fields={
                "phone": {
                    "selector": ".phone",
                    "multiple": True,
                    "pagination": {"nextSelector": "button.more"},
                }
            },
        )


def test_test_config_result_serializes_field_pagination_diagnostics() -> None:
    result = ConfigTestResult(
        ad_urls_found=1,
        field_pagination={
            "reviews": {
                "pages_visited": 3,
                "items_collected": 24,
                "pagination_mode": "click",
                "stop_reason": "end_of_pagination",
                "complete": True,
            }
        },
    )

    assert result.model_dump(by_alias=True)["fieldPagination"]["reviews"] == {
        "pagesVisited": 3,
        "itemsCollected": 24,
        "paginationMode": "click",
        "stopReason": "end_of_pagination",
        "complete": True,
    }


def test_scrape_config_rejects_invalid_poster_video_attribute() -> None:
    with pytest.raises(ValidationError, match="posterAttribute"):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields={
                **_VALID_FIELDS,
                "clips": {
                    "extractionMode": "posterVideo",
                    "containerSelector": ".clip",
                    "posterSelector": "img",
                    "posterAttribute": "alt",
                    "videoSelector": "video",
                    "videoAttribute": "src",
                },
            },
        )


def test_scrape_config_rejects_singular_image_field() -> None:
    with pytest.raises(ValidationError, match="images.*plurale"):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields={
                **_VALID_FIELDS,
                "image": {"selector": "img", "attribute": "src", "multiple": True},
            },
        )


@pytest.mark.parametrize(
    "media_field",
    [
        {"selector": "img", "attribute": "src", "multiple": False},
        {"selector": "img", "attribute": "text", "multiple": True},
    ],
)
def test_scrape_config_rejects_invalid_media_field(media_field: dict) -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields={**_VALID_FIELDS, "images": media_field},
        )


def test_scrape_config_maps_legacy_render_js_to_dynamic_fetch_mode() -> None:
    config = ScrapeConfigInput(
        start_urls=["https://example.com/listing"],
        ad_link_selector=".ad",
        fields=_VALID_FIELDS,
        render_js=True,
    )

    assert config.fetch_mode == "dynamic"


def test_scrape_config_accepts_stealth_options() -> None:
    config = ScrapeConfigInput(
        start_urls=["https://example.com/listing"],
        ad_link_selector=".ad",
        fields=_VALID_FIELDS,
        fetch_mode="stealth",
        solve_cloudflare=True,
        block_webrtc=True,
        hide_canvas=True,
        real_chrome=True,
        block_ads=True,
        wait_selector=".loaded",
        wait_ms=500,
    )

    assert config.fetch_mode == "stealth"
    assert config.solve_cloudflare is True
    assert config.wait_selector == ".loaded"
    assert config.wait_ms == 500


def test_scrape_config_rejects_invalid_fetch_mode() -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
            fetch_mode="invalid",
        )


def test_scrape_config_rejects_legacy_inline_proxy() -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
            proxy="http://proxy.example:8080",
        )


def test_scrape_config_accepts_optional_user_agent() -> None:
    config = ScrapeConfigInput(
        start_urls=["https://example.com/listing"],
        ad_link_selector=".ad",
        fields=_VALID_FIELDS,
        user_agent="  CustomScraper/2.0  ",
    )

    assert config.user_agent == "CustomScraper/2.0"


def test_scrape_config_rejects_blank_user_agent() -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
            user_agent="   ",
        )


def test_scrape_config_rejects_non_http_start_url() -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["ftp://example.com/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
        )


def test_scrape_config_rejects_relative_start_url() -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
        )


def test_scrape_config_rate_limit_has_a_safety_floor() -> None:
    """Il rate limit non è disattivabile dalla configurazione (vedi
    PROGETTO.md § 4): un operatore non può azzerare la pausa tra le
    richieste, solo aumentarla."""
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
            rate_limit_seconds=0,
        )


def test_scrape_config_caps_max_pages_and_max_ads() -> None:
    with pytest.raises(ValidationError):
        ScrapeConfigInput(
            start_urls=["https://example.com/listing"],
            ad_link_selector=".ad",
            fields=_VALID_FIELDS,
            max_pages=1000,
        )


def test_source_create_rejects_invalid_slug_characters() -> None:
    with pytest.raises(ValidationError):
        SourceCreate(
            name="Test Source",
            slug="Not A Valid Slug!",
            base_url="https://example.com",
        )


def test_source_create_accepts_valid_slug_without_scrape_config() -> None:
    source = SourceCreate(name="Test Source", slug="test_source", base_url="https://example.com")
    assert source.scrape_config is None
    assert source.priority == "medium"


def test_source_transfer_document_round_trip_uses_versioned_camel_case_format() -> None:
    document = SourceTransferDocument.model_validate(
        {
            "format": "lavoro-esterno-sources",
            "version": 1,
            "exportedAt": "2026-09-10T12:00:00Z",
            "sources": [
                {
                    "name": "Test Source",
                    "slug": "test_source",
                    "baseUrl": "https://example.com",
                    "priority": "high",
                    "scrapeConfig": None,
                    "proxyPoolName": "Mexico",
                    "watermarkRemoval": {"enabled": False, "regions": []},
                }
            ],
        }
    )

    serialized = document.model_dump(mode="json", by_alias=True)
    assert serialized["format"] == "lavoro-esterno-sources"
    assert serialized["version"] == 1
    assert serialized["sources"][0]["baseUrl"] == "https://example.com"
    assert serialized["sources"][0]["proxyPoolName"] == "Mexico"
    assert "enabled" not in serialized["sources"][0]
    assert "id" not in serialized["sources"][0]


def test_source_transfer_preserves_paginated_structured_fields() -> None:
    document = SourceTransferDocument.model_validate(
        {
            "format": "lavoro-esterno-sources",
            "version": 1,
            "exportedAt": "2026-09-14T12:00:00Z",
            "sources": [
                {
                    "name": "Reviews",
                    "slug": "reviews",
                    "baseUrl": "https://example.com",
                    "scrapeConfig": {
                        "startUrls": ["https://example.com/list"],
                        "adLinkSelector": "//a[contains(@class, 'ad')]",
                        "adLinkSelectorType": "xpath",
                        "fetchMode": "dynamic",
                        "fields": {
                            "phone": {"selector": ".phone"},
                            "reviews": {
                                "extractionMode": "items",
                                "multiple": True,
                                "containerSelector": "//article[@class='review']",
                                "containerSelectorType": "xpath",
                                "itemFields": {"text": {"selector": ".text"}},
                                "pagination": {
                                    "nextSelector": "//button[@class='more']",
                                    "nextSelectorType": "xpath",
                                },
                            },
                        },
                    },
                }
            ],
        }
    )

    reviews = document.model_dump(mode="json", by_alias=True)["sources"][0]["scrapeConfig"][
        "fields"
    ]["reviews"]
    assert reviews["itemFields"]["text"]["selector"] == ".text"
    assert reviews["containerSelectorType"] == "xpath"
    assert reviews["pagination"] == {
        "nextSelector": "//button[@class='more']",
        "nextSelectorType": "xpath",
        "maxPages": 10,
        "maxItems": 1000,
    }


def test_source_transfer_document_rejects_duplicate_slugs_and_unknown_version() -> None:
    source = {
        "name": "Test Source",
        "slug": "test_source",
        "baseUrl": "https://example.com",
    }
    with pytest.raises(ValidationError, match="slug duplicati"):
        SourceTransferDocument(
            format="lavoro-esterno-sources",
            version=1,
            exported_at="2026-09-10T12:00:00Z",
            sources=[source, source],
        )
    with pytest.raises(ValidationError):
        SourceTransferDocument(
            format="lavoro-esterno-sources",
            version=2,
            exported_at="2026-09-10T12:00:00Z",
            sources=[source],
        )


def test_source_export_request_requires_ids_only_for_selected_scope() -> None:
    with pytest.raises(ValidationError):
        SourceExportRequest(scope="selected", source_ids=[])
    with pytest.raises(ValidationError):
        SourceExportRequest(scope="all", source_ids=["00000000-0000-0000-0000-000000000001"])
