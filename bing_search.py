"""Direct Bing retrieval, result-card extraction, and explicit next-page offsets."""
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup
import httpx

from google_search import SearchError


def fetch_html(query: str, start: int = 0) -> str:
    """Fetch once; report HTTP redirects/blocks without retrying or switching engines."""
    try:
        response = httpx.get(
            "https://www.bing.com/search", params={"q": query, "first": start or 1},
            headers={"User-Agent": "MY_CUSTOM_BOT/0.3 (CCNY DSE I2400 educational project)",
                     "Accept-Language": "en-US,en;q=0.9"},
            timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
        )
    except httpx.TimeoutException:
        raise SearchError("Bing request timed out") from None
    except httpx.RequestError:
        raise SearchError("Bing network request failed") from None
    if response.status_code != 200:
        raise SearchError(f"Bing returned HTTP {response.status_code}; no retry attempted")
    if not response.text.strip():
        raise SearchError("Bing returned an empty response")
    return response.text


def parse_results(html: str) -> list[dict]:
    """Extract only Bing result cards, not navigation or unrelated global links."""
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one('#b_captcha, #captcha, .g-recaptcha, form[action*="challenge"]'):
        raise SearchError("Bing returned a CAPTCHA or challenge page")
    rows = []
    for card in soup.select("#b_results li.b_algo, #b_results li.b_ad"):
        link = card.select_one("h2 a[href]")
        if link is None:
            continue
        snippet = card.select_one(".b_caption p")
        rows.append({"title": link.get_text(" ", strip=True) or None,
                     "original_url": link["href"],
                     "snippet": snippet.get_text(" ", strip=True) if snippet else None,
                     "result_rank": len(rows) + 1,
                     "is_ad": "b_ad" in card.get("class", [])})
    if not rows:
        raise SearchError("Bing returned no supported result cards; inspect saved HTML")
    return rows


def next_page_start(html: str, query: str, current: int) -> int | None:
    """Accept only a same-query next link on the Bing search endpoint."""
    soup = BeautifulSoup(html, "html.parser")
    link = soup.select_one("a.sb_pagN[href]")
    if link is None:
        return None
    try:
        parts = urlsplit(urljoin("https://www.bing.com", link["href"]))
        params = parse_qs(parts.query)
        offset = int(params.get("first", [""])[0])
        if (parts.scheme == "https" and parts.hostname == "www.bing.com"
                and not parts.username and not parts.password and parts.port in (None, 443)
                and parts.path == "/search" and params.get("q") == [query]
                and current < offset <= 100):
            return offset
    except ValueError:
        pass
    return None


def fetch_scraper_html(query: str, start: int = 0) -> str:
    """Use paid HTML retrieval only when the caller explicitly selects it."""
    from config import get_scraper_config
    from scraper_api import fetch_target_html

    target = "https://www.bing.com/search?" + urlencode({"q": query, "first": start or 1})
    return fetch_target_html(target, get_scraper_config())
