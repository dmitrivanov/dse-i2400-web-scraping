import pytest
import run_search
from clean_urls import normalize_url, clean_results


@pytest.mark.parametrize("original, expected", [
    ("HTTPS://Example.COM:443/a?utm_source=x&ID=%2f#part", "https://example.com/a?ID=%2f#part"),
    ("https://example.com/?a=1&a=2&fbclid=x", "https://example.com/?a=1&a=2"),
    ("//EXAMPLE.com/a", "https://example.com/a"),
    ("/url?q=https%3A%2F%2Fexample.com%2Fa", "https://example.com/a"),
    ("https://example.com/a/../b", "https://example.com/a/../b"),
    ("javascript:alert(1)", None), ("https://u:p@example.com", None),
    ("https://example.com:bad/", None), ("https://example.com/a b", None),
    ("/search?q=example", None), ("", None),
])
def test_normalization(original, expected):
    assert normalize_url(original) == expected

def test_ad_and_unknown_do_not_claim_organic_url():
    rows = [{"original_url": "https://example.com", "is_ad": flag} for flag in [True, None, False, False]]
    _, counts = clean_results(rows)
    assert counts == {"raw_count": 4, "ad_count": 1, "duplicate_count": 3, "final_count": 1}

@pytest.mark.parametrize("query", ["childhood cancer early diagnosis methods", "the childhood cancer early diagnosis methods AND care"])
def test_valid_query(query):
    run_search.validate_query(query)

@pytest.mark.parametrize("query", ["", "the and OR not please", "childhood cancer diagnosis methods", "x" * 1001])
def test_invalid_query(query):
    with pytest.raises(ValueError):
        run_search.validate_query(query)

@pytest.mark.parametrize("url", ["relative/path", "https://bad%host.test", "ftp://example.org"])
def test_reject_unsafe_urls(url):
    assert normalize_url(url) is None
