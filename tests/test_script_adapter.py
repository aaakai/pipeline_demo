import pytest

from app.llm.script_adapter import (
    build_manifest_heuristic,
    build_manifest_llm,
)


def test_heuristic_manifest_valid() -> None:
    manifest = build_manifest_heuristic(
        title="Demo",
        source_url="https://example.com/story",
        cleaned_text='She paused.\n\n"Hello," he said.\n\nThe lights dimmed.',
    )
    assert manifest.title == "Demo"
    assert manifest.segments
    assert manifest.characters[0].name == "NARRATOR"


def test_llm_manifest_valid_with_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_call(**kwargs: str) -> str:
        return """
        {
          "title": "Demo",
          "source_url": "https://example.com/story",
          "language": "en",
          "characters": [{"name": "NARRATOR", "voice_hint": "neutral"}],
          "segments": [{"id": 1, "speaker": "NARRATOR", "text": "Scene opens.", "emotion": "neutral", "pause_ms": 300}]
        }
        """

    monkeypatch.setattr("app.llm.script_adapter._call_openai_compatible", fake_call)
    manifest = build_manifest_llm(
        title="Demo",
        source_url="https://example.com/story",
        cleaned_text="Scene opens.",
        api_key="key",
        base_url="https://api.example.com/v1",
        model="demo-model",
        timeout_seconds=20,
    )
    assert manifest.segments[0].speaker == "NARRATOR"
