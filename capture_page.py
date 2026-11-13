"""One optional Playwright screenshot of a rendered Bing search-results page."""
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit


class CaptureError(Exception):
    """A credential-free capture or OCR error suitable for the CLI."""


def capture_search_page(query: str, destination: Path) -> Path:
    """Navigate once, reject challenges, and screenshot visible result cards."""
    from playwright.sync_api import Error, sync_playwright

    if destination.exists():
        raise CaptureError("Screenshot destination already exists; refusing to overwrite it")
    url = "https://www.bing.com/search?" + urlencode({"q": query})
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
                if (final.hostname != "www.bing.com" or final.path != "/search"
                        or parse_qs(final.query).get("q") != [query]):
                    raise CaptureError("Capture navigation left the expected Bing search/query")
                challenge = page.locator('#b_captcha, #captcha, .g-recaptcha, iframe[src*="captcha"], form[action*="challenge"]')
                if challenge.count() and challenge.first.is_visible():
                    raise CaptureError("Capture stopped at a CAPTCHA or verification challenge")
                page.locator("#b_results li.b_algo h2 a[href]").first.wait_for(state="visible", timeout=10000)
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
