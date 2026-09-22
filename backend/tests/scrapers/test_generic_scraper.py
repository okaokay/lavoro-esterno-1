"""Test del motore di scraping generico (`app/scrapers/generic.py`) contro
fixture HTML sintetiche servite da un server HTTP locale
(`tests/scrapers/conftest.py`) — nessuna richiesta verso siti reali.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from scrapling.parser import Selector

from app.scrapers.base import Scraper
from app.scrapers.generic import AntiBotBlockedError, GenericScraper, RobotsDisallowedError

_BASE_CONFIG = {
    "ad_link_selector": "a.ad-link",
    "next_page_selector": "a.next",
    "max_pages": 5,
    "max_ads_per_run": 50,
    "rate_limit_seconds": 0,  # test rapidi: la validazione min=1.0 vive solo nello schema API
    "fields": {
        "title": {"selector": "h1.ad-title", "attribute": "text"},
        "description": {"selector": "p.ad-description", "attribute": "text"},
        "phone": {"selector": "span.ad-phone", "attribute": "text"},
        "images": {"selector": "div.ad-gallery img", "attribute": "src", "multiple": True},
    },
}


def _scraper(base_url: str, **overrides) -> GenericScraper:
    config = {**_BASE_CONFIG, "start_urls": [f"{base_url}/listing.html"], **overrides}
    return GenericScraper(slug="test_source", base_url=base_url, config=config)


@pytest.fixture
def user_agent_site_url() -> Iterator[tuple[str, list[tuple[str, str | None]]]]:
    requests: list[tuple[str, str | None]] = []

    class RecordingHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append((self.path, self.headers.get("User-Agent")))
            if self.path == "/robots.txt":
                body = b"User-agent: *\nAllow: /\n"
            elif self.path == "/listing.html":
                body = b'<html><body><a class="ad-link" href="/ad1.html">Ad 1</a></body></html>'
            else:
                body = b"<html><body></body></html>"

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, message_format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}", requests
    finally:
        server.shutdown()


def test_user_agent_falls_back_to_scraper_default(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)

    assert scraper.user_agent == Scraper.user_agent


@pytest.mark.parametrize(
    ("configured_user_agent", "expected_user_agent"),
    [(None, None), ("CustomBrowser/1.0", "CustomBrowser/1.0")],
)
async def test_browser_session_is_reused_and_only_receives_explicit_user_agent(
    monkeypatch: pytest.MonkeyPatch,
    open_site_url: str,
    configured_user_agent: str | None,
    expected_user_agent: str | None,
) -> None:
    sessions: list[object] = []

    class FakeSession:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.started = False
            self.closed = False
            self.fetches: list[str] = []
            sessions.append(self)

        async def start(self) -> None:
            self.started = True

        async def fetch(self, url: str, **_kwargs):
            self.fetches.append(url)
            return SimpleNamespace(status=200, headers={}, html_content="<html></html>")

        async def close(self) -> None:
            self.closed = True

    monkeypatch.setattr("scrapling.fetchers.AsyncStealthySession", FakeSession)
    options = {"fetch_mode": "stealth"}
    if configured_user_agent is not None:
        options["user_agent"] = configured_user_agent
    scraper = _scraper(open_site_url, **options)

    await scraper._fetch_page_stealth(f"{open_site_url}/one")
    await scraper._fetch_page_stealth(f"{open_site_url}/two")
    await scraper.aclose()

    assert len(sessions) == 1
    session = sessions[0]
    assert session.started is True
    assert session.fetches == [f"{open_site_url}/one", f"{open_site_url}/two"]
    assert session.kwargs.get("useragent") == expected_user_agent
    assert session.closed is True


def test_cloudflare_interstitial_with_success_status_is_blocked(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)
    response = SimpleNamespace(
        status=200,
        headers={"server": "cloudflare"},
        html_content=(
            "<html><head><title>Just a moment...</title></head>"
            '<body><form id="challenge-form"><script src="/cdn-cgi/challenge-platform/x">'
            "</script></form></body></html>"
        ),
    )

    with pytest.raises(AntiBotBlockedError) as error:
        scraper._raise_for_status(response, f"{open_site_url}/listing")

    assert error.value.http_status == 200


def test_cloudflare_403_is_classified_as_anti_bot_block(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)
    response = SimpleNamespace(
        status=403,
        headers={"cf-ray": "test"},
        html_content="<html><body>Forbidden</body></html>",
    )

    with pytest.raises(AntiBotBlockedError) as error:
        scraper._raise_for_status(response, f"{open_site_url}/listing")

    assert error.value.http_status == 403


def test_regular_page_with_turnstile_widget_is_not_false_positive(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)
    response = SimpleNamespace(
        status=200,
        headers={"server": "cloudflare"},
        html_content=(
            '<html><head><title>Contact</title></head><body><div class="cf-turnstile"></div>'
            '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>'
            "</body></html>"
        ),
    )

    scraper._raise_for_status(response, f"{open_site_url}/contact")


async def test_custom_user_agent_is_sent_in_http_requests(
    user_agent_site_url: tuple[str, list[tuple[str, str | None]]],
) -> None:
    base_url, requests = user_agent_site_url
    scraper = _scraper(base_url, user_agent="CustomScraper/2.0")
    try:
        await scraper.discover()
    finally:
        await scraper.aclose()

    assert ("/listing.html", "CustomScraper/2.0") in requests


async def test_custom_user_agent_is_used_for_robots_check(
    monkeypatch: pytest.MonkeyPatch, open_site_url: str
) -> None:
    seen_user_agents: list[str] = []

    def fake_is_allowed(robots_txt: str | None, url: str, user_agent: str) -> bool:
        seen_user_agents.append(user_agent)
        return True

    monkeypatch.setattr("app.services.robots_check.is_allowed", fake_is_allowed)
    scraper = _scraper(open_site_url, user_agent="RobotsCheckAgent/3.0")

    try:
        await scraper.discover()
    finally:
        await scraper.aclose()

    assert seen_user_agents
    assert all(user_agent == "RobotsCheckAgent/3.0" for user_agent in seen_user_agents)


async def test_legacy_render_js_routes_to_dynamic_fetcher(
    monkeypatch: pytest.MonkeyPatch, open_site_url: str
) -> None:
    calls: list[str] = []
    scraper = _scraper(open_site_url, render_js=True)

    async def skip_robots() -> None:
        return None

    async def fake_dynamic(url: str):
        calls.append(url)
        raise RuntimeError("stop after routing")

    monkeypatch.setattr(scraper, "_ensure_robots_loaded", skip_robots)
    monkeypatch.setattr("app.services.robots_check.is_allowed", lambda *args: True)
    monkeypatch.setattr(scraper, "_fetch_page_dynamic", fake_dynamic)

    with pytest.raises(Exception, match="stop after routing"):
        await scraper._fetch_page(f"{open_site_url}/listing.html")

    assert scraper.fetch_mode == "dynamic"
    assert calls == [f"{open_site_url}/listing.html"]


async def test_fetch_mode_stealth_routes_to_stealth_fetcher(
    monkeypatch: pytest.MonkeyPatch, open_site_url: str
) -> None:
    calls: list[str] = []
    scraper = _scraper(open_site_url, fetch_mode="stealth")

    async def skip_robots() -> None:
        return None

    async def fake_stealth(url: str):
        calls.append(url)
        raise RuntimeError("stop after routing")

    monkeypatch.setattr(scraper, "_ensure_robots_loaded", skip_robots)
    monkeypatch.setattr("app.services.robots_check.is_allowed", lambda *args: True)
    monkeypatch.setattr(scraper, "_fetch_page_stealth", fake_stealth)

    with pytest.raises(Exception, match="stop after routing"):
        await scraper._fetch_page(f"{open_site_url}/listing.html")

    assert calls == [f"{open_site_url}/listing.html"]


async def test_discover_follows_pagination_and_collects_all_ad_links(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)
    urls = await scraper.discover()

    assert len(urls) == 3
    assert urls[0].endswith("/ad1.html")
    assert urls[1].endswith("/ad2.html")
    assert urls[2].endswith("/ad3.html")  # dalla pagina 2, raggiunta via next_page_selector


async def test_http_discovery_supports_xpath_for_ads_and_pagination(
    open_site_url: str,
) -> None:
    scraper = _scraper(
        open_site_url,
        ad_link_selector="//a[contains(@class, 'ad-link')]",
        ad_link_selector_type="xpath",
        next_page_selector="//a[contains(@class, 'next')]",
        next_page_selector_type="xpath",
    )

    urls = await scraper.discover()

    assert [url.rsplit("/", 1)[-1] for url in urls] == [
        "ad1.html",
        "ad2.html",
        "ad3.html",
    ]
    assert scraper.discovery_diagnostics.pages_visited == 2


async def test_http_discover_accepts_duplicate_next_links_with_equivalent_targets(
    open_site_url: str,
) -> None:
    scraper = _scraper(open_site_url, max_pages=3)
    page_two_url = f"{open_site_url}/listing.html?page=2"
    pages = {
        f"{open_site_url}/listing.html": Selector(
            '<a class="ad-link" href="/ad1.html">Ad 1</a>'
            '<a class="next" href="?page=2#top">Next</a>'
            f'<a class="next" href="{page_two_url}#bottom">Next</a>'
        ),
        page_two_url: Selector('<a class="ad-link" href="/ad2.html">Ad 2</a>'),
    }

    async def fake_fetch(url: str):
        return pages[url]

    scraper._fetch_page = fake_fetch  # type: ignore[method-assign]
    urls = await scraper.discover()

    assert urls == [f"{open_site_url}/ad1.html", f"{open_site_url}/ad2.html"]
    assert scraper.discovery_diagnostics.pages_visited == 2
    assert scraper.discovery_diagnostics.stop_reason == "end_of_pagination"
    assert scraper.discovery_diagnostics.errors == []


def test_equivalent_next_url_rejects_different_mixed_or_javascript_controls(
    open_site_url: str,
) -> None:
    current_url = f"{open_site_url}/listing.html"

    assert GenericScraper._equivalent_next_url(current_url, ["?page=2", "?page=3"], 2) is None
    assert GenericScraper._equivalent_next_url(current_url, ["?page=2", None], 2) is None
    assert GenericScraper._equivalent_next_url(current_url, [None, None], 2) is None


async def test_discover_stops_at_max_pages(open_site_url: str) -> None:
    scraper = _scraper(open_site_url, max_pages=1)
    urls = await scraper.discover()

    # Solo la prima pagina: i 2 annunci lì elencati, non il terzo (pagina 2).
    assert len(urls) == 2
    assert scraper.discovery_diagnostics.pages_visited == 1
    assert scraper.discovery_diagnostics.stop_reason == "max_pages"
    assert scraper.discovery_diagnostics.warnings


async def test_discover_rejects_ambiguous_next_selector(open_site_url: str) -> None:
    scraper = _scraper(open_site_url, next_page_selector="a", max_pages=2)
    urls = await scraper.discover()

    assert len(urls) == 2
    assert scraper.discovery_diagnostics.stop_reason == "ambiguous_next_control"
    assert scraper.discovery_diagnostics.errors == [
        "Il selettore di paginazione ha trovato controlli Next non equivalenti: "
        "le corrispondenze multiple sono ammesse solo se tutti gli href portano "
        "alla stessa destinazione."
    ]


async def test_discover_stops_when_next_href_repeats_page(open_site_url: str) -> None:
    scraper = _scraper(open_site_url, next_page_selector="a.self", max_pages=3)
    pages = {
        f"{open_site_url}/listing.html": Selector(
            '<a class="ad-link" href="/ad1.html">Ad</a>'
            '<a class="self" href="/listing.html">Next</a>'
        )
    }

    async def fake_fetch(url: str):
        return pages[url]

    scraper._fetch_page = fake_fetch  # type: ignore[method-assign]
    urls = await scraper.discover()

    assert len(urls) == 1
    assert scraper.discovery_diagnostics.pages_visited == 1
    assert scraper.discovery_diagnostics.stop_reason == "repeated_page"


async def test_discover_blocks_cross_origin_pagination(open_site_url: str) -> None:
    scraper = _scraper(open_site_url, next_page_selector="a.external", max_pages=3)
    page = Selector(
        '<a class="ad-link" href="/ad1.html">Ad</a>'
        '<a class="external" href="https://other.example/page/2">Next</a>'
    )

    async def fake_fetch(_url: str):
        return page

    scraper._fetch_page = fake_fetch  # type: ignore[method-assign]
    urls = await scraper.discover()

    assert len(urls) == 1
    assert scraper.discovery_diagnostics.stop_reason == "cross_origin_blocked"
    assert scraper.discovery_diagnostics.errors


async def test_discover_deduplicates_ads_across_multiple_start_urls(open_site_url: str) -> None:
    second_start = f"{open_site_url}/other-listing.html"
    scraper = _scraper(
        open_site_url,
        start_urls=[f"{open_site_url}/listing.html", second_start],
        next_page_selector=None,
    )
    page = Selector('<a class="ad-link" href="/same-ad.html">Ad</a>')

    async def fake_fetch(_url: str):
        return page

    scraper._fetch_page = fake_fetch  # type: ignore[method-assign]
    urls = await scraper.discover()

    assert urls == [f"{open_site_url}/same-ad.html"]
    assert scraper.discovery_diagnostics.pages_visited == 2
    assert scraper.discovery_diagnostics.unique_ads_found == 1


async def test_discover_stops_at_max_ads_per_run(open_site_url: str) -> None:
    scraper = _scraper(open_site_url, max_ads_per_run=1)
    urls = await scraper.discover()

    assert len(urls) == 1


async def test_scrape_ad_extracts_configured_fields(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)
    raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")

    assert raw["title"] == "Synthetic Ad One"
    assert raw["description"] == "This is a synthetic test fixture, not real content."
    assert raw["phone"] == "+39 333 111 1111"
    assert raw["images"] == ["/img1.jpg", "/img2.jpg"]


async def test_scrape_ad_extracts_text_and_attributes_with_xpath(open_site_url: str) -> None:
    scraper = _scraper(
        open_site_url,
        fields={
            "phone": {
                "selector": "//span[contains(@class, 'ad-phone')]",
                "selectorType": "xpath",
                "attribute": "text",
            },
            "images": {
                "selector": "//div[contains(@class, 'ad-gallery')]//img",
                "selectorType": "xpath",
                "attribute": "src",
                "multiple": True,
            },
        },
    )

    raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")

    assert raw["phone"] == "+39 333 111 1111"
    assert raw["images"] == ["/img1.jpg", "/img2.jpg"]


@pytest.mark.parametrize(
    ("raw_key", "expected"),
    [
        ("Età", "eta"),
        ("ETA", "eta"),
        ("age", "eta"),
        ("Tipo annuncio", "tipo_annuncio"),
    ],
)
def test_key_value_keys_are_normalized(raw_key: str, expected: str) -> None:
    assert GenericScraper.normalize_pair_key(raw_key) == expected


async def test_scrape_ad_extracts_key_value_pairs(open_site_url: str) -> None:
    fields = {
        **_BASE_CONFIG["fields"],
        "details": {
            "extractionMode": "keyValue",
            "containerSelector": ".ad-details .detail",
            "keySelector": "dt",
            "keyAttribute": "text",
            "valueSelector": "dd",
            "valueAttribute": "text",
        },
    }
    scraper = _scraper(open_site_url, fields=fields)

    raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")

    assert raw["details"] == {"eta": "26", "tipo_annuncio": "Privato"}
    assert scraper.normalize(raw)["custom_fields"]["details"] == raw["details"]


async def test_scrape_ad_extracts_poster_video_pairs(open_site_url: str) -> None:
    fields = {
        **_BASE_CONFIG["fields"],
        "clips": {
            "extractionMode": "posterVideo",
            "containerSelector": ".media-pair",
            "posterSelector": "img",
            "posterAttribute": "src",
            "videoSelector": ".video, video",
            "videoAttribute": "src",
        },
    }
    scraper = _scraper(open_site_url, fields=fields)

    raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")

    assert raw["clips"] == [
        {"poster": "/poster1.jpg", "video": "/video1.mp4"},
        {"poster": "/poster2.jpg", "video": "/video2.mp4"},
    ]


def test_text_extraction_preserves_br_and_inline_content() -> None:
    page = Selector(
        """
        <p class="description">
          Prima riga<br>
          Seconda <strong>riga</strong><br><br>
          Ultima <span>riga</span><script>ignored()</script>
        </p>
        """
    )
    scraper = _scraper("https://example.test")

    value = scraper._extract_field(page, {"selector": "p.description", "attribute": "text"})

    assert value == "Prima riga\nSeconda riga\n\nUltima riga"


def test_text_extraction_returns_one_complete_value_per_selected_element() -> None:
    page = Selector(
        """
        <div>
          <p class="note">Prima<br>nota</p>
          <p class="note">Seconda <a href="#">nota</a></p>
        </div>
        """
    )
    scraper = _scraper("https://example.test")
    spec = {"selector": "p.note", "attribute": "text"}

    assert scraper._extract_field(page, spec) == "Prima\nnota"
    assert scraper._extract_field(page, {**spec, "multiple": True}) == [
        "Prima\nnota",
        "Seconda nota",
    ]


def test_structured_items_extract_scalar_subfields_and_skip_empty_items() -> None:
    page = Selector(
        """
        <article class="review"><b class="author">Ada</b><span class="rating">5</span></article>
        <article class="review"><b class="author">Lin</b></article>
        <article class="review"><span class="unused">vuoto</span></article>
        """
    )
    scraper = _scraper("https://example.com")

    assert scraper._extract_field(
        page,
        {
            "extractionMode": "items",
            "containerSelector": ".review",
            "itemFields": {
                "author": {"selector": ".author", "attribute": "text"},
                "rating": {"selector": ".rating", "attribute": "text"},
            },
        },
    ) == [{"author": "Ada", "rating": "5"}, {"author": "Lin"}]


def test_structured_modes_support_relative_xpath_selectors() -> None:
    page = Selector(
        """
        <section class="detail"><dt>Età</dt><dd>26</dd></section>
        <section class="clip"><img src="/poster.jpg"><video src="/video.mp4"></video></section>
        <article class="review"><b>Ada</b><p>Ottima</p></article>
        """
    )
    scraper = _scraper("https://example.com")

    assert scraper._extract_field(
        page,
        {
            "extractionMode": "keyValue",
            "containerSelector": "//section[@class='detail']",
            "containerSelectorType": "xpath",
            "keySelector": ".//dt",
            "keySelectorType": "xpath",
            "valueSelector": ".//dd",
            "valueSelectorType": "xpath",
        },
    ) == {"eta": "26"}
    assert scraper._extract_field(
        page,
        {
            "extractionMode": "posterVideo",
            "containerSelector": "//section[@class='clip']",
            "containerSelectorType": "xpath",
            "posterSelector": ".//img",
            "posterSelectorType": "xpath",
            "posterAttribute": "src",
            "videoSelector": ".//video",
            "videoSelectorType": "xpath",
            "videoAttribute": "src",
        },
    ) == [{"poster": "/poster.jpg", "video": "/video.mp4"}]
    assert scraper._extract_field(
        page,
        {
            "extractionMode": "items",
            "containerSelector": "//article[@class='review']",
            "containerSelectorType": "xpath",
            "itemFields": {
                "author": {"selector": ".//b", "selectorType": "xpath"},
                "text": {"selector": ".//p", "selectorType": "xpath"},
            },
        },
    ) == [{"author": "Ada", "text": "Ottima"}]


def test_xpath_wait_selector_is_encoded_for_the_browser() -> None:
    scraper = _scraper(
        "https://example.com",
        fetch_mode="dynamic",
        wait_selector="//*[@data-loaded]",
        wait_selector_type="xpath",
    )

    assert scraper._browser_request_kwargs()["wait_selector"] == "xpath=//*[@data-loaded]"


def test_paginated_merge_deduplicates_lists_and_keeps_first_key_value() -> None:
    merged, reached = GenericScraper._merge_paginated_value(["a", "b"], ["b", "c", "d"], "value", 3)
    assert merged == ["a", "b", "c"]
    assert reached is True

    pairs, reached = GenericScraper._merge_paginated_value(
        {"city": "Roma"}, {"city": "Milano", "age": "30"}, "keyValue", 10
    )
    assert pairs == {"city": "Roma", "age": "30"}
    assert reached is False


@pytest.mark.parametrize(
    ("selector", "attribute"),
    [
        ("img.full-image", "src"),
        ("a:has(img.full-image)", "href"),
    ],
)
async def test_scrape_ad_extracts_thumbnail_or_original_image_urls(
    open_site_url: str, selector: str, attribute: str
) -> None:
    fields = {
        **_BASE_CONFIG["fields"],
        "images": {"selector": selector, "attribute": attribute, "multiple": True},
    }
    scraper = _scraper(open_site_url, fields=fields)

    raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")

    assert raw["images"] == ["/img1.jpg", "/img2.jpg"]


async def test_normalize_maps_raw_fields_to_common_shape(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)
    raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")
    normalized = scraper.normalize(raw)

    assert normalized["title"] == "Synthetic Ad One"
    assert normalized["phone_raw"] == "+39 333 111 1111"
    assert normalized["images"] == ["/img1.jpg", "/img2.jpg"]


async def test_ad_without_phone_has_no_phone_raw(open_site_url: str) -> None:
    """ad3.html non ha un campo telefono: verifica che il motore non
    inventi nulla, lasciando alla pipeline di ingestione la decisione di
    scartare l'annuncio (vedi app/services/scrape_ingest.py:collect_ads)."""
    scraper = _scraper(open_site_url)
    raw = await scraper.scrape_ad(f"{open_site_url}/ad3.html")
    normalized = scraper.normalize(raw)

    assert normalized["phone_raw"] is None


