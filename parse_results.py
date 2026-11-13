"""Conservative, provisional Google selectors; live HTML validation is pending."""
from bs4 import BeautifulSoup

from google_search import SearchError


def parse_results(html: str) -> list[dict]:
    """Extract linked h3 observations; classify only recognized result containers."""
    soup = BeautifulSoup(html, "html.parser")
    if (soup.select_one('form[action*="/sorry"], #captcha, .g-recaptcha')
            or soup.select_one('form[action*="consent.google"]')
            or (soup.title and any(text in soup.title.get_text().lower()
                                  for text in ("before you continue", "unusual traffic", "access denied")))):
        raise SearchError("Google returned a CAPTCHA, consent, or blocked page")
    results = []
    for heading in soup.select("h3"):
        link = heading.find_parent("a", href=True)
        if link is None:
            continue
        ancestors = list(heading.parents)
        ad = next((node for node in ancestors if node.get("id") in {"tads", "bottomads"}
                   or node.has_attr("data-text-ad")), None)
        organic = heading.find_parent(class_="g")
        if organic is None and heading.find_parent(class_="yuRUbf"):
            organic = heading.find_parent(class_="MjjYud")
        container = ad or organic
        # Unrecognized linked headings remain observations with unknown ad status.
        is_ad = True if ad else (False if organic else None)
        snippet = container.select_one(".VwiC3b, .IsZvec") if container else None
        results.append({"title": heading.get_text(" ", strip=True) or None,
                        "original_url": link["href"],
                        "snippet": snippet.get_text(" ", strip=True) if snippet else None,
                        "result_rank": len(results) + 1, "is_ad": is_ad})
    if not results:
        if soup.select_one('a[href^="/httpservice/retry/enablejs"]'):
            raise SearchError("Google returned a JavaScript-required redirect shell; no search results")
        raise SearchError("No supported linked result headings found; inspect the saved HTML")
    return results


def next_page_start(html: str, query: str, current: int) -> int | None:
    """Use an explicit Google Next link rather than inventing page offsets."""
    from urllib.parse import parse_qs, urljoin, urlsplit

    soup = BeautifulSoup(html, "html.parser")
    link = soup.select_one("a#pnnext[href], a[rel~=next][href]")
    if link is None:
        return None
    try:
        parts = urlsplit(urljoin("https://www.google.com", link["href"]))
        values = parse_qs(parts.query)
        start = int(values.get("start", [""])[0])
        if (parts.scheme == "https" and parts.hostname == "www.google.com"
                and not parts.username and not parts.password and parts.port in (None, 443)
                and parts.path == "/search" and values.get("q") == [query]
                and current < start <= 100):
            return start
    except ValueError:
        pass
    return None
