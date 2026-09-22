"""Motore di scraping generico, reale e configurabile.

`GenericScraper` non conosce alcun sito specifico: URL, selettori CSS/XPath per
link annunci/paginazione e campi da estrarre arrivano da
`Source.scrape_config` (JSONB, validato da
`app/schemas/sources.py:ScrapeConfigInput` prima di essere salvato).

Vincoli incorporati qui:
- `robots.txt` viene verificato PRIMA di ogni richiesta reale
  (`app/services/robots_check.py`); un URL vietato viene saltato.
- Rate limiting (`rate_limit_seconds`) applicato tra una richiesta e l'altra.
- `user_agent` viene letto dalla configurazione della fonte quando presente,
  con fallback al default di `Scraper`.
- Tetti di sicurezza (`max_pages`, `max_ads_per_run`) per evitare crawl
  incontrollati.

Il fetch delle pagine usa Scrapling:
- `fetch_mode="http"`: richiesta HTTP via `AsyncFetcher`.
- `fetch_mode="dynamic"`: browser headless via `DynamicFetcher`.
- `fetch_mode="stealth"`: browser headless via `StealthyFetcher` con opzioni
  anti-bot configurabili per fonte.

`render_js=True` resta supportato per retrocompatibilita e viene trattato come
`fetch_mode="dynamic"` quando `fetch_mode` non e presente.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import socket
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from curl_cffi.requests import AsyncSession as CurlAsyncSession
from curl_cffi.requests.errors import RequestsError as CurlRequestsError
from lxml import html as lxml_html

from app.scrapers.base import MediaDownloadFailure, MediaDownloadResult, Scraper
from app.services.proxy_rotation import ProxyRuntimeConfig, ProxyRuntimeEvent

_DEFAULT_MAX_PAGES = 3
_DEFAULT_MAX_ADS_PER_RUN = 50
_REQUEST_TIMEOUT_SECONDS = 15.0
_BROWSER_NAVIGATION_TIMEOUT_MS = 20_000
_PAGINATION_CHANGE_TIMEOUT_MS = 15_000

_AMBIGUOUS_NEXT_CONTROL_MESSAGE = (
    "Il selettore di paginazione ha trovato controlli Next non equivalenti: "
    "le corrispondenze multiple sono ammesse solo se tutti gli href portano "
    "alla stessa destinazione."
)

logger = logging.getLogger(__name__)

_STANDARD_FIELDS = {"title", "description", "phone", "images", "videos", "source_url"}


class RobotsDisallowedError(Exception):
    """Sollevata quando `robots.txt` vieta l'accesso a un URL."""

    def __init__(self, url: str):
        super().__init__(f"robots.txt vieta l'accesso a: {url}")
        self.url = url


class PageFetchError(Exception):
    """Sollevata quando Scrapling non riesce a recuperare una pagina."""


class AntiBotBlockedError(PageFetchError):
    """A WAF challenge remained active after Scrapling's bounded solver cycle."""

    def __init__(self, http_status: int | None = None):
        super().__init__(
            "La protezione anti-bot ha bloccato la richiesta dopo i tentativi consentiti."
        )
        self.http_status = http_status


class ProxyRetryableError(PageFetchError):
    """Failure that may be retried through another endpoint in the pool."""

    def __init__(self, category: str):
        super().__init__("Richiesta tramite proxy non riuscita.")
        self.category = category


class ProxyPoolExhaustedError(PageFetchError):
    """All candidates assigned to this run failed; direct access is forbidden."""

    def __init__(self, message: str, category: str | None = None):
        super().__init__(message)
        self.category = category


class BrowserPaginationError(Exception):
    """Errore browser classificato senza conservare dettagli della pagina."""

    def __init__(self, reason: str, safe_message: str):
        super().__init__(safe_message)
        self.reason = reason
        self.safe_message = safe_message


@dataclass
class DiscoveryDiagnostics:
    pages_visited: int = 0
    configured_max_pages: int = 1
    pagination_mode: str = "none"
    stop_reason: str = "not_started"
    unique_ads_found: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class FieldPaginationDiagnostic:
    """Risultato privo di contenuti sensibili della paginazione di un campo."""

    pages_visited: int = 0
    items_collected: int = 0
    pagination_mode: str = "none"
    stop_reason: str = "not_started"
    complete: bool = False