async def test_download_media_fetches_real_bytes_and_sniffs_as_jpeg(open_site_url: str) -> None:
    from app.services.media_storage import sniff_mime_type

    scraper = _scraper(open_site_url)
    raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")
    normalized = scraper.normalize(raw)

    media = await scraper.download_media(normalized)

    assert media.attempted_count == 2
    assert media.failed_count == 0
    assert len(media.media_bytes) == 2
    assert all(sniff_mime_type(blob) == "image/jpeg" for blob in media.media_bytes)


async def test_download_media_reports_failure_without_exposing_media_url(
    monkeypatch: pytest.MonkeyPatch, open_site_url: str
) -> None:
    scraper = _scraper(open_site_url)
    secret_url = "https://cdn.example.invalid/image.jpg?secret=do-not-log"

    async def fail_download(_url: str) -> bytes:
        raise RuntimeError(secret_url)

    async def skip_robots() -> None:
        scraper._robots_fetched = True

    monkeypatch.setattr(scraper, "_ensure_robots_loaded", skip_robots)
    monkeypatch.setattr("app.services.robots_check.is_allowed", lambda *args: True)
    monkeypatch.setattr(scraper, "_download_media_stream", fail_download)

    result = await scraper.download_media({"images": [secret_url], "videos": []})

    assert result.attempted_count == 1
    assert result.failed_count == 1
    assert result.media_bytes == []
    assert secret_url not in result.failures[0].message
    assert result.failures[0].message == "Errore inatteso durante il download media."


