"""Offline Gemini configuration preparation. Execution is intentionally unavailable."""
from config import get_gemini_config


def validate_configuration() -> dict[str, str | bool]:
    """Return non-secret readiness metadata; syntax does not prove account access."""
    settings = get_gemini_config()
    return {"provider": "gemini", "model": settings["model"],
            "configured": True, "execution_available": False}
