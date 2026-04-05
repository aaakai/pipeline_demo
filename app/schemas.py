"""Pydantic schemas used across the application."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class Character(BaseModel):
    name: str
    voice_hint: str = "neutral"


class ScriptSegment(BaseModel):
    id: int
    speaker: str
    text: str
    emotion: str = "neutral"
    pause_ms: int = 300


class ScriptManifest(BaseModel):
    title: str
    source_url: str
    language: Literal["en", "zh", "mixed"] = "mixed"
    characters: list[Character] = Field(default_factory=list)
    segments: list[ScriptSegment]


class ExtractedDocument(BaseModel):
    title: str
    source_url: str
    raw_html_path: str | None = None
    raw_text: str
    cleaned_text: str
    metadata: dict[str, str]


class ExtractionRequest(BaseModel):
    url: HttpUrl
    outdir: str | None = None


class ScriptRequest(ExtractionRequest):
    mode: Literal["heuristic", "llm"] = "heuristic"


class ExtractionResponse(BaseModel):
    title: str
    source_url: str
    cleaned_text: str
    metadata: dict[str, str]


class ScriptResponse(BaseModel):
    title: str
    source_url: str
    cleaned_text: str
    script_manifest: ScriptManifest


class RuntimeConfig(BaseModel):
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"
    timeout_seconds: int = 20
    max_retries: int = 1
    user_agent: str = (
        "pipeline-demo/0.1 (+https://example.invalid; single-url extractor)"
    )


class MetaRecord(BaseModel):
    title: str
    source_url: str
    site_type: str
    fetched_at: datetime
    mode: str | None = None
    raw_html_path: str | None = None
