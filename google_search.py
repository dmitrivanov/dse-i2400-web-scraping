"""Primary structured Google JSON retrieval, with legacy HTML diagnostic functions."""
from urllib.parse import urlencode

import httpx

from config import get_scraper_config


class SearchError(Exception):
    """A safe provider or extraction failure suitable for storage and display."""


def fetch_html(query: str, start: int = 0) -> str:
    """Fetch one page with no retries; Google start is a result offset."""
    settings = get_scraper_config()
    target = "https://www.google.com/search?" + urlencode({"q": query, "hl": "en", "start": start})
    from scraper_api import fetch_target_html

    return fetch_target_html(target, settings)


def fetch_direct_html(query: str, start: int = 0) -> str:
    """Request Google directly once, identifying this educational project honestly."""
    try:
        response = httpx.get(
            "https://www.google.com/search",
            params={"q": query, "hl": "en", "start": start},
            headers={"User-Agent": "MY_CUSTOM_BOT/0.2 (CCNY DSE I2400 educational project)",
                     "Accept-Language": "en-US,en;q=0.9"},
            timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
        )
    except httpx.TimeoutException:
        raise SearchError("Direct Google request timed out") from None
    except httpx.RequestError:
        raise SearchError("Direct Google network request failed") from None
    if response.status_code != 200:
        raise SearchError(f"Direct Google returned HTTP {response.status_code}; no retry or fallback attempted")
    html = response.text
    if not html.strip():
        raise SearchError("Direct Google returned HTTP 200 with an empty response")
    # Check recognizable challenges before passing HTML to the existing parser.
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    if (soup.select_one('form[action*="/sorry"], #captcha, .g-recaptcha, form[action*="consent.google"]')
            or (soup.title and any(marker in soup.title.get_text().lower()
                                  for marker in ("before you continue", "unusual traffic", "access denied")))):
        raise SearchError("Direct Google returned HTTP 200 with a consent, CAPTCHA, or access-denied page")
    return html


def fetch_results(query: str, start: int = 0) -> dict:
    """Get one structured Google JSON page, preserving the exact submitted query."""
    import requests

    settings = get_scraper_config()
    try:
        response = requests.get(
            settings["base_url"].rstrip("/") + "/structured/google/search",
            params={"api_key": settings["api_key"], "query": query, "start": start},
            timeout=(10, 60), allow_redirects=False,
        )
    except requests.Timeout:
        raise SearchError("Structured Google request timed out") from None
    except requests.RequestException:
        raise SearchError("Structured Google network request failed") from None
    if response.status_code != 200:
        raise SearchError(f"Structured Google returned HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        raise SearchError("Structured Google returned invalid JSON") from None
    if not isinstance(data, dict) or not isinstance(data.get("organic_results"), list):
        raise SearchError("Structured Google response is missing an organic_results list")
    return data


def parse_organic_results(data: dict) -> list[dict]:
    """Map only returned organic observations; keep supplied links and positions."""
    rows = []
    for item in data["organic_results"]:
        if not isinstance(item, dict) or not isinstance(item.get("link"), str) or not item["link"]:
            raise SearchError("Structured Google organic result is missing a URL")
        for field in ("title", "snippet"):
            if item.get(field) is not None and not isinstance(item[field], str):
                raise SearchError("Structured Google result contains an invalid text field")
        position = item.get("position")
        if position is not None and (type(position) is not int or position < 0):
            raise SearchError("Structured Google result contains an invalid position")
        rows.append({"title": item.get("title"), "original_url": item["link"],
                     "snippet": item.get("snippet"), "result_rank": position, "is_ad": False})
    return rows


def next_results_start(data: dict, current: int) -> int | None:
    """Advance by Google's documented default ten-result offset, within caller limit."""
    if not data["organic_results"]:
        return None
    pagination = data.get("pagination")
    if isinstance(pagination, dict) and "next_page_url" in pagination and not pagination["next_page_url"]:
        return None
    # Rebuild the structured request with start; never follow returned URLs/keys.
    return current + 10
