"""Lightweight audio analysis for asset manifests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment


@dataclass(frozen=True)
class AudioAnalysis:
    duration_ms: int
    sample_rate: int
    channels: int
    rms_dbfs: float
    peak_dbfs: float
    silence_ratio: float
    estimated_intensity: float

    def as_dict(self) -> dict[str, float]:
        return {
            "rms_dbfs": round(self.rms_dbfs, 2),
            "peak_dbfs": round(self.peak_dbfs, 2),
            "silence_ratio": round(self.silence_ratio, 4),
            "estimated_intensity": round(self.estimated_intensity, 4),
        }


EVENT_TYPE_BIAS = {
    "cup_hit": 0.18,
    "door_close_hard": 0.18,
    "horn_short": 0.16,
    "puddle_step": 0.08,
    "footsteps_fast": 0.06,
    "car_passby_wet": 0.04,
    "rain_light": -0.14,
    "wind_light": -0.18,
    "crowd_murmur": -0.08,
    "street_noise": -0.06,
}


def analyze_audio(path: str | Path, event_type: str) -> AudioAnalysis:
    segment = AudioSegment.from_file(path)
    rms_dbfs = _finite_dbfs(segment.dBFS, fallback=-80.0)
    peak_dbfs = _finite_dbfs(segment.max_dBFS, fallback=-80.0)
    silence_ratio = _estimate_silence_ratio(segment)
    estimated_intensity = _estimate_intensity(rms_dbfs, peak_dbfs, silence_ratio, event_type)
    return AudioAnalysis(
        duration_ms=len(segment),
        sample_rate=segment.frame_rate,
        channels=segment.channels,
        rms_dbfs=rms_dbfs,
        peak_dbfs=peak_dbfs,
        silence_ratio=silence_ratio,
        estimated_intensity=estimated_intensity,
    )


def _finite_dbfs(value: float, fallback: float) -> float:
    if value == float("-inf"):
        return fallback
    return float(value)


def _estimate_silence_ratio(segment: AudioSegment, chunk_ms: int = 100) -> float:
    if len(segment) <= 0:
        return 1.0
    chunks = 0
    silent = 0
    threshold_dbfs = max(-55.0, _finite_dbfs(segment.dBFS, fallback=-80.0) - 18.0)
    for start_ms in range(0, len(segment), chunk_ms):
        chunk = segment[start_ms : start_ms + chunk_ms]
        if not chunk:
            continue
        chunks += 1
        if _finite_dbfs(chunk.dBFS, fallback=-80.0) <= threshold_dbfs:
            silent += 1
    return silent / chunks if chunks else 1.0


def _estimate_intensity(
    rms_dbfs: float,
    peak_dbfs: float,
    silence_ratio: float,
    event_type: str,
) -> float:
    # Map practical audio ranges into 0..1, then bias by semantic event type.
    rms_score = _clamp((rms_dbfs + 45.0) / 35.0, 0.0, 1.0)
    peak_score = _clamp((peak_dbfs + 18.0) / 18.0, 0.0, 1.0)
    silence_penalty = min(0.25, silence_ratio * 0.35)
    bias = EVENT_TYPE_BIAS.get(event_type, 0.0)
    return round(_clamp(0.68 * rms_score + 0.32 * peak_score + bias - silence_penalty, 0.05, 0.98), 4)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
