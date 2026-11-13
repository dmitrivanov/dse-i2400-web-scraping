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
