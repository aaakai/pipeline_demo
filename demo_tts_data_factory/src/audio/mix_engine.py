"""Pydub-based timeline mixer."""

from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment

from src.audio.io import export_wav, load_audio
from src.audio.normalize import normalize_peak
from src.schemas import TimelineEvent


class MixEngine:
    def __init__(self, sample_rate: int, channels: int, fade_ms: int, max_peak_dbfs: float = -1.0):
        self.sample_rate = sample_rate
        self.channels = channels
        self.fade_ms = fade_ms
        self.max_peak_dbfs = max_peak_dbfs

    def mix(
        self,
        clean_speech_path: Path,
        timeline: list[TimelineEvent],
        output_path: Path,
        speech_gain_db: float,
    ) -> None:
        speech = load_audio(clean_speech_path, self.sample_rate, self.channels)
        base = speech.apply_gain(speech_gain_db)

        ducked = base
        for item in timeline:
            if item.asset_path and item.ducking_db < 0:
                ducked = self._apply_ducking(ducked, item.start_ms, item.end_ms, item.ducking_db)

        mixed = ducked
        for item in timeline:
            if not item.asset_path:
                continue
            sfx = load_audio(item.asset_path, self.sample_rate, self.channels)
            max_len = max(1, item.end_ms - item.start_ms)
            if not item.foreground and len(sfx) < max_len:
                repeat_count = max_len // max(len(sfx), 1) + 1
                sfx = sfx * repeat_count
            sfx = sfx[:max_len].apply_gain(item.gain_db)
            fade = min(self.fade_ms, max(1, len(sfx) // 3))
            sfx = sfx.fade_in(fade).fade_out(fade)
            mixed = mixed.overlay(sfx, position=max(0, item.start_ms))

        export_wav(normalize_peak(mixed, self.max_peak_dbfs), output_path)

    def _apply_ducking(
        self,
        speech: AudioSegment,
        start_ms: int,
        end_ms: int,
        ducking_db: float,
    ) -> AudioSegment:
        start = max(0, min(start_ms, len(speech)))
        end = max(start, min(end_ms, len(speech)))
        if end <= start:
            return speech
        return speech[:start] + speech[start:end].apply_gain(ducking_db) + speech[end:]