async def test_download_media_reports_partial_http_failure(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)

    result = await scraper.download_media(
        {"images": ["/img1.jpg", "/missing-image.jpg"], "videos": []}
    )

    assert result.attempted_count == 2
    assert len(result.media_bytes) == 1
    assert result.failed_count == 1
    assert result.failures[0].message == "Il server media ha risposto HTTP 404."


def test_media_extraction_warning_only_for_configured_empty_media(open_site_url: str) -> None:
    scraper = _scraper(open_site_url)
    assert scraper.media_extraction_warnings({"images": []}) == [
        "Nessun URL immagine trovato dal selettore configurato per 'images'."
    ]

    config_without_media = {
        **_BASE_CONFIG,
        "fields": {"phone": {"selector": ".phone", "attribute": "text"}},
    }
    scraper_without_media = _scraper(open_site_url, **config_without_media)
    assert scraper_without_media.media_extraction_warnings({}) == []


async def test_robots_disallow_blocks_discover_entirely(closed_site_url: str) -> None:
    """`closed_site_url` ha un robots.txt con `Disallow: /`: `discover()`
    deve rifiutarsi di scaricare anche solo la pagina di elenco, non solo
    i singoli annunci — il divieto non è un'opzione aggirabile."""
    scraper = _scraper(closed_site_url)

    with pytest.raises(RobotsDisallowedError):
        await scraper.discover()


async def test_robots_disallow_blocks_individual_ad_pages(closed_site_url: str) -> None:
    """Anche chiamando `scrape_ad` direttamente su un URL noto (bypassando
    `discover`), il divieto robots.txt deve comunque applicarsi: non è solo
    un controllo "all'ingresso" del crawl."""
    scraper = _scraper(closed_site_url)

    with pytest.raises(RobotsDisallowedError):
        await scraper.scrape_ad(f"{closed_site_url}/ad1.html")
