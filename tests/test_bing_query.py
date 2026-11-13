"""Protect exact assignment query encoding without network requests."""
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

import bing_search


@pytest.mark.parametrize("query", [
    "childhood cancer early diagnosis methods",
    "b) Childhood cancer early diagnosis methods",
])
@pytest.mark.parametrize("offset", [0, 11])
def test_bing_preserves_complete_query_and_page_offset(monkeypatch, query, offset):
    def respond(url, **kwargs):
        request = httpx.Request("GET", url, params=kwargs["params"])
        assert parse_qs(request.url.query.decode())["q"] == [query]
        assert request.url.params["first"] == str(offset or 1)
        if query.startswith("b)"):
            assert "b%29+Childhood" in str(request.url)
        return httpx.Response(200, text="Fixture response")
    monkeypatch.setattr(httpx, "get", respond)
    assert bing_search.fetch_html(query, offset) == "Fixture response"


def test_observed_prefixed_results_are_supported_without_parser_changes():
    html = (Path(__file__).parent / "fixtures" / "bing_prefixed_results.html").read_text()
    rows = bing_search.parse_results(html)
    assert len(rows) == 5
    assert rows[0]["title"].startswith("Early diagnosis of cancer in children and adolescents")
    assert rows[2]["title"] == "Early Diagnosis of Childhood Cancer Manual - ICCP Portal"
    assert rows[4]["original_url"] == "https://onlinelibrary.wiley.com/doi/10.1002/pbc.31702"
