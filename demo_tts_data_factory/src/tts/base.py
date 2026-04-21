"""TTS provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, out_path: Path) -> Path:
        """Generate or provide clean speech audio."""
