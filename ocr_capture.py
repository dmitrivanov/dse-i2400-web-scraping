"""Local English OCR of an existing screenshot using Tesseract."""
from pathlib import Path

from capture_page import CaptureError


def extract_screenshot_text(screenshot: Path, destination: Path) -> Path:
    """Write real OCR text as UTF-8, without replacing an existing output file."""
    import pytesseract
    from PIL import Image

    if destination.exists():
        raise CaptureError("OCR destination already exists; refusing to overwrite it")
    try:
        with Image.open(screenshot) as image:
            text = pytesseract.image_to_string(image, lang="eng", timeout=60)
        if not text.strip():
            raise CaptureError("OCR produced no readable text; screenshot retained")
        with destination.open("x", encoding="utf-8") as output:
            output.write(text)
        return destination.resolve()
    except pytesseract.TesseractNotFoundError:
        raise CaptureError("Tesseract is not installed or not on PATH; screenshot retained") from None
    except (pytesseract.TesseractError, RuntimeError):
        raise CaptureError("Tesseract OCR failed or timed out; screenshot retained") from None
    except OSError:
        raise CaptureError("OCR could not read the screenshot or save its text; screenshot retained") from None