class GenericScraper(Scraper):
    """Connettore generico guidato da configurazione."""

    def __init__(
        self,
        slug: str,
        base_url: str,
        config: dict[str, Any],
        proxy_candidates: list[ProxyRuntimeConfig] | None = None,
    ):
        self.slug = slug
        self.base_url = base_url
        self.config = config
        self.render_js = bool(self._config_value("render_js", "renderJs", False))
        self.fetch_mode = str(
            self._config_value("fetch_mode", "fetchMode")
            or ("dynamic" if self.render_js else "http")
        )
        if self.fetch_mode not in {"http", "dynamic", "stealth"}:
            raise ValueError(f"fetch_mode non valido: {self.fetch_mode!r}")

        configured_user_agent = self._config_value("user_agent", "userAgent")
        self.configured_user_agent = (
            str(configured_user_agent).strip() if configured_user_agent else None
        )
        if self.configured_user_agent:
            self.user_agent = self.configured_user_agent

        configured_rate_limit = self._config_value("rate_limit_seconds", "rateLimitSeconds")
        self.rate_limit_seconds = (
            self.rate_limit_seconds
            if configured_rate_limit is None
            else float(configured_rate_limit)
        )

        self._robots_txt: str | None = None
        self._robots_fetched = False
        self._client: httpx.AsyncClient | None = None
        self._browser_session: Any | None = None
        self._proxy_candidates = list(proxy_candidates or [])
        self._proxy_index = 0
        self.proxy_events: list[ProxyRuntimeEvent] = []
        self.discovery_diagnostics = DiscoveryDiagnostics()
        self.field_pagination_diagnostics: dict[str, FieldPaginationDiagnostic] = {}
        self.field_pagination_warnings: list[str] = []
        # URL assoluto -> pagina di listing piu bassa in cui e stato visto.
        self.discovered_page_numbers: dict[str, int] = {}

    def _config_value(self, snake_case_key: str, camel_case_key: str, default: Any = None) -> Any:
        return self.config.get(snake_case_key, self.config.get(camel_case_key, default))

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            proxy = self._active_proxy()
            self._client = httpx.AsyncClient(
                follow_redirects=True, proxy=proxy.httpx_url() if proxy else None
            )
        return self._client

    def _active_proxy(self) -> ProxyRuntimeConfig | None:
        if not self._proxy_candidates:
            return None
        if self._proxy_index >= len(self._proxy_candidates):
            raise ProxyPoolExhaustedError("Nessun proxy sano rimasto per questa operazione.")
        return self._proxy_candidates[self._proxy_index]

    @staticmethod
    def _proxy_failure_category(exc: Exception) -> str | None:
        if isinstance(exc, ProxyRetryableError):
            return exc.category
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {
            403,
            407,
            429,
        }:
            return f"http_{exc.response.status_code}"
        if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
            return "timeout"
        if "timeout" in type(exc).__name__.lower():
            return "timeout"
        if isinstance(exc, httpx.ProxyError):
            return "proxy_connection"
        if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
            return "network"
        if isinstance(exc, CurlRequestsError):
            return "proxy_connection"
        if isinstance(exc, PageFetchError) and str(exc).startswith("Fetch Scrapling fallito"):
            return "browser_network"
        return None

    async def _rotate_proxy(self) -> bool:
        if self._proxy_index + 1 >= len(self._proxy_candidates):
            return False
        await self._close_browser_session()
        self._proxy_index += 1
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        return True

    async def _with_proxy_rotation(self, operation: str, callback: Any) -> Any:
        """Run one bounded network operation and rotate without direct fallback."""
        if not self._proxy_candidates:
            return await callback()
        while True:
            proxy = self._active_proxy()
            started = time.monotonic()
            try:
                value = await callback()
            except Exception as exc:
                category = self._proxy_failure_category(exc)
                if category is None:
                    raise
                self.proxy_events.append(
                    ProxyRuntimeEvent(
                        endpoint_id=proxy.endpoint_id,
                        operation=operation,
                        outcome="failed",
                        latency_ms=int((time.monotonic() - started) * 1000),
                        failure_category=category,
                    )
                )
                if not await self._rotate_proxy():
                    raise ProxyPoolExhaustedError(
                        "Tutti i proxy disponibili hanno fallito; accesso diretto bloccato.",
                        category=category,
                    ) from exc
                continue
            self.proxy_events.append(
                ProxyRuntimeEvent(
                    endpoint_id=proxy.endpoint_id,
                    operation=operation,
                    outcome="success",
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
            )
            return value

    async def _ensure_robots_loaded(self) -> None:
        if not self._robots_fetched:
            from app.services.robots_check import fetch_robots_txt

            async def fetch() -> str | None:
                return await fetch_robots_txt(self.base_url, client=self._ensure_client())

            self._robots_txt = await self._with_proxy_rotation("robots", fetch)
            self._robots_fetched = True

    async def _fetch_page(self, url: str) -> Any:
        """Fetch unico per pagine HTML: robots.txt + rate limit + Scrapling."""
        await self._ensure_robots_loaded()
        from app.services.robots_check import is_allowed

        if not is_allowed(self._robots_txt, url, self.user_agent):
            raise RobotsDisallowedError(url)

        await asyncio.sleep(self.rate_limit_seconds)

        async def fetch() -> Any:
            try:
                if self.fetch_mode == "http":
                    return await self._fetch_page_http(url)
                if self.fetch_mode == "dynamic":
                    return await self._fetch_page_dynamic(url)
                return await self._fetch_page_stealth(url)
            except Exception as exc:
                if isinstance(exc, PageFetchError):
                    raise
                raise PageFetchError(f"Fetch Scrapling fallito per {url}: {exc}") from exc

        return await self._with_proxy_rotation("page", fetch)

    async def _fetch_page_http(self, url: str) -> Any:
        from scrapling.fetchers import AsyncFetcher

        proxy = self._active_proxy()
        response = await AsyncFetcher.get(
            url,
            headers={"User-Agent": self.user_agent},
            stealthy_headers=False,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            proxy=proxy.scrapling_value() if proxy else None,
        )
        self._raise_for_status(response, url)
        return response

    async def _fetch_page_dynamic(self, url: str) -> Any:
        session = await self._ensure_browser_session()
        response = await session.fetch(url, **self._browser_request_kwargs())
        self._raise_for_status(response, url)
        return response

    async def _fetch_page_stealth(self, url: str) -> Any:
        session = await self._ensure_browser_session()
        response = await session.fetch(url, **self._browser_request_kwargs())
        self._raise_for_status(response, url)
        return response

    def _browser_session_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "headless": True,
            "timeout": _BROWSER_NAVIGATION_TIMEOUT_MS,
        }
        if self.configured_user_agent:
            kwargs["useragent"] = self.configured_user_agent
        proxy = self._active_proxy()
        if proxy:
            kwargs["proxy"] = proxy.scrapling_value()
        if self.fetch_mode == "stealth":
            kwargs.update(
                solve_cloudflare=bool(
                    self._config_value("solve_cloudflare", "solveCloudflare", False)
                ),
                block_webrtc=bool(self._config_value("block_webrtc", "blockWebrtc", False)),
                hide_canvas=bool(self._config_value("hide_canvas", "hideCanvas", False)),
                real_chrome=bool(self._config_value("real_chrome", "realChrome", False)),
                block_ads=bool(self._config_value("block_ads", "blockAds", False)),
            )
        return kwargs

    def _browser_request_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"network_idle": True}
        if self.fetch_mode == "stealth":
            kwargs["solve_cloudflare"] = bool(
                self._config_value("solve_cloudflare", "solveCloudflare", False)
            )
        if wait_selector := self._config_value("wait_selector", "waitSelector"):
            wait_selector_type = self._config_value("wait_selector_type", "waitSelectorType", "css")
            kwargs["wait_selector"] = self._browser_selector(
                str(wait_selector), str(wait_selector_type)
            )
        if wait_ms := self._config_value("wait_ms", "waitMs"):
            kwargs["wait"] = int(wait_ms)
        return kwargs

    async def _ensure_browser_session(self) -> Any:
        if self._browser_session is not None:
            return self._browser_session
        if self.fetch_mode == "dynamic":
            from scrapling.fetchers import AsyncDynamicSession

            session_class = AsyncDynamicSession
        else:
            from scrapling.fetchers import AsyncStealthySession

            session_class = AsyncStealthySession
        session = session_class(**self._browser_session_kwargs())
        try:
            await session.start()
        except Exception:
            await session.close()
            raise
        self._browser_session = session
        return session

    async def _close_browser_session(self) -> None:
        if self._browser_session is None:
            return
        session = self._browser_session
        self._browser_session = None
        try:
            await session.close()
        except Exception:  # noqa: BLE001 - cleanup best-effort, without target data in logs
            logger.warning("Chiusura della sessione browser Scrapling non riuscita.")

    @staticmethod
    def _response_html(response: Any) -> str:
        html_content = getattr(response, "html_content", None)
        if html_content is not None:
            return str(html_content)
        body = getattr(response, "body", b"")
        if isinstance(body, bytes):
            return body.decode("utf-8", errors="ignore")
        return str(body or "")

    @classmethod
    def _is_cloudflare_challenge(cls, response: Any, status: int | None) -> bool:
        html = cls._response_html(response).lower()
        headers = getattr(response, "headers", {}) or {}
        normalized_headers = {
            str(key).lower(): str(value).lower() for key, value in headers.items()
        }
        cloudflare_header = (
            "cloudflare" in normalized_headers.get("server", "") or "cf-ray" in normalized_headers
        )
        challenge_markers = sum(
            marker in html
            for marker in (
                "/cdn-cgi/challenge-platform/",
                "cf-chl-",
                'id="challenge-form"',
            )
        )
        interstitial_title = any(
            title in html
            for title in (
                "<title>just a moment",
                "<title>attention required",
            )
        )
        if status == 403 and (cloudflare_header or challenge_markers > 0 or interstitial_title):
            return True
        return interstitial_title and challenge_markers > 0

    def _raise_for_status(self, response: Any, url: str) -> None:
        status = getattr(response, "status", None)
        status_code = int(status) if status is not None else None
        if self._is_cloudflare_challenge(response, status_code):
            if self._proxy_candidates:
                raise ProxyRetryableError("anti_bot_blocked")
            raise AntiBotBlockedError(status_code)
        if status_code is not None and not 200 <= status_code < 300:
            if self._proxy_candidates and status_code in {403, 407, 429}:
                raise ProxyRetryableError(f"http_{status_code}")
            raise PageFetchError(f"Risposta HTTP {status_code} per {url}")

    @staticmethod
    def _browser_selector(selector: str, selector_type: str) -> str:
        """Converte il selettore configurato nel formato accettato da Playwright."""
        return f"xpath={selector}" if selector_type == "xpath" else selector

    @staticmethod
    def _select_elements(page: Any, selector: str, selector_type: str = "css") -> list[Any]:
        """Seleziona elementi con l'engine CSS o XPath 1.0 di Scrapling."""
        selected = page.xpath(selector) if selector_type == "xpath" else page.css(selector)
        return list(selected)

    @classmethod
    def _extract_all(
        cls, page: Any, selector: str, attribute: str, selector_type: str = "css"
    ) -> list[str]:
        elements = cls._select_elements(page, selector, selector_type)
        if attribute == "text":
            # `selector::text` restituisce un valore per ciascun nodo testuale:
            # con <p>prima<br>seconda</p> il consumer non-multiple prendeva
            # quindi soltanto "prima". Selezioniamo invece gli elementi e ne
            # ricostruiamo il testo completo, conservando i <br> come newline.
            values = [cls._element_text(element) for element in elements]
        else:
            values = [element.attrib.get(attribute) for element in elements]
        return [str(value).strip() for value in values if value is not None and str(value).strip()]

    @staticmethod
    def _element_text(element: Any) -> str:
        """Estrae il testo visibile preservando solo i break HTML espliciti.

        Scrapling espone l'HTML serializzato dell'elemento; ripercorrerlo evita
        di inserire newline artificiali attorno a tag inline come ``strong`` o
        ``span``. ``None`` è usato internamente come marcatore di ``br``.
        """
        root = lxml_html.fragment_fromstring(str(element.html_content), create_parent="div")
        tokens: list[str | None] = []

        def visit(node: Any) -> None:
            if node.text:
                tokens.append(str(node.text))
            for child in node:
                tag = child.tag.lower() if isinstance(child.tag, str) else ""
                if tag == "br":
                    tokens.append(None)
                elif tag not in {"script", "style"}:
                    visit(child)
                if child.tail:
                    tokens.append(str(child.tail))

        visit(root)
        lines: list[str] = []
        current: list[str] = []
        for token in tokens:
            if token is None:
                lines.append(" ".join("".join(current).split()))
                current = []
            else:
                current.append(token)
        lines.append(" ".join("".join(current).split()))

        # Mantiene le righe vuote tra <br> consecutivi, ma replica il vecchio
        # `.strip()` eliminando whitespace/break soltanto ai bordi.
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)

    async def discover(self) -> list[str]:
        configured_max_pages = int(
            self._config_value("max_pages", "maxPages") or _DEFAULT_MAX_PAGES
        )
        configured_max_ads = int(
            self._config_value("max_ads_per_run", "maxAdsPerRun") or _DEFAULT_MAX_ADS_PER_RUN
        )
        pages_limited = bool(self._config_value("max_pages_enabled", "maxPagesEnabled", True))
        ads_limited = bool(
            self._config_value("max_ads_per_run_enabled", "maxAdsPerRunEnabled", True)
        )
        max_pages = configured_max_pages if pages_limited else 2**31 - 1
        max_ads = configured_max_ads if ads_limited else 2**31 - 1
        ad_link_selector = self._config_value("ad_link_selector", "adLinkSelector")
        ad_link_selector_type = str(
            self._config_value("ad_link_selector_type", "adLinkSelectorType", "css")
        )
        next_page_selector = self._config_value("next_page_selector", "nextPageSelector")
        next_page_selector_type = str(
            self._config_value("next_page_selector_type", "nextPageSelectorType", "css")
        )

        self.discovery_diagnostics = DiscoveryDiagnostics(configured_max_pages=configured_max_pages)
        if next_page_selector and pages_limited and max_pages == 1:
            self.discovery_diagnostics.warnings.append(
                "Il selettore di paginazione e configurato, ma maxPages=1 limita lo scan "
                "alla prima pagina."
            )

        if self.fetch_mode == "http":
            urls = await self._discover_http(
                max_pages=max_pages,
                max_ads=max_ads,
                ad_link_selector=ad_link_selector,
                ad_link_selector_type=ad_link_selector_type,
                next_page_selector=next_page_selector,
                next_page_selector_type=next_page_selector_type,
            )
        else:
            urls = await self._discover_browser(
                max_pages=max_pages,
                max_ads=max_ads,
                ad_link_selector=ad_link_selector,
                ad_link_selector_type=ad_link_selector_type,
                next_page_selector=next_page_selector,
                next_page_selector_type=next_page_selector_type,
            )
        self.discovery_diagnostics.unique_ads_found = len(urls)
        return urls

    @staticmethod
    def _same_origin(first: str, second: str) -> bool:
        def origin(url: str) -> tuple[str, str, int | None]:
            parsed = urlparse(url)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return parsed.scheme.lower(), (parsed.hostname or "").lower(), port

        return origin(first) == origin(second)

    @staticmethod
    def _equivalent_next_url(current_url: str, hrefs: list[Any], control_count: int) -> str | None:
        """Restituisce la destinazione comune di uno o piu link Next.

        Il frammento non identifica una nuova pagina HTTP e viene quindi escluso
        dal confronto. Il numero di href deve coincidere con quello dei controlli:
        una selezione mista link/pulsanti resta intenzionalmente ambigua.
        """
        if control_count < 1 or len(hrefs) != control_count:
            return None
        clean_hrefs = [
            str(href).strip() for href in hrefs if href is not None and str(href).strip()
        ]
        if len(clean_hrefs) != control_count:
            return None
        destinations = {urldefrag(urljoin(current_url, href)).url for href in clean_hrefs}
        if len(destinations) != 1:
            return None
        return destinations.pop()

    @staticmethod
    async def _first_available_control(controls: Any, control_count: int) -> Any | None:
        """Seleziona il primo duplicato visibile e abilitato nell'ordine DOM."""
        for index in range(control_count):
            candidate = controls.nth(index)
            if await candidate.is_visible() and await candidate.is_enabled():
                return candidate
        return None

    @staticmethod
    def _browser_failure_reason(page: Any, exc: Exception, *, during_click: bool) -> str:
        """Classifica un errore Playwright senza propagarne testo o URL."""
        try:
            if page.is_closed():
                return "page_closed"
        except Exception:  # noqa: BLE001 - anche l'ispezione puo fallire a browser chiuso
            pass
        try:
            browser = page.context.browser
            if browser is not None and not browser.is_connected():
                return "browser_closed"
        except Exception:  # noqa: BLE001 - contesto gia distrutto
            pass

        # Il dettaglio resta in memoria: serve solo a distinguere errori che
        # Playwright non espone con sottoclassi pubbliche specifiche.
        detail = f"{type(exc).__name__} {exc}".lower()
        if "browser has been closed" in detail or "browser closed" in detail:
            return "browser_closed"
        if (
            "page has been closed" in detail
            or "target page, context or browser has been closed" in detail
        ):
            return "page_closed"
        if "detached" in detail or "not attached" in detail:
            return "next_control_detached"
        if "timeout" in detail and not during_click:
            return "browser_navigation_timeout"
        return "browser_click_failed" if during_click else "browser_navigation_timeout"

    @staticmethod
    def _pagination_error_message(reason: str) -> str:
        return {
            "browser_click_failed": (
                "Il browser non e riuscito ad attivare il controllo Next. "
                "Verificare che il selettore identifichi un elemento cliccabile."
            ),
            "browser_navigation_timeout": (
                "La pagina successiva non ha completato il caricamento entro il timeout."
            ),
            "next_control_detached": (
                "Il controllo Next e stato sostituito dalla pagina prima del click."
            ),
            "page_closed": "La pagina browser e stata chiusa durante la paginazione.",
            "browser_closed": "Il browser si e chiuso durante la paginazione.",
            "cross_origin_popup": (
                "Il controllo Next ha aperto una pagina appartenente a un'origine diversa."
            ),
            "page_did_not_change": (
                "Il controllo Next non ha modificato URL, annunci o contenitore "
                "entro il timeout."
            ),
        }.get(reason, "Errore browser durante la paginazione.")

    def _set_browser_pagination_failure(self, reason: str) -> None:
        self.discovery_diagnostics.stop_reason = reason
        message = self._pagination_error_message(reason)
        if message not in self.discovery_diagnostics.errors:
            self.discovery_diagnostics.errors.append(message)

    async def _browser_listing_state(
        self,
        browser_page: Any,
        ad_link_selector: str,
        ad_link_selector_type: str,
    ) -> tuple[str, list[str], str]:
        """Rileva URL, link e digest DOM senza restituire contenuti HTML."""
        current_url = str(browser_page.url)
        ad_locator = browser_page.locator(
            self._browser_selector(ad_link_selector, ad_link_selector_type)
        )
        state = await ad_locator.evaluate_all(
            """(elements) => {
                const links = elements
                  .map((element) => element.getAttribute('href'))
                  .filter(Boolean);
                const container = elements.length > 0
                  ? (elements[0].parentElement || elements[0])
                  : document.body;
                const value = container ? container.innerHTML : '';
                let hash = 2166136261;
                for (let index = 0; index < value.length; index += 1) {
                  hash ^= value.charCodeAt(index);
                  hash = Math.imul(hash, 16777619);
                }
                return {links, containerHash: (hash >>> 0).toString(16)};
            }"""
        )
        hrefs = [str(item) for item in state.get("links", [])]
        absolute_hrefs = [urljoin(current_url, href) for href in hrefs]
        return current_url, absolute_hrefs, str(state.get("containerHash", ""))

    def _add_ad_urls(
        self,
        urls: list[str],
        seen_urls: set[str],
        page_url: str,
        hrefs: list[str],
        max_ads: int,
        page_number: int,
    ) -> bool:
        for href in hrefs:
            absolute = urljoin(page_url, href)
            previous_page = self.discovered_page_numbers.get(absolute)
            self.discovered_page_numbers[absolute] = (
                page_number if previous_page is None else min(previous_page, page_number)
            )
            if absolute in seen_urls:
                continue
            seen_urls.add(absolute)
            urls.append(absolute)
            if len(urls) >= max_ads:
                self.discovery_diagnostics.stop_reason = "max_ads"
                return True
        return False

    async def _discover_http(
        self,
        *,
        max_pages: int,
        max_ads: int,
        ad_link_selector: str,
        ad_link_selector_type: str,
        next_page_selector: str | None,
        next_page_selector_type: str,
    ) -> list[str]:
        urls: list[str] = []
        seen_urls: set[str] = set()
        for start_url in self._config_value("start_urls", "startUrls"):
            page_url = start_url
            visited_pages: set[str] = set()
            for page_index in range(max_pages):
                if page_url in visited_pages:
                    self.discovery_diagnostics.stop_reason = "repeated_page"
                    self.discovery_diagnostics.errors.append(
                        "La paginazione ha prodotto una pagina gia visitata."
                    )
                    break
                visited_pages.add(page_url)
                page = await self._fetch_page(page_url)
                self.discovery_diagnostics.pages_visited += 1
                if self._add_ad_urls(
                    urls,
                    seen_urls,
                    page_url,
                    self._extract_all(page, ad_link_selector, "href", ad_link_selector_type),
                    max_ads,
                    page_index + 1,
                ):
                    return urls
                if not next_page_selector:
                    self.discovery_diagnostics.stop_reason = "no_pagination_configured"
                    break
                if page_index + 1 >= max_pages:
                    self.discovery_diagnostics.stop_reason = "max_pages"
                    break
                controls = self._select_elements(page, next_page_selector, next_page_selector_type)
                if not controls:
                    self.discovery_diagnostics.stop_reason = "end_of_pagination"
                    if page_index == 0:
                        self.discovery_diagnostics.errors.append(
                            "Il selettore di paginazione non ha trovato il controllo Next."
                        )
                    break
                next_hrefs = self._extract_all(
                    page, next_page_selector, "href", next_page_selector_type
                )
                next_url = self._equivalent_next_url(page_url, next_hrefs, len(controls))
                if len(controls) > 1 and next_url is None:
                    self.discovery_diagnostics.stop_reason = "ambiguous_next_control"
                    self.discovery_diagnostics.errors.append(_AMBIGUOUS_NEXT_CONTROL_MESSAGE)
                    break
                if next_url is None:
                    self.discovery_diagnostics.stop_reason = "click_requires_browser"
                    self.discovery_diagnostics.errors.append(
                        "Il controllo Next non ha href: usare il mode dynamic o stealth."
                    )
                    break
                if not self._same_origin(start_url, next_url):
                    self.discovery_diagnostics.stop_reason = "cross_origin_blocked"
                    self.discovery_diagnostics.errors.append(
                        "La paginazione verso un'origine diversa e stata bloccata."
                    )
                    break
                self.discovery_diagnostics.pagination_mode = "href"
                page_url = next_url
        if self.discovery_diagnostics.stop_reason == "not_started":
            self.discovery_diagnostics.stop_reason = "completed"
        return urls

    async def _discover_browser(
        self,
        *,
        max_pages: int,
        max_ads: int,
        ad_link_selector: str,
        ad_link_selector_type: str,
        next_page_selector: str | None,
        next_page_selector_type: str,
    ) -> list[str]:
        from app.services.robots_check import is_allowed

        await self._ensure_robots_loaded()
        urls: list[str] = []
        seen_urls: set[str] = set()
        stop_all = False

        for start_url in self._config_value("start_urls", "startUrls"):
            if stop_all:
                break
            if not is_allowed(self._robots_txt, start_url, self.user_agent):
                raise RobotsDisallowedError(start_url)
            await asyncio.sleep(self.rate_limit_seconds)
            seen_pages: set[str] = set()

            async def paginate_pages(
                browser_page: Any,
                *,
                start_url: str = start_url,
                seen_pages: set[str] = seen_pages,
            ) -> None:
                nonlocal stop_all
                for page_index in range(max_pages):
                    current_url, absolute_hrefs, container_hash = (
                        await self._browser_listing_state(
                            browser_page, ad_link_selector, ad_link_selector_type
                        )
                    )
                    hrefs = absolute_hrefs
                    fingerprint = json.dumps(
                        [current_url, absolute_hrefs, container_hash],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    if fingerprint in seen_pages:
                        self.discovery_diagnostics.stop_reason = "repeated_page"
                        self.discovery_diagnostics.errors.append(
                            "La paginazione ha prodotto contenuti gia visitati."
                        )
                        break
                    seen_pages.add(fingerprint)
                    self.discovery_diagnostics.pages_visited += 1
                    if self._add_ad_urls(
                        urls,
                        seen_urls,
                        current_url,
                        hrefs,
                        max_ads,
                        page_index + 1,
                    ):
                        stop_all = True
                        break
                    if not next_page_selector:
                        self.discovery_diagnostics.stop_reason = "no_pagination_configured"
                        break
                    if page_index + 1 >= max_pages:
                        self.discovery_diagnostics.stop_reason = "max_pages"
                        break

                    controls = browser_page.locator(
                        self._browser_selector(next_page_selector, next_page_selector_type)
                    )
                    control_count = await controls.count()
                    if control_count == 0:
                        self.discovery_diagnostics.stop_reason = "end_of_pagination"
                        if page_index == 0:
                            self.discovery_diagnostics.errors.append(
                                "Il selettore di paginazione non ha trovato il controllo Next."
                            )
                        break
                    control_hrefs = await controls.evaluate_all(
                        "(elements) => elements.map((element) => element.getAttribute('href'))"
                    )
                    equivalent_next_url = self._equivalent_next_url(
                        current_url, control_hrefs, control_count
                    )
                    if control_count > 1 and equivalent_next_url is None:
                        self.discovery_diagnostics.stop_reason = "ambiguous_next_control"
                        self.discovery_diagnostics.errors.append(_AMBIGUOUS_NEXT_CONTROL_MESSAGE)
                        break

                    control = await self._first_available_control(controls, control_count)
                    if control is None:
                        self.discovery_diagnostics.stop_reason = "next_control_unavailable"
                        self.discovery_diagnostics.errors.append(
                            "Il controllo Next non e visibile o abilitato."
                        )
                        break
                    href = equivalent_next_url or await control.get_attribute("href")
                    before_url = current_url
                    before_links = json.dumps(absolute_hrefs, separators=(",", ":"))
                    before_container = container_hash
                    original_page = browser_page
                    try:
                        known_pages = set(browser_page.context.pages)
                    except Exception:  # noqa: BLE001 - verificato dopo il click
                        known_pages = {browser_page}
                    await asyncio.sleep(self.rate_limit_seconds)
                    click_error: Exception | None = None
                    if href:
                        next_url = urldefrag(urljoin(current_url, href)).url
                        if not self._same_origin(start_url, next_url):
                            self.discovery_diagnostics.stop_reason = "cross_origin_blocked"
                            self.discovery_diagnostics.errors.append(
                                "La paginazione verso un'origine diversa e stata bloccata."
                            )
                            break
                        if not is_allowed(self._robots_txt, next_url, self.user_agent):
                            raise RobotsDisallowedError(next_url)
                        self.discovery_diagnostics.pagination_mode = "href"
                        try:
                            await browser_page.goto(
                                next_url,
                                wait_until="domcontentloaded",
                                timeout=_BROWSER_NAVIGATION_TIMEOUT_MS,
                            )
                        except Exception as exc:  # noqa: BLE001 - categorizzato senza dettagli
                            reason = self._browser_failure_reason(
                                browser_page, exc, during_click=False
                            )
                            raise BrowserPaginationError(
                                reason, self._pagination_error_message(reason)
                            ) from None
                    else:
                        self.discovery_diagnostics.pagination_mode = "click"
                        # Il click Playwright forzato supera gli overlay visuali e
                        # genera un evento utente reale quando il controllo riceve
                        # gli eventi del puntatore. Se un overlay lo copre, il
                        # dispatch Playwright sul locator evita di cliccare
                        # l'overlay senza eseguire un secondo tentativo.
                        try:
                            receives_pointer = await control.evaluate(
                                """(element) => {
                                    const rect = element.getBoundingClientRect();
                                    const x = rect.left + (rect.width / 2);
                                    const y = rect.top + (rect.height / 2);
                                    const hit = document.elementFromPoint(x, y);
                                    return hit === element || element.contains(hit);
                                }"""
                            )
                            if receives_pointer:
                                await control.click(
                                    force=True,
                                    no_wait_after=True,
                                    timeout=_BROWSER_NAVIGATION_TIMEOUT_MS,
                                )
                            else:
                                await control.dispatch_event("click")
                        except Exception as exc:  # noqa: BLE001 - puo avere gia navigato
                            click_error = exc

                    deadline = time.monotonic() + (_PAGINATION_CHANGE_TIMEOUT_MS / 1000)
                    page_changed = False
                    navigation_started = False
                    while time.monotonic() < deadline:
                        try:
                            popup = next(
                                (
                                    page
                                    for page in browser_page.context.pages
                                    if page not in known_pages and not page.is_closed()
                                ),
                                None,
                            )
                            if popup is not None:
                                popup_url = str(popup.url)
                                if popup_url != "about:blank":
                                    if not self._same_origin(start_url, popup_url):
                                        self._set_browser_pagination_failure(
                                            "cross_origin_popup"
                                        )
                                        return
                                    browser_page = popup
                                    navigation_started = True

                            after_url, after_hrefs, after_container = (
                                await self._browser_listing_state(
                                    browser_page,
                                    ad_link_selector,
                                    ad_link_selector_type,
                                )
                            )
                            after_links = json.dumps(after_hrefs, separators=(",", ":"))
                            if (
                                browser_page is not original_page
                                or after_url != before_url
                                or after_links != before_links
                                or after_container != before_container
                            ):
                                page_changed = True
                                break
                        except Exception as exc:  # noqa: BLE001 - transitorio durante navigation
                            reason = self._browser_failure_reason(
                                browser_page, exc, during_click=False
                            )
                            if reason in {"page_closed", "browser_closed"}:
                                raise BrowserPaginationError(
                                    reason, self._pagination_error_message(reason)
                                ) from None
                            navigation_started = True
                        await asyncio.sleep(0.2)
                    if not page_changed:
                        if click_error is not None:
                            reason = self._browser_failure_reason(
                                browser_page, click_error, during_click=True
                            )
                        elif navigation_started:
                            reason = "browser_navigation_timeout"
                        else:
                            reason = "page_did_not_change"
                        self._set_browser_pagination_failure(reason)
                        break
                    if not self._same_origin(start_url, str(browser_page.url)):
                        self.discovery_diagnostics.stop_reason = "cross_origin_blocked"
                        self.discovery_diagnostics.errors.append(
                            "La paginazione verso un'origine diversa e stata bloccata."
                        )
                        break

            action_errors: list[Exception] = []

            async def paginate(
                browser_page: Any, *, action_errors: list[Exception] = action_errors
            ) -> None:
                try:
                    await paginate_pages(browser_page)
                except RobotsDisallowedError as exc:
                    action_errors.append(exc)
                except BrowserPaginationError as exc:
                    self._set_browser_pagination_failure(exc.reason)
                except Exception:  # noqa: BLE001 - il dettaglio puo contenere URL/dati pagina
                    self._set_browser_pagination_failure("browser_navigation_timeout")

            await self._with_proxy_rotation(
                "discovery",
                lambda start_url=start_url, paginate=paginate: self._fetch_browser_for_discovery(
                    start_url, paginate
                ),
            )
            if action_errors:
                raise action_errors[0]

        if self.discovery_diagnostics.stop_reason == "not_started":
            self.discovery_diagnostics.stop_reason = "completed"
        return urls

    async def _fetch_browser_for_discovery(self, url: str, page_action: Any) -> None:
        kwargs = self._browser_request_kwargs()
        kwargs["page_action"] = page_action
        session = await self._ensure_browser_session()
        response = await session.fetch(url, **kwargs)
        self._raise_for_status(response, url)

    async def scrape_ad(self, url: str) -> dict[str, Any]:
        page = await self._fetch_page(url)

        raw: dict[str, Any] = {"source_url": url}
        for field_name, spec in self._config_value("fields", "fields", {}).items():
            initial_value = self._extract_field(page, spec)
            if self._field_option(spec, "pagination", "pagination") is None:
                raw[field_name] = initial_value
                continue
            raw[field_name] = await self._extract_paginated_field(
                url, field_name, spec, initial_value
            )
        return raw

    def _extract_field(self, page: Any, spec: dict[str, Any]) -> Any:
        extraction_mode = spec.get("extraction_mode", spec.get("extractionMode", "value"))
        if extraction_mode == "keyValue":
            return self._extract_key_value_field(page, spec)
        if extraction_mode == "posterVideo":
            return self._extract_poster_video_field(page, spec)
        if extraction_mode == "items":
            return self._extract_items_field(page, spec)

        selector = spec["selector"]
        selector_type = self._field_option(spec, "selector_type", "selectorType", "css")
        attribute = spec.get("attribute", "text")
        multiple = bool(spec.get("multiple", False))
        values = self._extract_all(page, selector, attribute, selector_type)
        if multiple:
            return values
        return values[0] if values else None

    def _extract_items_field(self, page: Any, spec: dict[str, Any]) -> list[dict[str, str]]:
        """Estrae oggetti usando selettori relativi al rispettivo container."""
        container_selector = self._field_option(spec, "container_selector", "containerSelector")
        container_selector_type = self._field_option(
            spec, "container_selector_type", "containerSelectorType", "css"
        )
        item_fields = self._field_option(spec, "item_fields", "itemFields", {})
        items: list[dict[str, str]] = []
        for container in self._select_elements(page, container_selector, container_selector_type):
            item: dict[str, str] = {}
            for name, item_spec in item_fields.items():
                values = self._extract_all(
                    container,
                    self._field_option(item_spec, "selector", "selector"),
                    self._field_option(item_spec, "attribute", "attribute", "text"),
                    self._field_option(item_spec, "selector_type", "selectorType", "css"),
                )
                if values:
                    item[name] = values[0]
            if item:
                items.append(item)
        return items

    @staticmethod
    def _value_fingerprint(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def _merge_paginated_value(
        cls, aggregate: Any, value: Any, extraction_mode: str, max_items: int
    ) -> tuple[Any, bool]:
        """Unisce una pagina, preservando ordine e primo valore incontrato."""
        if extraction_mode == "keyValue":
            merged = dict(aggregate or {})
            for key, item in (value or {}).items():
                if key not in merged and len(merged) < max_items:
                    merged[key] = item
            return merged, len(merged) >= max_items

        merged = list(aggregate or [])
        fingerprints = {cls._value_fingerprint(item) for item in merged}
        for item in value or []:
            fingerprint = cls._value_fingerprint(item)
            if fingerprint in fingerprints:
                continue
            if len(merged) >= max_items:
                return merged, True
            merged.append(item)
            fingerprints.add(fingerprint)
        return merged, len(merged) >= max_items

    def _add_field_pagination_warning(self, field_name: str, reason: str) -> None:
        self.field_pagination_warnings.append(
            f"Paginazione incompleta per il campo '{field_name}' ({reason})."
        )

    async def _extract_paginated_field(
        self, url: str, field_name: str, spec: dict[str, Any], initial_value: Any
    ) -> Any:
        """Raccoglie un campo su piu stati DOM in una pagina browser isolata."""
        from scrapling.parser import Selector

        from app.services.robots_check import is_allowed

        pagination = self._field_option(spec, "pagination", "pagination", {})
        next_selector = self._field_option(pagination, "next_selector", "nextSelector")
        next_selector_type = self._field_option(
            pagination, "next_selector_type", "nextSelectorType", "css"
        )
        max_pages = int(self._field_option(pagination, "max_pages", "maxPages", 10))
        max_items = int(self._field_option(pagination, "max_items", "maxItems", 1000))
        extraction_mode = self._field_option(spec, "extraction_mode", "extractionMode", "value")
        aggregate, limit_reached = self._merge_paginated_value(
            {} if extraction_mode == "keyValue" else [],
            initial_value,
            extraction_mode,
            max_items,
        )
        diagnostic = FieldPaginationDiagnostic(items_collected=len(aggregate))
        self.field_pagination_diagnostics[field_name] = diagnostic

        if limit_reached:
            diagnostic.pages_visited = 1
            diagnostic.stop_reason = "max_items"
            self._add_field_pagination_warning(field_name, diagnostic.stop_reason)
            return aggregate

        async def paginate(browser_page: Any) -> None:
            nonlocal aggregate

            async def extract_current() -> Any:
                document = Selector(await browser_page.content(), url=str(browser_page.url))
                return self._extract_field(document, spec)

            try:
                current_value = await extract_current()
                aggregate, reached = self._merge_paginated_value(
                    aggregate, current_value, extraction_mode, max_items
                )
                diagnostic.pages_visited = 1
                diagnostic.items_collected = len(aggregate)
                state = self._value_fingerprint(current_value)
                seen_states = {state}
                if reached:
                    diagnostic.stop_reason = "max_items"
                    return

                for _page_index in range(1, max_pages):
                    controls = browser_page.locator(
                        self._browser_selector(next_selector, next_selector_type)
                    )
                    count = await controls.count()
                    if count == 0:
                        diagnostic.stop_reason = "end_of_pagination"
                        diagnostic.complete = True
                        return
                    control_hrefs = await controls.evaluate_all(
                        "(elements) => elements.map((element) => element.getAttribute('href'))"
                    )
                    equivalent_next_url = self._equivalent_next_url(
                        str(browser_page.url), control_hrefs, count
                    )
                    if count > 1 and equivalent_next_url is None:
                        diagnostic.stop_reason = "ambiguous_next_control"
                        return

                    control = await self._first_available_control(controls, count)
                    if control is None:
                        diagnostic.stop_reason = "next_control_unavailable"
                        diagnostic.complete = True
                        return

                    before_url = str(browser_page.url)
                    before_state = state
                    href = equivalent_next_url or await control.get_attribute("href")
                    await asyncio.sleep(self.rate_limit_seconds)
                    if href:
                        next_url = urldefrag(urljoin(before_url, href)).url
                        diagnostic.pagination_mode = "href"
                        if not self._same_origin(url, next_url):
                            diagnostic.stop_reason = "cross_origin_blocked"
                            return
                        if not is_allowed(self._robots_txt, next_url, self.user_agent):
                            diagnostic.stop_reason = "robots_disallowed"
                            return
                        await browser_page.goto(
                            next_url,
                            wait_until="domcontentloaded",
                            timeout=_BROWSER_NAVIGATION_TIMEOUT_MS,
                        )
                        current_value = await extract_current()
                    else:
                        diagnostic.pagination_mode = "click"
                        await control.evaluate("(element) => element.click()")
                        deadline = time.monotonic() + (_PAGINATION_CHANGE_TIMEOUT_MS / 1000)
                        while True:
                            current_value = await extract_current()
                            state = self._value_fingerprint(current_value)
                            if str(browser_page.url) != before_url or state != before_state:
                                break
                            if time.monotonic() >= deadline:
                                diagnostic.stop_reason = "page_did_not_change"
                                return
                            await asyncio.sleep(0.2)

                    state = self._value_fingerprint(current_value)
                    diagnostic.pages_visited += 1
                    if state in seen_states:
                        diagnostic.stop_reason = "repeated_content"
                        return
                    seen_states.add(state)
                    aggregate, reached = self._merge_paginated_value(
                        aggregate, current_value, extraction_mode, max_items
                    )
                    diagnostic.items_collected = len(aggregate)
                    if reached:
                        diagnostic.stop_reason = "max_items"
                        return

                diagnostic.stop_reason = "max_pages"
            except Exception:  # noqa: BLE001 - diagnostica senza URL o contenuto target
                diagnostic.stop_reason = "pagination_failed"

        async def fetch_with_action() -> None:
            session = await self._ensure_browser_session()
            kwargs = self._browser_request_kwargs()
            kwargs["page_action"] = paginate
            response = await session.fetch(url, **kwargs)
            self._raise_for_status(response, url)

        try:
            await asyncio.sleep(self.rate_limit_seconds)
            await self._with_proxy_rotation("field_pagination", fetch_with_action)
        except Exception:  # noqa: BLE001 - il valore iniziale resta utilizzabile
            if diagnostic.stop_reason == "not_started":
                diagnostic.stop_reason = "pagination_failed"

        diagnostic.items_collected = len(aggregate)
        if diagnostic.stop_reason == "not_started":
            diagnostic.stop_reason = "pagination_failed"
        if not diagnostic.complete:
            self._add_field_pagination_warning(field_name, diagnostic.stop_reason)
        return aggregate

    @staticmethod
    def _field_option(spec: dict[str, Any], snake: str, camel: str, default: Any = None) -> Any:
        return spec.get(snake, spec.get(camel, default))

    @staticmethod
    def normalize_pair_key(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
        normalized = re.sub(r"[^a-z0-9]+", "_", without_accents.lower()).strip("_")
        return {"age": "eta", "eta": "eta"}.get(normalized, normalized)

    def _extract_key_value_field(self, page: Any, spec: dict[str, Any]) -> dict[str, str]:
        container_selector = self._field_option(spec, "container_selector", "containerSelector")
        container_selector_type = self._field_option(
            spec, "container_selector_type", "containerSelectorType", "css"
        )
        key_selector = self._field_option(spec, "key_selector", "keySelector")
        key_selector_type = self._field_option(spec, "key_selector_type", "keySelectorType", "css")
        value_selector = self._field_option(spec, "value_selector", "valueSelector")
        value_selector_type = self._field_option(
            spec, "value_selector_type", "valueSelectorType", "css"
        )
        key_attribute = self._field_option(spec, "key_attribute", "keyAttribute", "text")
        value_attribute = self._field_option(spec, "value_attribute", "valueAttribute", "text")
        pairs: dict[str, str] = {}
        for container in self._select_elements(page, container_selector, container_selector_type):
            keys = self._extract_all(container, key_selector, key_attribute, key_selector_type)
            values = self._extract_all(
                container, value_selector, value_attribute, value_selector_type
            )
            if not keys or not values:
                continue
            key = self.normalize_pair_key(keys[0])
            if key and key not in pairs:
                pairs[key] = values[0]
        return pairs

    def _extract_poster_video_field(self, page: Any, spec: dict[str, Any]) -> list[dict[str, str]]:
        container_selector = self._field_option(spec, "container_selector", "containerSelector")
        container_selector_type = self._field_option(
            spec, "container_selector_type", "containerSelectorType", "css"
        )
        poster_selector = self._field_option(spec, "poster_selector", "posterSelector")
        poster_selector_type = self._field_option(
            spec, "poster_selector_type", "posterSelectorType", "css"
        )
        video_selector = self._field_option(spec, "video_selector", "videoSelector")
        video_selector_type = self._field_option(
            spec, "video_selector_type", "videoSelectorType", "css"
        )
        poster_attribute = self._field_option(spec, "poster_attribute", "posterAttribute", "src")
        video_attribute = self._field_option(spec, "video_attribute", "videoAttribute", "src")
        pairs: list[dict[str, str]] = []
        for container in self._select_elements(page, container_selector, container_selector_type):
            posters = self._extract_all(
                container, poster_selector, poster_attribute, poster_selector_type
            )
            videos = self._extract_all(
                container, video_selector, video_attribute, video_selector_type
            )
            if posters and videos:
                pairs.append({"poster": posters[0], "video": videos[0]})
        return pairs

    def media_extraction_warnings(self, ad: dict[str, Any]) -> list[str]:
        """Segnala campi media configurati che non hanno estratto URL."""
        fields = self._config_value("fields", "fields", {})
        warnings: list[str] = []
        for field_name, label in (("images", "immagine"), ("videos", "video")):
            if field_name in fields and not ad.get(field_name):
                warnings.append(
                    f"Nessun URL {label} trovato dal selettore configurato per '{field_name}'."
                )
        return warnings

    @staticmethod
    def _safe_media_error(exc: Exception) -> str:
        if isinstance(exc, RobotsDisallowedError):
            return "Download media vietato da robots.txt."
        if isinstance(exc, httpx.HTTPStatusError):
            return f"Il server media ha risposto HTTP {exc.response.status_code}."
        if isinstance(exc, httpx.TimeoutException):
            return "Timeout durante il download media."
        if isinstance(exc, httpx.HTTPError):
            return "Errore HTTP durante il download media."
        if isinstance(exc, PageFetchError):
            safe_messages = (
                "URL media non HTTP(S).",
                "Host media non risolvibile.",
                "URL media verso rete privata o riservata bloccato.",
                "Redirect media senza Location.",
                "Media oltre il limite massimo.",
                "Risposta media troncata rispetto a Content-Length.",
                "Troppi redirect durante il download media.",
            )
            message = str(exc)
            return message if message in safe_messages else "Download media non riuscito."
        return "Errore inatteso durante il download media."

    async def download_media(self, ad: dict[str, Any]) -> MediaDownloadResult:
        media_urls = [*(ad.get("images") or []), *(ad.get("videos") or [])]
        result = MediaDownloadResult(attempted_count=len(media_urls))
        for media_url in media_urls:
            try:
                await self._ensure_robots_loaded()
                from app.services.robots_check import is_allowed

                absolute_url = urljoin(self.base_url, media_url)
                if not is_allowed(self._robots_txt, absolute_url, self.user_agent):
                    raise RobotsDisallowedError(absolute_url)

                await asyncio.sleep(self.rate_limit_seconds)
                result.media_bytes.append(
                    await self._with_proxy_rotation(
                        "media",
                        lambda absolute_url=absolute_url: self._download_media_stream(absolute_url),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - download best-effort per singolo media
                # Non loggare l'eccezione o l'URL media: possono contenere token.
                logger.warning(
                    "Download media fallito per la fonte '%s' (%s).",
                    self.slug,
                    type(exc).__name__,
                )
                result.failures.append(MediaDownloadFailure(self._safe_media_error(exc)))
        return result

    @staticmethod
    async def _assert_public_url(url: str) -> None:
        from app.config import settings

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise PageFetchError("URL media non HTTP(S).")
        loop = asyncio.get_running_loop()
        try:
            addresses = await loop.run_in_executor(
                None, lambda: socket.getaddrinfo(parsed.hostname, parsed.port or 443)
            )
        except socket.gaierror as exc:
            raise PageFetchError("Host media non risolvibile.") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global and settings.ENVIRONMENT != "test":
                raise PageFetchError("URL media verso rete privata o riservata bloccato.")

    async def _download_media_stream(self, url: str) -> bytes:
        """Bounded streaming download with DNS/redirect SSRF checks."""
        from app.config import settings
        from app.services.media_storage import sniff_mime_type

        current = url
        limit = settings.MEDIA_VIDEO_MAX_BYTES
        proxy = self._active_proxy()
        if proxy is not None and proxy.scheme == "socks4":
            return await self._download_media_stream_socks4(current, limit, proxy)
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            proxy=proxy.httpx_url() if proxy else None,
        ) as client:
            for _ in range(6):
                await self._assert_public_url(current)
                async with client.stream(
                    "GET",
                    current,
                    headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"},
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise PageFetchError("Redirect media senza Location.")
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    declared = int(response.headers.get("content-length") or 0)
                    if declared > limit:
                        raise PageFetchError("Media oltre il limite massimo.")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) >= 12:
                            if sniff_mime_type(body).startswith("image/"):
                                limit = settings.MEDIA_IMAGE_MAX_BYTES
                        if len(body) > limit:
                            raise PageFetchError("Media oltre il limite massimo.")
                    if declared and len(body) != declared:
                        raise PageFetchError("Risposta media troncata rispetto a Content-Length.")
                    return bytes(body)
        raise PageFetchError("Troppi redirect durante il download media.")

    async def _download_media_stream_socks4(
        self, url: str, limit: int, proxy: ProxyRuntimeConfig
    ) -> bytes:
        """Bounded SOCKS4 download using libcurl (unsupported by httpx)."""
        from app.services.media_storage import sniff_mime_type

        current = url
        async with CurlAsyncSession() as client:
            for _ in range(6):
                await self._assert_public_url(current)
                state: dict[str, Any] = {
                    "body": bytearray(),
                    "limit": limit,
                    "exceeded": False,
                }

                def receive(chunk: bytes, state: dict[str, Any] = state) -> None:
                    body = state["body"]
                    body.extend(chunk)
                    if len(body) >= 12 and sniff_mime_type(body).startswith("image/"):
                        from app.config import settings

                        state["limit"] = settings.MEDIA_IMAGE_MAX_BYTES
                    if len(body) > state["limit"]:
                        state["exceeded"] = True
                        raise RuntimeError("bounded_media_limit")

                try:
                    response = await client.get(
                        current,
                        headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"},
                        allow_redirects=False,
                        timeout=_REQUEST_TIMEOUT_SECONDS,
                        proxy=proxy.httpx_url(),
                        content_callback=receive,
                    )
                except Exception as exc:
                    if state["exceeded"]:
                        raise PageFetchError("Media oltre il limite massimo.") from exc
                    raise
                body = state["body"]
                limit = state["limit"]
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise PageFetchError("Redirect media senza Location.")
                    current = urljoin(current, location)
                    continue
                if response.status_code in {403, 407, 429}:
                    raise ProxyRetryableError(f"http_{response.status_code}")
                if response.status_code >= 400:
                    synthetic = httpx.Response(
                        response.status_code,
                        request=httpx.Request("GET", current),
                    )
                    synthetic.raise_for_status()
                declared = int(response.headers.get("content-length") or 0)
                if declared > limit:
                    raise PageFetchError("Media oltre il limite massimo.")
                if declared and len(body) != declared:
                    raise PageFetchError("Risposta media troncata rispetto a Content-Length.")
                return bytes(body)
        raise PageFetchError("Troppi redirect durante il download media.")

    def normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        configured_fields = self._config_value("fields", "fields", {})
        custom_fields = {
            field_name: data.get(field_name)
            for field_name in configured_fields
            if field_name not in _STANDARD_FIELDS
        }
        return {
            "title": (data.get("title") or "").strip() or None,
            "description": (data.get("description") or "").strip() or None,
            "phone_raw": data.get("phone"),
            "source_url": data.get("source_url"),
            "images": data.get("images") or [],
            "videos": data.get("videos") or [],
            # Missing selectors remain explicit null values so consumers can
            # distinguish "configured but absent" from "not configured".
            "custom_fields": custom_fields,
        }

    async def aclose(self) -> None:
        try:
            await self._close_browser_session()
        finally:
            if self._client is not None:
                await self._client.aclose()
                self._client = None
