"""Audio-derived hints for dialogue-driven SFX placement."""

from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment
from pydub.silence import detect_silence


def detect_pauses(
    audio_path: str | Path,
    min_silence_len_ms: int = 320,
    silence_margin_db: float = 16.0,
) -> list[dict[str, int | float]]:
    audio = AudioSegment.from_file(audio_path)
    silence_thresh = max(-55.0, audio.dBFS - silence_margin_db)
    ranges = detect_silence(
        audio,
        min_silence_len=min_silence_len_ms,
        silence_thresh=silence_thresh,
        seek_step=20,
    )
    return [
        {
            "start_ms": int(start),
            "end_ms": int(end),
            "duration_ms": int(end - start),
            "silence_thresh_dbfs": round(silence_thresh, 2),
        }
        for start, end in ranges
        if end > start
    ]


def detect_energy_peaks(
    audio_path: str | Path,
    window_ms: int = 800,
    max_peaks: int = 8,
) -> list[dict[str, int | float]]:
    audio = AudioSegment.from_file(audio_path)
    if len(audio) <= 0:
        return []
    windows: list[tuple[float, int, int]] = []
    for start_ms in range(0, len(audio), window_ms):
        end_ms = min(len(audio), start_ms + window_ms)
        chunk = audio[start_ms:end_ms]
        if not chunk:
            continue
        dbfs = -80.0 if chunk.dBFS == float("-inf") else float(chunk.dBFS)
        windows.append((dbfs, start_ms, end_ms))
    windows.sort(reverse=True, key=lambda item: item[0])
    peaks: list[dict[str, int | float]] = []
    for dbfs, start_ms, end_ms in windows:
        if any(abs(start_ms - int(existing["start_ms"])) < window_ms for existing in peaks):
            continue
        peaks.append({"start_ms": start_ms, "end_ms": end_ms, "rms_dbfs": round(dbfs, 2)})
        if len(peaks) >= max_peaks:
            break
    return sorted(peaks, key=lambda item: int(item["start_ms"]))


def compact_ranges(ranges: list[dict], limit: int = 12) -> list[dict]:
    if len(ranges) <= limit:
        return ranges
    head = ranges[: limit // 2]
    tail = ranges[-(limit - len(head)) :]
    return head + tail
