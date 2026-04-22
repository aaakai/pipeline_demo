"""OpenAI-compatible ASR for dialogue audio."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

from src.schemas import OpenAIASRConfig


def transcribe_audio(audio_path: str | Path, config: OpenAIASRConfig) -> dict[str, Any]:
    api_key = os.getenv(config.api_key_env)
    if not api_key:
        raise RuntimeError(f"ASR requires environment variable {config.api_key_env}.")
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Dialogue audio not found: {path}")

    endpoint = config.base_url.rstrip("/") + "/audio/transcriptions"
    with path.open("rb") as audio_file:
        files = {"file": (path.name, audio_file, _content_type(path))}
        data: dict[str, object] = {
            "model": config.model,
            "response_format": "verbose_json",
        }
        if config.language:
            data["language"] = config.language
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            data=data,
            timeout=config.timeout_seconds,
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"ASR request failed with HTTP {response.status_code}: {response.text[:1000]}"
        )
    payload = response.json()
    return _normalize_asr_payload(payload)


def _normalize_asr_payload(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text") or "").strip()
    segments = []
    for index, item in enumerate(payload.get("segments") or [], start=1):
        start = float(item.get("start") or 0.0)
        end = float(item.get("end") or start)
        segment_text = str(item.get("text") or "").strip()
        if not segment_text:
            continue
        segments.append(
            {
                "id": int(item.get("id", index)),
                "start_ms": int(start * 1000),
                "end_ms": int(end * 1000),
                "text": segment_text,
            }
        )
    return {
        "text": text,
        "language": payload.get("language"),
        "duration_ms": int(float(payload.get("duration") or 0.0) * 1000),
        "segments": segments,
        "raw": payload,
    }


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".m4a":
        return "audio/mp4"
    if suffix == ".flac":
        return "audio/flac"
    if suffix == ".ogg":
        return "audio/ogg"
    return "application/octet-stream"
