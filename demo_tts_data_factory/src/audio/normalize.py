"""Small normalization helpers."""

from __future__ import annotations

from pydub import AudioSegment


def safe_gain(segment: AudioSegment, gain_db: float) -> AudioSegment:
    return segment.apply_gain(gain_db)


def normalize_peak(segment: AudioSegment, target_peak_dbfs: float = -1.0) -> AudioSegment:
    if segment.max_dBFS == float("-inf"):
        return segment
    gain = target_peak_dbfs - segment.max_dBFS
    return segment.apply_gain(gain)
