"""Audio IO wrappers."""

from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment


def load_audio(path: str | Path, sample_rate: int, channels: int) -> AudioSegment:
    segment = AudioSegment.from_file(path)
    return segment.set_frame_rate(sample_rate).set_channels(channels)


def export_wav(segment: AudioSegment, path: str | Path) -> None:
    segment.export(path, format="wav")
