"""Primary structured Google JSON provider; no direct HTML or fallback requests."""
from config import get_scraper_config


class SearchError(Exception):
    """Safe retrieval/processing error without request URLs or credentials."""


def fetch_results(query: str, start: int = 0) -> dict:
    """Get one structured Google JSON page, preserving the exact submitted query."""
    import requests

    settings = get_scraper_config()
    try:
        response = requests.get(
            settings["base_url"].rstrip("/") + "/structured/google/search/v1",
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


def fetch_page(query: str, start: int = 0) -> tuple[list[dict], int | None]:
    """Provider interface consumed by the one shared ETL workflow."""
    data = fetch_results(query, start=start)
    return parse_organic_results(data), next_results_start(data, start)
