"""Load and validate local MySQL settings without displaying secrets."""
import os
from pathlib import Path

from dotenv import load_dotenv


def get_database_config() -> dict[str, str | int]:
    """Read .env beside this module; existing environment values take precedence."""
    load_dotenv(Path(__file__).resolve().parent / ".env")
    settings = {}
    for name in ("DB_HOST", "DB_USER", "DB_NAME"):
        value = os.getenv(name, "").strip()
        if not value:
            raise ValueError(f"{name} is required")
        settings[name] = value
    password = os.getenv("DB_PASSWORD")
    if password is None:
        raise ValueError("DB_PASSWORD must be set (an empty value is allowed)")
    try:
        port = int(os.getenv("DB_PORT", "3306"))
    except ValueError:
        raise ValueError("DB_PORT must be an integer from 1 to 65535") from None
    if not 1 <= port <= 65535:
        raise ValueError("DB_PORT must be an integer from 1 to 65535")
    return {
        "host": settings["DB_HOST"], "port": port,
        "user": settings["DB_USER"], "password": password,
        "database": settings["DB_NAME"],
    }


def get_scraper_config() -> dict[str, str]:
    """Read credentials for the standard HTTPS HTML endpoint only."""
    from urllib.parse import urlsplit

    load_dotenv(Path(__file__).resolve().parent / ".env")
    key = os.getenv("SCRAPER_API_KEY", "").strip()
    if not key:
        raise ValueError("SCRAPER_API_KEY is required")
    base = os.getenv("SCRAPER_API_BASE_URL", "https://api.scraperapi.com").strip()
    try:
        parts = urlsplit(base)
        port = parts.port
    except ValueError:
        raise ValueError("SCRAPER_API_BASE_URL must be the standard HTTPS ScraperAPI endpoint") from None
    if (parts.scheme != "https" or parts.hostname != "api.scraperapi.com"
            or parts.path not in ("", "/") or parts.query or parts.fragment
            or parts.username or parts.password or port not in (None, 443)):
        raise ValueError("SCRAPER_API_BASE_URL must be the standard HTTPS ScraperAPI endpoint")
    return {"api_key": key, "base_url": base}


def get_search_fetcher() -> str:
    """Choose the configured fetcher, defaulting to direct HTTP without an API key."""
    load_dotenv(Path(__file__).resolve().parent / ".env")
    fetcher = os.getenv("SEARCH_FETCHER", "direct").strip().lower()
    if fetcher not in {"direct", "scraperapi"}:
        raise ValueError("SEARCH_FETCHER must be direct or scraperapi")
    return fetcher
