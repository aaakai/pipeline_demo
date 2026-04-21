"""Mock TTS provider using a local clean speech wav."""

from __future__ import annotations

from pathlib import Path

from src.audio.io import export_wav, load_audio
from src.tts.base import TTSProvider


class MockTTSProvider(TTSProvider):
    def __init__(
        self,
        project_root: Path,
        clean_voice_path: str | None,
        sample_rate: int,
        channels: int,
    ):
        self.project_root = project_root
        self.clean_voice_path = clean_voice_path
        self.sample_rate = sample_rate
        self.channels = channels

    def synthesize(self, text: str, out_path: Path) -> Path:
        source = self._resolve_source()
        if not source.exists():
            raise FileNotFoundError(
                "No mock voice found. Set clean_voice_path in config or provide "
                f"{self.project_root / 'assets/mock_voice/sample_clean_voice.wav'}"
            )
        audio = load_audio(source, self.sample_rate, self.channels)
        export_wav(audio, out_path)
        return out_path

    def _resolve_source(self) -> Path:
        if self.clean_voice_path:
            path = Path(self.clean_voice_path).expanduser()
            return path if path.is_absolute() else (self.project_root / path).resolve()
        return (self.project_root / "assets/mock_voice/sample_clean_voice.wav").resolve()
