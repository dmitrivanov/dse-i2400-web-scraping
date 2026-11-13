"""Explicit paid HTML retrieval shared by the supported search engines."""
import httpx


def fetch_target_html(target_url: str, settings: dict[str, str]) -> str:
    """Retrieve one target page without retries, logging URLs, or exposing the key."""
    from google_search import SearchError

    try:
        response = httpx.get(
            settings["base_url"], params={"api_key": settings["api_key"], "url": target_url},
            timeout=httpx.Timeout(60, connect=10), follow_redirects=False,
        )
    except httpx.TimeoutException:
        raise SearchError("ScraperAPI request timed out") from None
    except httpx.RequestError:
        raise SearchError("ScraperAPI network request failed") from None
    if response.status_code != 200:
        raise SearchError(f"ScraperAPI returned HTTP {response.status_code}")
    html = response.text.replace(settings["api_key"], "[REDACTED]")
    if not html.strip():
        raise SearchError("ScraperAPI returned an empty response")
    return html
