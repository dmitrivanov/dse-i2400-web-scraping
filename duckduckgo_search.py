"""DuckDuckGo's public non-JavaScript HTML interface and result-card parser."""
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import httpx

from google_search import SearchError

ENDPOINT = "https://html.duckduckgo.com/html/"


def fetch_html(query: str, start: dict | int = 0) -> str:
    """Fetch one page, optionally submitting fields from an observed Next form."""
    params = {"q": query}
    method = "get"
    if isinstance(start, dict):
        params.update(start["params"])
        params["q"] = query
        method = start["method"]
    try:
        kwargs = {"params" if method == "get" else "data": params}
        request = httpx.get if method == "get" else httpx.post
        response = request(
            ENDPOINT, **kwargs,
            headers={"User-Agent": "MY_CUSTOM_BOT/0.3 (CCNY DSE I2400 educational project)",
                     "Accept-Language": "en-US,en;q=0.9"},
            timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
        )
    except httpx.TimeoutException:
        raise SearchError("DuckDuckGo request timed out") from None
    except httpx.RequestError:
        raise SearchError("DuckDuckGo network request failed") from None
    if response.status_code != 200:
        raise SearchError(f"DuckDuckGo returned HTTP {response.status_code}; access unavailable, no retry attempted")
    if not response.text.strip():
        raise SearchError("DuckDuckGo returned an empty response")
    return response.text


def parse_results(html: str) -> list[dict]:
    """Classify recognized web-result and ad cards, preserving ambiguous cards."""
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one('#challenge-form, #anomaly-form, .anomaly-modal, .g-recaptcha'):
        raise SearchError("DuckDuckGo returned a human-verification challenge")
    rows = []
    for card in soup.select(".result"):
        link = card.select_one("a.result__a[href]")
        if link is None:
            continue
        classes = card.get("class", [])
        if "result--ad" in classes or card.select_one(".result__badge--ad"):
            is_ad = True
        elif "web-result" in classes or "results_links" in classes:
            is_ad = False
        else:
            is_ad = None
        snippet = card.select_one(".result__snippet")
        rows.append({"title": link.get_text(" ", strip=True) or None,
                     "original_url": link["href"],
                     "snippet": snippet.get_text(" ", strip=True) if snippet else None,
                     "result_rank": len(rows) + 1, "is_ad": is_ad})
    if not rows:
        raise SearchError("DuckDuckGo returned no supported result cards; inspect saved HTML")
    return rows


def next_page_start(html: str, query: str, current: dict | int) -> dict | None:
    """Preserve observed Next form fields without inventing pagination tokens."""
    soup = BeautifulSoup(html, "html.parser")
    for form in soup.select("form"):
        submit = form.select_one('input[type="submit"][value="Next"], button[type="submit"]')
        if submit is None or (submit.name == "button" and submit.get_text(strip=True) != "Next"):
            continue
        try:
            target = urlsplit(urljoin(ENDPOINT, form.get("action", "")))
            if (target.scheme != "https" or target.hostname != "html.duckduckgo.com"
                    or target.path.rstrip("/") != "/html" or target.username or target.password
                    or target.port not in (None, 443) or target.query or target.fragment):
                continue
        except ValueError:
            continue
        params = {field["name"]: field.get("value", "") for field in form.select('input[type="hidden"][name]')}
        method = form.get("method", "get").lower()
        if params.get("q") != query or method not in {"get", "post"}:
            continue
        try:
            previous = int(current["params"].get("s", "0")) if isinstance(current, dict) else 0
            offset = int(params.get("s", "0"))
        except ValueError:
            continue
        if previous < offset <= 100:
            return {"method": method, "params": params}
    return None
