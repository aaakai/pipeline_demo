from pathlib import Path

import pytest
from requests.models import Response

from app.exceptions import ExtractionError
from app.extractors.pipeline import extract_document


class DummyResponse(Response):
    def __init__(self, html: str, status_code: int = 200):
        super().__init__()
        self._content = html.encode("utf-8")
        self.status_code = status_code
        self.encoding = "utf-8"


def test_ao3_extraction(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ao3_html: str) -> None:
    monkeypatch.setattr(
        "app.extractors.pipeline.requests.get",
        lambda *args, **kwargs: DummyResponse(ao3_html),
    )
    document = extract_document(
        url="https://archiveofourown.org/works/123/chapters/456",
        outdir=tmp_path,
        user_agent="test-agent",
    )
    assert document.title == "AO3 Test Work"
    assert "Hello there" in document.raw_text
    assert "Opening note" not in document.raw_text
    assert "Ending note" not in document.raw_text
    assert "Should not be extracted" not in document.raw_text


def test_generic_extraction(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, generic_html: str) -> None:
    monkeypatch.setattr(
        "app.extractors.pipeline.requests.get",
        lambda *args, **kwargs: DummyResponse(generic_html),
    )
    document = extract_document(
        url="https://example.com/story",
        outdir=tmp_path,
        user_agent="test-agent",
    )
    assert document.title == "Example Article"
    assert "first paragraph" in document.raw_text


def test_empty_body_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    html = "<html><head><title>Empty</title></head><body><main></main></body></html>"
    monkeypatch.setattr(
        "app.extractors.pipeline.requests.get",
        lambda *args, **kwargs: DummyResponse(html),
    )
    with pytest.raises(ExtractionError):
        extract_document(
            url="https://example.com/empty",
            outdir=tmp_path,
            user_agent="test-agent",
        )
