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
    """Read credentials for the configured ScraperAPI HTTPS origin."""
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


def get_collection_page_limit() -> int:
    """Read a default collection budget of ten pages, bounded to 1–50."""
    load_dotenv(Path(__file__).resolve().parent / ".env")
    try:
        value = int(os.getenv("COLLECTION_MAX_PAGES", "10"))
    except ValueError:
        raise ValueError("COLLECTION_MAX_PAGES must be an integer from 1 to 50") from None
    if not 1 <= value <= 50:
        raise ValueError("COLLECTION_MAX_PAGES must be an integer from 1 to 50")
    return value


def get_gemini_config() -> dict[str, str]:
    """Validate server-only settings locally; never contact Gemini or echo a key."""
    load_dotenv(Path(__file__).resolve().parent / ".env")
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY is required")
    model = get_gemini_model()
    return {"api_key": key, "model": model}


def get_gemini_model() -> str:
    """Read a requested model without requiring credentials for cached reads."""
    import re
    load_dotenv(Path(__file__).resolve().parent / ".env")
    model = os.getenv("GEMINI_MODEL", "").strip()
    if not re.fullmatch(r"gemini-[a-zA-Z0-9][a-zA-Z0-9._-]{0,90}", model):
        raise ValueError("GEMINI_MODEL must be an explicitly configured Gemini model identifier")
    return model
