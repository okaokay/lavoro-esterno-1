"""Test del motore di scraping generico in modalità `render_js=True`
(Scrapling DynamicFetcher su Chromium headless), contro le stesse fixture HTML sintetiche
usate da `test_generic_scraper.py` (`tests/scrapers/conftest.py`) — nessuna
richiesta verso siti reali. Le fixture non richiedono JavaScript per
mostrare il proprio contenuto: qui si verifica che il percorso browser
produca esattamente gli stessi risultati del percorso HTTP sui casi
semplici, e che robots.txt/rate limit restino identici indipendentemente
dal motore di fetch usato.

Richiede i browser Playwright installati (`playwright install chromium`,
vedi `backend/Dockerfile`): se Chromium non è disponibile, i test di questo
modulo vengono saltati invece di fallire, per non bloccare run locali senza
browser installato.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("playwright")

from app.scrapers.generic import GenericScraper, RobotsDisallowedError

_BASE_CONFIG = {
    "ad_link_selector": "a.ad-link",
    "next_page_selector": "a.next",
    "max_pages": 5,
    "max_ads_per_run": 50,
    "rate_limit_seconds": 0,  # test rapidi: la validazione min=1.0 vive solo nello schema API
    "render_js": True,
    "fields": {
        "title": {"selector": "h1.ad-title", "attribute": "text"},
        "description": {"selector": "p.ad-description", "attribute": "text"},
        "phone": {"selector": "span.ad-phone", "attribute": "text"},
        "images": {"selector": "div.ad-gallery img", "attribute": "src", "multiple": True},
    },
}


@pytest.fixture
async def _chromium_ready() -> None:
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            await browser.close()
    except Exception as exc:  # noqa: BLE001 - qualunque fallimento di avvio => skip, non errore
        pytest.skip(f"Browser Playwright (Chromium) non disponibile: {exc}")


def _scraper(base_url: str, **overrides) -> GenericScraper:
    config = {**_BASE_CONFIG, "start_urls": [f"{base_url}/listing.html"], **overrides}
    return GenericScraper(slug="test_source", base_url=base_url, config=config)


@pytest.fixture
def browser_cookie_site_url() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/robots.txt":
                body = b"User-agent: *\nAllow: /\n"
                cookie = None
            elif self.path == "/seed":
                body = b"<html><body>seeded</body></html>"
                cookie = "cf_clearance=synthetic; Path=/; HttpOnly"
            else:
                has_cookie = "cf_clearance=synthetic" in (self.headers.get("Cookie") or "")
                body = (
                    b'<html><body><span class="cookie-ok">yes</span></body></html>'
                    if has_cookie
                    else b'<html><body><span class="cookie-missing">no</span></body></html>'
                )
                cookie = None
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, message_format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()


@pytest.fixture
def javascript_pagination_site_url() -> Iterator[str]:
    listing = b"""<!doctype html><html><body>
    <div id="overlay" style="position:fixed;inset:0;z-index:20"></div>
    <div id="ads"></div><a class="next" aria-label="Next">Next</a>
    <script>
      const pages = [
        ['/ad1.html', '/ad2.html'],
        ['/ad2.html', '/ad3.html'],
        ['/ad4.html']
      ];
      let pageIndex = 0;
      function render() {
        document.querySelector('#ads').innerHTML = pages[pageIndex]
          .map((href) => `<a class="ad-link" href="${href}">${href}</a>`).join('');
        if (pageIndex === pages.length - 1) document.querySelector('.next')?.remove();
      }
      document.querySelector('.next').addEventListener('click', () => {
        pageIndex += 1;
        render();
      });
      render();
    </script></body></html>"""
    navigation_one = b"""<!doctype html><html><body>
      <div id="ads"><a class="ad-link" href="/ad1.html">Ad 1</a></div>
      <button class="next" onclick="location.href='/navigation-2.html'">Next</button>
    </body></html>"""
    navigation_two = b"""<!doctype html><html><body>
      <div id="ads"><a class="ad-link" href="/ad2.html">Ad 2</a></div>
    </body></html>"""
    popup_one = b"""<!doctype html><html><body>
      <div id="ads"><a class="ad-link" href="/ad1.html">Ad 1</a></div>
      <button class="next" onclick="window.open('/popup-2.html', '_blank')">Next</button>
    </body></html>"""
    popup_two = b"""<!doctype html><html><body>
      <div id="ads"><a class="ad-link" href="/ad2.html">Ad 2</a></div>
    </body></html>"""
    replaced_container = b"""<!doctype html><html><body>
      <div id="ads"><a class="ad-link" href="/same.html">Version one</a></div>
      <button class="next">Next</button>
      <script>
        document.querySelector('.next').addEventListener('click', () => {
          document.querySelector('#ads').innerHTML =
            '<a class="ad-link" href="/same.html">Version two</a>';
          document.querySelector('.next').remove();
        });
      </script>
    </body></html>"""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/robots.txt":
                body = b"User-agent: *\nAllow: /\n"
            elif self.path == "/navigation-1.html":
                body = navigation_one
            elif self.path == "/navigation-2.html":
                body = navigation_two
            elif self.path == "/popup-1.html":
                body = popup_one
            elif self.path == "/popup-2.html":
                body = popup_two
            elif self.path == "/replaced-container.html":
                body = replaced_container
            else:
                body = listing
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, message_format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()


@pytest.fixture
def paginated_fields_site_url() -> Iterator[str]:
    interactive = b"""<!doctype html><html><body>
    <span class="phone">+39 333 111 1111</span>
    <section id="carousel"><img class="slide" src="/one.jpg"></section>
    <button class="carousel-next">Next image</button>
    <section id="reviews">
      <article class="review"><b class="author">Ada</b><p class="text">Prima</p></article>
    </section>
    <button class="reviews-more">More reviews</button>
    <script>
      const slides = ['/one.jpg', '/two.jpg', '/three.jpg'];
      let slide = 0;
      document.querySelector('.carousel-next').addEventListener('click', () => {
        slide += 1;
        document.querySelector('.slide').setAttribute('src', slides[slide]);
        if (slide === slides.length - 1) document.querySelector('.carousel-next').remove();
      });
      const reviewPages = [
        [['Ada', 'Prima']],
        [['Ada', 'Prima'], ['Lin', 'Seconda']],
        [['Ada', 'Prima'], ['Lin', 'Seconda'], ['Kim', 'Terza']]
      ];
      let reviewsPage = 0;
      document.querySelector('.reviews-more').addEventListener('click', () => {
        reviewsPage += 1;
        document.querySelector('#reviews').innerHTML = reviewPages[reviewsPage]
          .map(([author, text]) => `<article class="review"><b class="author">${author}</b>`
            + `<p class="text">${text}</p></article>`).join('');
        if (reviewsPage === reviewPages.length - 1) {
          document.querySelector('.reviews-more').remove();
        }
      });
    </script></body></html>"""
    href_page_one = b"""<!doctype html><html><body>
      <span class="phone">+39 333 111 1111</span>
      <p class="comment">Uno</p><a class="comments-next" href="/comments-2.html">Next</a>
    </body></html>"""
    href_page_two = b"""<!doctype html><html><body>
      <span class="phone">+39 333 111 1111</span>
      <p class="comment">Due</p>
    </body></html>"""
    duplicate_listing_one = b"""<!doctype html><html><body>
      <a class="next" style="display:none" href="?page=2#header">Next</a>
      <a class="ad-link" href="/ad1.html">Ad 1</a>
      <a class="next" href="?page=2#footer">Next</a>
    </body></html>"""
    duplicate_listing_two = b"""<!doctype html><html><body>
      <a class="ad-link" href="/ad2.html">Ad 2</a>
    </body></html>"""
    duplicate_items_one = b"""<!doctype html><html><body>
      <span class="phone">+39 333 111 1111</span>
      <p class="comment">Prima</p>
      <article class="review"><b class="author">Ada</b></article>
      <a class="reviews-next" style="display:none"
         href="/duplicate-items-2.html#header">Next</a>
      <a class="reviews-next" href="/duplicate-items-2.html#footer">Next</a>
    </body></html>"""
    duplicate_items_two = b"""<!doctype html><html><body>
      <span class="phone">+39 333 111 1111</span>
      <p class="comment">Seconda</p>
      <article class="review"><b class="author">Lin</b></article>
    </body></html>"""
    unchanged = b"""<!doctype html><html><body>
      <span class="phone">+39 333 111 1111</span>
      <p class="comment">Unico</p><button class="comments-next">Next</button>
    </body></html>"""
    unsafe_links = b"""<!doctype html><html><body>
      <span class="phone">+39 333 111 1111</span><p class="comment">Unico</p>
      <a class="external-next" href="https://example.com/elsewhere">Next</a>
      <a class="blocked-next" href="/blocked">Blocked</a>
    </body></html>"""
    ambiguous = b"""<!doctype html><html><body>
      <span class="phone">+39 333 111 1111</span><p class="comment">Unico</p>
      <button class="comments-next">A</button><button class="comments-next">B</button>
    </body></html>"""
    repeated = b"""<!doctype html><html><body>
      <span class="phone">+39 333 111 1111</span><p class="comment">Uno</p>
      <button class="comments-next">Next</button>
      <script>
        let alternate = false;
        document.querySelector('.comments-next').addEventListener('click', () => {
          alternate = !alternate;
          document.querySelector('.comment').textContent = alternate ? 'Due' : 'Uno';
        });
      </script>
    </body></html>"""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/robots.txt":
                body = b"User-agent: *\nDisallow: /blocked\nAllow: /\n"
            elif self.path == "/comments-1.html":
                body = href_page_one
            elif self.path == "/comments-2.html":
                body = href_page_two
            elif self.path == "/duplicated-listing.html":
                body = duplicate_listing_one
            elif self.path == "/duplicated-listing.html?page=2":
                body = duplicate_listing_two
            elif self.path == "/duplicate-items-1.html":
                body = duplicate_items_one
            elif self.path == "/duplicate-items-2.html":
                body = duplicate_items_two
            elif self.path == "/unchanged.html":
                body = unchanged
            elif self.path == "/unsafe-links.html":
                body = unsafe_links
            elif self.path == "/ambiguous.html":
                body = ambiguous
            elif self.path == "/repeated.html":
                body = repeated
            else:
                body = interactive
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, message_format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()


async def test_discover_follows_pagination_and_collects_all_ad_links(
    _chromium_ready: None, open_site_url: str
) -> None:
    scraper = _scraper(open_site_url)
    try:
        urls = await scraper.discover()
    finally:
        await scraper.aclose()

    assert len(urls) == 3
    assert urls[0].endswith("/ad1.html")
    assert urls[1].endswith("/ad2.html")
    assert urls[2].endswith("/ad3.html")  # dalla pagina 2, raggiunta via next_page_selector
    assert scraper.discovery_diagnostics.pages_visited == 2
    assert scraper.discovery_diagnostics.pagination_mode == "href"
    assert scraper.discovery_diagnostics.stop_reason == "end_of_pagination"


async def test_browser_discovery_supports_xpath_link_pagination(
    _chromium_ready: None, open_site_url: str
) -> None:
    scraper = _scraper(
        open_site_url,
        ad_link_selector="//a[contains(@class, 'ad-link')]",
        ad_link_selector_type="xpath",
        next_page_selector="//a[contains(@class, 'next')]",
        next_page_selector_type="xpath",
    )
    try:
        urls = await scraper.discover()
    finally:
        await scraper.aclose()

    assert [url.rsplit("/", 1)[-1] for url in urls] == [
        "ad1.html",
        "ad2.html",
        "ad3.html",
    ]
    assert scraper.discovery_diagnostics.pagination_mode == "href"


async def test_browser_discovery_supports_xpath_javascript_pagination(
    _chromium_ready: None, javascript_pagination_site_url: str
) -> None:
    scraper = _scraper(
        javascript_pagination_site_url,
        start_urls=[f"{javascript_pagination_site_url}/listing.html"],
        ad_link_selector="//a[contains(@class, 'ad-link')]",
        ad_link_selector_type="xpath",
        next_page_selector="//a[@aria-label='Next']",
        next_page_selector_type="xpath",
        max_pages=3,
    )
    try:
        urls = await scraper.discover()
    finally:
        await scraper.aclose()

    assert [url.rsplit("/", 1)[-1] for url in urls] == [
        "ad1.html",
        "ad2.html",
        "ad3.html",
        "ad4.html",
    ]
    assert scraper.discovery_diagnostics.pagination_mode == "click"


async def test_browser_discover_accepts_hidden_and_visible_equivalent_next_links(
    _chromium_ready: None, paginated_fields_site_url: str
) -> None:
    scraper = _scraper(
        paginated_fields_site_url,
        start_urls=[f"{paginated_fields_site_url}/duplicated-listing.html"],
        next_page_selector="a.next",
        max_pages=3,
    )
    try:
        urls = await scraper.discover()
    finally:
        await scraper.aclose()

    assert urls == [
        f"{paginated_fields_site_url}/ad1.html",
        f"{paginated_fields_site_url}/ad2.html",
    ]
    assert scraper.discovery_diagnostics.pages_visited == 2
    assert scraper.discovery_diagnostics.pagination_mode == "href"
    assert scraper.discovery_diagnostics.stop_reason == "end_of_pagination"
    assert scraper.discovery_diagnostics.errors == []


async def test_discover_clicks_javascript_next_under_overlay_and_deduplicates(
    _chromium_ready: None, javascript_pagination_site_url: str
) -> None:
    scraper = _scraper(
        javascript_pagination_site_url,
        start_urls=[f"{javascript_pagination_site_url}/listing.html"],
        next_page_selector='a.next[aria-label="Next"]',
        max_pages=3,
    )
    try:
        urls = await scraper.discover()
    finally:
        await scraper.aclose()

    assert [url.rsplit("/", 1)[-1] for url in urls] == [
        "ad1.html",
        "ad2.html",
        "ad3.html",
        "ad4.html",
    ]
    assert scraper.discovery_diagnostics.pages_visited == 3
    assert scraper.discovery_diagnostics.pagination_mode == "click"
    assert scraper.discovery_diagnostics.stop_reason == "max_pages"
    assert scraper.discovery_diagnostics.unique_ads_found == 4


async def test_browser_click_supports_full_navigation(
    _chromium_ready: None, javascript_pagination_site_url: str
) -> None:
    scraper = _scraper(
        javascript_pagination_site_url,
        start_urls=[f"{javascript_pagination_site_url}/navigation-1.html"],
        next_page_selector="button.next",
        max_pages=3,
    )
    try:
        urls = await scraper.discover()
    finally:
        await scraper.aclose()

    assert [url.rsplit("/", 1)[-1] for url in urls] == ["ad1.html", "ad2.html"]
    assert scraper.discovery_diagnostics.pages_visited == 2
    assert scraper.discovery_diagnostics.pagination_mode == "click"
    assert scraper.discovery_diagnostics.stop_reason == "end_of_pagination"


async def test_browser_click_adopts_same_origin_popup(
    _chromium_ready: None, javascript_pagination_site_url: str
) -> None:
    scraper = _scraper(
        javascript_pagination_site_url,
        start_urls=[f"{javascript_pagination_site_url}/popup-1.html"],
        next_page_selector="button.next",
        max_pages=3,
    )
    try:
        urls = await scraper.discover()
    finally:
        await scraper.aclose()

    assert [url.rsplit("/", 1)[-1] for url in urls] == ["ad1.html", "ad2.html"]
    assert scraper.discovery_diagnostics.pages_visited == 2
    assert scraper.discovery_diagnostics.stop_reason == "end_of_pagination"


async def test_browser_click_detects_listing_container_replacement(
    _chromium_ready: None, javascript_pagination_site_url: str
) -> None:
    scraper = _scraper(
        javascript_pagination_site_url,
        start_urls=[f"{javascript_pagination_site_url}/replaced-container.html"],
        next_page_selector="button.next",
        max_pages=3,
    )
    try:
        urls = await scraper.discover()
    finally:
        await scraper.aclose()

    assert [url.rsplit("/", 1)[-1] for url in urls] == ["same.html"]
    assert scraper.discovery_diagnostics.pages_visited == 2
    assert scraper.discovery_diagnostics.stop_reason == "end_of_pagination"


async def test_http_mode_reports_javascript_only_pagination(
    javascript_pagination_site_url: str,
) -> None:
    scraper = _scraper(
        javascript_pagination_site_url,
        start_urls=[f"{javascript_pagination_site_url}/listing.html"],
        render_js=False,
        fetch_mode="http",
        next_page_selector='a.next[aria-label="Next"]',
        max_pages=3,
    )
    try:
        await scraper.discover()
    finally:
        await scraper.aclose()

    assert scraper.discovery_diagnostics.pages_visited == 1
    assert scraper.discovery_diagnostics.stop_reason == "click_requires_browser"
    assert scraper.discovery_diagnostics.errors == [
        "Il controllo Next non ha href: usare il mode dynamic o stealth."
    ]


async def test_browser_reports_click_that_does_not_change_page(
    _chromium_ready: None,
    javascript_pagination_site_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.scrapers.generic._PAGINATION_CHANGE_TIMEOUT_MS", 200)
    scraper = _scraper(
        javascript_pagination_site_url,
        start_urls=[f"{javascript_pagination_site_url}/listing.html"],
        next_page_selector="#overlay",
        max_pages=2,
    )
    try:
        await scraper.discover()
    finally:
        await scraper.aclose()

    assert scraper.discovery_diagnostics.pages_visited == 1
    assert scraper.discovery_diagnostics.stop_reason == "page_did_not_change"
    assert scraper.discovery_diagnostics.errors == [
        "Il controllo Next non ha modificato URL, annunci o contenitore entro il timeout."
    ]


async def test_scrape_ad_extracts_configured_fields(
    _chromium_ready: None, open_site_url: str
) -> None:
    scraper = _scraper(open_site_url)
    try:
        raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")
    finally:
        await scraper.aclose()

    assert raw["title"] == "Synthetic Ad One"
    assert raw["description"] == "This is a synthetic test fixture, not real content."
    assert raw["phone"] == "+39 333 111 1111"
    assert raw["images"] == ["/img1.jpg", "/img2.jpg"]


async def test_browser_wait_selector_supports_xpath(
    _chromium_ready: None, open_site_url: str
) -> None:
    scraper = _scraper(
        open_site_url,
        wait_selector="//h1[contains(@class, 'ad-title')]",
        wait_selector_type="xpath",
    )
    try:
        raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")
    finally:
        await scraper.aclose()

    assert raw["title"] == "Synthetic Ad One"


async def test_field_pagination_collects_replaced_carousel_values(
    _chromium_ready: None, paginated_fields_site_url: str
) -> None:
    scraper = _scraper(
        paginated_fields_site_url,
        fields={
            "phone": {"selector": ".phone", "attribute": "text"},
            "images": {
                "selector": ".slide",
                "attribute": "src",
                "multiple": True,
                "pagination": {
                    "nextSelector": ".carousel-next",
                    "maxPages": 10,
                    "maxItems": 10,
                },
            },
        },
    )
    try:
        raw = await scraper.scrape_ad(f"{paginated_fields_site_url}/interactive.html")
    finally:
        await scraper.aclose()

    assert raw["images"] == ["/one.jpg", "/two.jpg", "/three.jpg"]
    diagnostic = scraper.field_pagination_diagnostics["images"]
    assert diagnostic.pages_visited == 3
    assert diagnostic.items_collected == 3
    assert diagnostic.pagination_mode == "click"
    assert diagnostic.stop_reason == "end_of_pagination"
    assert diagnostic.complete is True


async def test_field_pagination_collects_structured_load_more_items(
    _chromium_ready: None, paginated_fields_site_url: str
) -> None:
    scraper = _scraper(
        paginated_fields_site_url,
        fields={
            "phone": {"selector": ".phone", "attribute": "text"},
            "reviews": {
                "extractionMode": "items",
                "multiple": True,
                "containerSelector": ".review",
                "itemFields": {
                    "author": {"selector": ".author", "attribute": "text"},
                    "text": {"selector": ".text", "attribute": "text"},
                },
                "pagination": {
                    "nextSelector": ".reviews-more",
                    "maxPages": 10,
                    "maxItems": 10,
                },
            },
        },
    )
    try:
        raw = await scraper.scrape_ad(f"{paginated_fields_site_url}/interactive.html")
    finally:
        await scraper.aclose()

    assert raw["reviews"] == [
        {"author": "Ada", "text": "Prima"},
        {"author": "Lin", "text": "Seconda"},
        {"author": "Kim", "text": "Terza"},
    ]
    assert scraper.field_pagination_diagnostics["reviews"].complete is True


async def test_field_pagination_stops_at_item_limit_and_reports_truncation(
    _chromium_ready: None, paginated_fields_site_url: str
) -> None:
    scraper = _scraper(
        paginated_fields_site_url,
        fields={
            "phone": {"selector": ".phone", "attribute": "text"},
            "reviews": {
                "extractionMode": "items",
                "multiple": True,
                "containerSelector": ".review",
                "itemFields": {"author": {"selector": ".author"}},
                "pagination": {
                    "nextSelector": ".reviews-more",
                    "maxPages": 10,
                    "maxItems": 2,
                },
            },
        },
    )
    try:
        raw = await scraper.scrape_ad(f"{paginated_fields_site_url}/interactive.html")
    finally:
        await scraper.aclose()

    assert raw["reviews"] == [{"author": "Ada"}, {"author": "Lin"}]
    diagnostic = scraper.field_pagination_diagnostics["reviews"]
    assert diagnostic.stop_reason == "max_items"
    assert diagnostic.complete is False


async def test_field_pagination_follows_same_origin_href(
    _chromium_ready: None, paginated_fields_site_url: str
) -> None:
    scraper = _scraper(
        paginated_fields_site_url,
        fields={
            "phone": {"selector": ".phone", "attribute": "text"},
            "comments": {
                "selector": ".comment",
                "attribute": "text",
                "multiple": True,
                "pagination": {
                    "nextSelector": ".comments-next",
                    "maxPages": 10,
                    "maxItems": 10,
                },
            },
        },
    )
    try:
        raw = await scraper.scrape_ad(f"{paginated_fields_site_url}/comments-1.html")
    finally:
        await scraper.aclose()

    assert raw["comments"] == ["Uno", "Due"]
    diagnostic = scraper.field_pagination_diagnostics["comments"]
    assert diagnostic.pagination_mode == "href"
    assert diagnostic.stop_reason == "end_of_pagination"
    assert diagnostic.complete is True


async def test_field_pagination_accepts_equivalent_duplicate_links(
    _chromium_ready: None, paginated_fields_site_url: str
) -> None:
    scraper = _scraper(
        paginated_fields_site_url,
        fields={
            "phone": {"selector": ".phone", "attribute": "text"},
            "comments": {
                "selector": ".comment",
                "attribute": "text",
                "multiple": True,
                "pagination": {
                    "nextSelector": ".reviews-next",
                    "maxPages": 3,
                    "maxItems": 10,
                },
            },
            "reviews": {
                "extractionMode": "items",
                "multiple": True,
                "containerSelector": ".review",
                "itemFields": {"author": {"selector": ".author"}},
                "pagination": {
                    "nextSelector": ".reviews-next",
                    "maxPages": 3,
                    "maxItems": 10,
                },
            },
        },
    )
    try:
        raw = await scraper.scrape_ad(f"{paginated_fields_site_url}/duplicate-items-1.html")
    finally:
        await scraper.aclose()

    assert raw["comments"] == ["Prima", "Seconda"]
    assert raw["reviews"] == [{"author": "Ada"}, {"author": "Lin"}]
    for field_name in ("comments", "reviews"):
        diagnostic = scraper.field_pagination_diagnostics[field_name]
        assert diagnostic.pages_visited == 2
        assert diagnostic.pagination_mode == "href"
        assert diagnostic.stop_reason == "end_of_pagination"
        assert diagnostic.complete is True


async def test_field_pagination_supports_xpath_for_values_items_and_next(
    _chromium_ready: None, paginated_fields_site_url: str
) -> None:
    scraper = _scraper(
        paginated_fields_site_url,
        fields={
            "phone": {
                "selector": "//span[@class='phone']",
                "selectorType": "xpath",
            },
            "comments": {
                "selector": "//p[@class='comment']",
                "selectorType": "xpath",
                "multiple": True,
                "pagination": {
                    "nextSelector": "//a[contains(@class, 'reviews-next')]",
                    "nextSelectorType": "xpath",
                    "maxPages": 3,
                },
            },
            "reviews": {
                "extractionMode": "items",
                "multiple": True,
                "containerSelector": "//article[@class='review']",
                "containerSelectorType": "xpath",
                "itemFields": {
                    "author": {
                        "selector": ".//b[@class='author']",
                        "selectorType": "xpath",
                    }
                },
                "pagination": {
                    "nextSelector": "//a[contains(@class, 'reviews-next')]",
                    "nextSelectorType": "xpath",
                    "maxPages": 3,
                },
            },
        },
    )
    try:
        raw = await scraper.scrape_ad(f"{paginated_fields_site_url}/duplicate-items-1.html")
    finally:
        await scraper.aclose()

    assert raw["comments"] == ["Prima", "Seconda"]
    assert raw["reviews"] == [{"author": "Ada"}, {"author": "Lin"}]
    assert scraper.field_pagination_diagnostics["comments"].complete is True
    assert scraper.field_pagination_diagnostics["reviews"].complete is True


@pytest.mark.parametrize(
    ("next_selector", "expected_reason"),
    [
        (".external-next", "cross_origin_blocked"),
        (".blocked-next", "robots_disallowed"),
    ],
)
async def test_field_pagination_keeps_partial_values_for_unsafe_links(
    _chromium_ready: None,
    paginated_fields_site_url: str,
    next_selector: str,
    expected_reason: str,
) -> None:
    scraper = _scraper(
        paginated_fields_site_url,
        fields={
            "phone": {"selector": ".phone", "attribute": "text"},
            "comments": {
                "selector": ".comment",
                "attribute": "text",
                "multiple": True,
                "pagination": {"nextSelector": next_selector, "maxPages": 3},
            },
        },
    )
    try:
        raw = await scraper.scrape_ad(f"{paginated_fields_site_url}/unsafe-links.html")
    finally:
        await scraper.aclose()

    assert raw["comments"] == ["Unico"]
    assert scraper.field_pagination_diagnostics["comments"].stop_reason == expected_reason
    assert scraper.field_pagination_warnings == [
        f"Paginazione incompleta per il campo 'comments' ({expected_reason})."
    ]


async def test_field_pagination_keeps_partial_values_when_click_does_not_change(
    _chromium_ready: None,
    paginated_fields_site_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.scrapers.generic._PAGINATION_CHANGE_TIMEOUT_MS", 200)
    scraper = _scraper(
        paginated_fields_site_url,
        fields={
            "phone": {"selector": ".phone", "attribute": "text"},
            "comments": {
                "selector": ".comment",
                "attribute": "text",
                "multiple": True,
                "pagination": {"nextSelector": ".comments-next", "maxPages": 3},
            },
        },
    )
    try:
        raw = await scraper.scrape_ad(f"{paginated_fields_site_url}/unchanged.html")
    finally:
        await scraper.aclose()

    assert raw["comments"] == ["Unico"]
    assert scraper.field_pagination_diagnostics["comments"].stop_reason == "page_did_not_change"


@pytest.mark.parametrize(
    ("path", "expected_values", "expected_reason"),
    [
        ("ambiguous.html", ["Unico"], "ambiguous_next_control"),
        ("repeated.html", ["Uno", "Due"], "repeated_content"),
    ],
)
async def test_field_pagination_stops_on_ambiguous_or_repeated_content(
    _chromium_ready: None,
    paginated_fields_site_url: str,
    path: str,
    expected_values: list[str],
    expected_reason: str,
) -> None:
    scraper = _scraper(
        paginated_fields_site_url,
        fields={
            "phone": {"selector": ".phone", "attribute": "text"},
            "comments": {
                "selector": ".comment",
                "attribute": "text",
                "multiple": True,
                "pagination": {"nextSelector": ".comments-next", "maxPages": 5},
            },
        },
    )
    try:
        raw = await scraper.scrape_ad(f"{paginated_fields_site_url}/{path}")
    finally:
        await scraper.aclose()

    assert raw["comments"] == expected_values
    assert scraper.field_pagination_diagnostics["comments"].stop_reason == expected_reason


async def test_browser_session_preserves_cookies_between_pages(
    _chromium_ready: None, browser_cookie_site_url: str
) -> None:
    scraper = _scraper(browser_cookie_site_url)
    try:
        await scraper._fetch_page(f"{browser_cookie_site_url}/seed")
        response = await scraper._fetch_page(f"{browser_cookie_site_url}/check")
    finally:
        await scraper.aclose()

    assert response.css(".cookie-ok::text").get() == "yes"


async def test_download_media_uses_scrapling_http_regardless_of_render_js(
    _chromium_ready: None, open_site_url: str
) -> None:
    """I media (immagini) sono sempre scaricati via Scrapling HTTP, mai via
    browser, anche quando `render_js=True`: vedi
    `GenericScraper.download_media`."""
    from app.services.media_storage import sniff_mime_type

    scraper = _scraper(open_site_url)
    try:
        raw = await scraper.scrape_ad(f"{open_site_url}/ad1.html")
        normalized = scraper.normalize(raw)
        media = await scraper.download_media(normalized)
    finally:
        await scraper.aclose()

    assert len(media.media_bytes) == 2
    assert media.failed_count == 0
    assert all(sniff_mime_type(blob) == "image/jpeg" for blob in media)


async def test_robots_disallow_blocks_discover_entirely(
    _chromium_ready: None, closed_site_url: str
) -> None:
    """`closed_site_url` ha un robots.txt con `Disallow: /`: anche in
    modalità browser, `discover()` deve rifiutarsi di navigare anche solo
    la pagina di elenco — l'enforcement robots.txt avviene prima della
    navigazione, non è specifico del motore HTTP."""
    scraper = _scraper(closed_site_url)
    try:
        with pytest.raises(RobotsDisallowedError):
            await scraper.discover()
    finally:
        await scraper.aclose()


async def test_robots_disallow_blocks_individual_ad_pages(
    _chromium_ready: None, closed_site_url: str
) -> None:
    scraper = _scraper(closed_site_url)
    try:
        with pytest.raises(RobotsDisallowedError):
            await scraper.scrape_ad(f"{closed_site_url}/ad1.html")
    finally:
        await scraper.aclose()
