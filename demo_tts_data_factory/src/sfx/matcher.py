"""SFX asset matcher."""

from __future__ import annotations

import random

from src.schemas import SfxAsset, TimelineEvent
from src.sfx.library import SfxLibrary
from src.sfx.taxonomy import TAXONOMY


class SfxMatcher:
    def __init__(self, library: SfxLibrary, rng: random.Random):
        self.library = library
        self.rng = rng

    def match(self, event: TimelineEvent) -> SfxAsset | None:
        candidates = self.library.by_event_type(event.event_type)
        self.rng.shuffle(candidates)
        if not candidates:
            return None

        target_duration = max(1, event.end_ms - event.start_ms)

        def score(asset: SfxAsset) -> float:
            # Estimate desired intensity from gain position inside taxonomy range.
            gain_low, gain_high = TAXONOMY[event.event_type].gain_db_range
            if gain_high == gain_low:
                desired_intensity = 0.5
            else:
                desired_intensity = (event.gain_db - gain_low) / (gain_high - gain_low)
            intensity_score = abs(asset.intensity - desired_intensity)
            duration_score = abs(asset.duration_ms - target_duration) / max(target_duration, 1)
            jitter = self.rng.random() * 0.05
            return intensity_score + duration_score + jitter

        return min(candidates, key=score)
