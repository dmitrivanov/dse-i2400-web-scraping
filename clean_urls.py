"""Conservative URL normalization and per-run duplicate identification."""
import re
import base64
import binascii

from urllib.parse import parse_qs, unquote_plus, urljoin, urlsplit, urlunsplit

TRACKING = {"gclid", "dclid", "fbclid", "msclkid"}


def normalize_url(original: str) -> str | None:
    """Return a safe HTTP(S) URL, or None; retain path, fragment and query order."""
    if not original or any(ord(char) <= 32 or ord(char) == 127 for char in original):
        return None
    if not (original.lower().startswith(("http://", "https://"))
            or original.startswith(("//", "/url?", "/l/?", "/ck/a?"))):
        return None
    try:
        base = "https://www.google.com"
        if original.startswith("/l/?"):
            base = "https://duckduckgo.com"
        elif original.startswith("/ck/a?"):
            base = "https://www.bing.com"
        url = urljoin(base, original)
        parts = urlsplit(url)
        if parts.hostname in {"google.com", "www.google.com"} and parts.path == "/url":
            values = parse_qs(parts.query)
            url = values.get("q", values.get("url", [""]))[0]
            parts = urlsplit(url)
        elif parts.hostname in {"duckduckgo.com", "html.duckduckgo.com", "www.duckduckgo.com"} and parts.path == "/l/":
            url = parse_qs(parts.query).get("uddg", [""])[0]
            parts = urlsplit(url)
        elif parts.hostname in {"bing.com", "www.bing.com"} and parts.path == "/ck/a":
            value = parse_qs(parts.query).get("u", [""])[0]
            if value.startswith("a1"):
                encoded = value[2:]
                url = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True).decode("utf-8")
            else:
                url = value
            parts = urlsplit(url)
        if any(ord(char) <= 32 or ord(char) == 127 for char in url):
            return None
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return None
        if parts.hostname in {"google.com", "www.google.com"} and parts.path in {"/search", "/preferences", "/sorry/"}:
            return None
        if parts.username or parts.password or "\\" in url:
            return None
        host = parts.hostname.encode("idna").decode("ascii").lower()
        if not re.fullmatch(r"[a-z0-9.:-]+", host):
            return None
        if ":" in host:
            host = f"[{host}]"
        port = parts.port
        if port and (parts.scheme.lower(), port) not in {("https", 443), ("http", 80)}:
            host += f":{port}"
        # Retain original encoding/order of every non-tracking query component.
        query = "&".join(part for part in parts.query.split("&")
                         if unquote_plus(part.split("=", 1)[0]).lower() not in TRACKING
                         and not unquote_plus(part.split("=", 1)[0]).lower().startswith("utm_"))
        return urlunsplit((parts.scheme.lower(), host, parts.path or "/", query, parts.fragment))
    except (ValueError, UnicodeError, binascii.Error):
        return None


def clean_results(results: list[dict], preserve_urls: bool = False) -> tuple[list[dict], dict[str, int]]:
    """Choose one representative per valid URL, preferring a known organic row."""
    cleaned = []
    for row in results:
        original = row["original_url"]
        normalized = supplied_url(original) if preserve_urls else normalize_url(original)
        cleaned.append(dict(row, normalized_url=normalized))
    winners = {}
    for index, row in enumerate(cleaned):
        url = row["normalized_url"]
        if url is None:
            continue
        previous = winners.get(url)
        if previous is None or (row["is_ad"] is False and cleaned[previous]["is_ad"] is not False):
            winners[url] = index
    counts = {"raw_count": len(cleaned), "ad_count": 0, "duplicate_count": 0, "final_count": 0}
    for index, row in enumerate(cleaned):
        url = row["normalized_url"]
        row["is_duplicate"] = bool(url and winners[url] != index)
        counts["ad_count"] += row["is_ad"] is True
        counts["duplicate_count"] += row["is_duplicate"]
        if url and row["is_ad"] is False and not row["is_duplicate"]:
            counts["final_count"] += 1
    return cleaned, counts


def supplied_url(url: str) -> str | None:
    """Validate a supplied HTTP(S) link without decoding, rewriting, or resolving it."""
    try:
        parts = urlsplit(url)
        if (parts.scheme.lower() not in {"http", "https"} or not parts.hostname
                or parts.username or parts.password or "\\" in url
                or any(ord(char) <= 32 or ord(char) == 127 for char in url)):
            return None
        _ = parts.port  # Reject invalid port syntax without changing the supplied URL.
        return url
    except ValueError:
        return None
