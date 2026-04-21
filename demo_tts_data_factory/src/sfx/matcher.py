"""SFX asset matcher."""

from __future__ import annotations

import random
from collections import deque

from src.schemas import AssetSelectionConfig, SfxAsset, TimelineEvent
from src.sfx.library import SfxLibrary
from src.sfx.taxonomy import TAXONOMY


class SfxMatcher:
    def __init__(self, library: SfxLibrary, rng: random.Random, config: AssetSelectionConfig):
        self.library = library
        self.rng = rng
        self.config = config
        self.recent_asset_ids: deque[str] = deque(maxlen=max(1, config.recent_window))

    def match(self, event: TimelineEvent, scene_tags: set[str] | None = None) -> tuple[SfxAsset, float, str] | None:
        candidates = self.library.by_event_type(event.event_type)
        self.rng.shuffle(candidates)
        if not candidates:
            return None

        target_duration = max(1, event.end_ms - event.start_ms)
        scene_tags = scene_tags or set()

        def score(asset: SfxAsset) -> float:
            # Estimate desired intensity from gain position inside taxonomy range.
            gain_low, gain_high = TAXONOMY[event.event_type].gain_db_range
            if gain_high == gain_low:
                desired_intensity = 0.5
            else:
                desired_intensity = (event.gain_db - gain_low) / (gain_high - gain_low)
            intensity_score = abs(asset.intensity - desired_intensity)
            duration_score = abs(asset.duration_ms - target_duration) / max(target_duration, 1)
            tag_bonus = len(scene_tags.intersection(set(asset.tags))) * self.config.scene_tag_weight
            recent_penalty = 0.25 if self.config.avoid_recent and asset.asset_id in self.recent_asset_ids else 0.0
            jitter = self.rng.random() * 0.06
            return intensity_score + duration_score + recent_penalty + jitter - tag_bonus

        scored = sorted((score(asset), asset) for asset in candidates)
        top_k = max(1, min(self.config.top_k, len(scored)))
        top = scored[:top_k]
        if self.config.strategy == "weighted_top_k" and len(top) > 1:
            weights = [1.0 / (item_score + 0.05) for item_score, _ in top]
            chosen_score, chosen = self.rng.choices(top, weights=weights, k=1)[0]
        else:
            chosen_score, chosen = top[0]
        self.recent_asset_ids.append(chosen.asset_id)
        reason = (
            f"event_type match; score={chosen_score:.4f}; "
            f"intensity={chosen.intensity:.2f}; duration_ms={chosen.duration_ms}; "
            f"top_k={top_k}"
        )
        return chosen, round(chosen_score, 4), reason
