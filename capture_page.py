"""Explicit authentic provider-page screenshots; no reconstructed result pages."""
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit


class CaptureError(Exception):
    """A credential-free capture or OCR error suitable for the CLI."""


def capture_search_page(query: str, destination: Path, engine: str = "bing") -> Path:
    """Navigate once, reject challenges, and screenshot visible result cards."""
    from playwright.sync_api import Error, sync_playwright

    if destination.exists():
        raise CaptureError("Screenshot destination already exists; refusing to overwrite it")
    if engine not in {"google", "bing"}:
        raise CaptureError("Authentic capture supports Google or Bing only")
    host = "www.google.com" if engine == "google" else "www.bing.com"
    url = f"https://{host}/search?" + urlencode({"q": query})
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
                response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if response is None or response.status != 200:
                    raise CaptureError("Capture navigation did not return HTTP 200")
                final = urlsplit(page.url)
                if (final.hostname != host or final.path != "/search"
                        or parse_qs(final.query).get("q") != [query]):
                    raise CaptureError("Capture navigation left the expected provider search/query")
                challenge = page.locator('#b_captcha, #captcha, .g-recaptcha, iframe[src*="captcha"], form[action*="challenge"]')
                if challenge.count() and challenge.first.is_visible():
                    raise CaptureError("Capture stopped at a CAPTCHA or verification challenge")
                title = page.title().lower()
                if any(marker in title for marker in ("before you continue", "unusual traffic", "access denied")):
                    raise CaptureError("Capture stopped at a consent or verification page")
                selector = "#search a h3, #rso a h3" if engine == "google" else "#b_results li.b_algo h2 a[href]"
                page.locator(selector).first.wait_for(state="visible", timeout=10000)
                text = page.locator("body").inner_text(timeout=5000).lower()
                if any(marker in text for marker in ("verify you are human", "verify that you are human", "unusual traffic", "complete the challenge")):
                    raise CaptureError("Capture stopped at a CAPTCHA or verification challenge")
                page.screenshot(path=str(destination), full_page=True, animations="disabled", timeout=15000)
            finally:
                browser.close()
        if not destination.is_file() or destination.stat().st_size == 0:
            raise CaptureError("Screenshot file was not created")
        return destination.resolve()
    except Error:
        raise CaptureError("Browser capture failed: check Chromium installation, network access, and visible result cards") from None
    except OSError:
        raise CaptureError("Screenshot could not be saved to the artifacts directory") from None
