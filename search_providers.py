"""Small provider registry: each fetch_page returns (observations, next offset)."""
import bing_search
import google_search
import engine_search
from functools import partial

# Default Bing CLI remains direct; the GUI explicitly selects ScraperAPI.
PROVIDERS = {
    "google": ("google:scraperapi:structured", "scraperapi", google_search.fetch_page),
    "bing": ("bing:direct:html", "direct", bing_search.fetch_page),
}


def get_provider(engine: str, fetcher: str | None = None) -> tuple:
    """Reject unsupported paths rather than silently selecting a fallback."""
    if fetcher == 'scraperapi' and engine in {'bing','yahoo','duckduckgo'}:
        return f'{engine}:scraperapi:html', 'scraperapi', partial(engine_search.fetch_page, engine)
    if engine not in PROVIDERS:
        raise ValueError("Supported engines: google (primary), bing (legacy CLI)")
    provider_id, method, fetch_page = PROVIDERS[engine]
    if fetcher is not None and fetcher != method:
        raise ValueError(f"{engine} supports only {method} retrieval")
    return provider_id, method, fetch_page
