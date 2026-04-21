"""OpenAI Speech API TTS provider."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import requests

from src.audio.io import export_wav, load_audio
from src.schemas import OpenAITTSConfig
from src.tts.base import TTSProvider


class OpenAITTSProvider(TTSProvider):
    """Generate clean speech through OpenAI's /audio/speech endpoint.

    The provider writes the API response to a temporary file first, then uses
    pydub to normalize sample rate, channel count, and final wav format.
    """

    def __init__(
        self,
        config: OpenAITTSConfig,
        sample_rate: int,
        channels: int,
        timeout_seconds: int = 60,
    ):
        self.config = config
        self.sample_rate = sample_rate
        self.channels = channels
        self.timeout_seconds = timeout_seconds

    def synthesize(self, text: str, out_path: Path) -> Path:
        api_key = os.getenv(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"OpenAI TTS requires environment variable {self.config.api_key_env}."
            )
        if not text.strip():
            raise ValueError("Cannot synthesize empty text.")

        endpoint = self.config.base_url.rstrip("/") + "/audio/speech"
        payload: dict[str, object] = {
            "model": self.config.model,
            "voice": self.config.voice,
            "input": text,
            "response_format": self.config.response_format,
            "speed": self.config.speed,
        }
        if self.config.instructions and self.config.model not in {"tts-1", "tts-1-hd"}:
            payload["instructions"] = self.config.instructions

        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenAI TTS request failed with HTTP {response.status_code}: "
                f"{response.text[:1000]}"
            )

        suffix = "." + self.config.response_format.lstrip(".")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            tmp_file.write(response.content)
            tmp_path = Path(tmp_file.name)

        try:
            audio = load_audio(tmp_path, self.sample_rate, self.channels)
            export_wav(audio, out_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        return out_path
