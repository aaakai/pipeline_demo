"""Timeline event merging to avoid overly dense acoustic events."""

from __future__ import annotations

from dataclasses import replace

from src.schemas import MergeConfig, TimelineEvent
from src.sfx.taxonomy import TAXONOMY


class EventMerger:
    def __init__(self, config: MergeConfig):
        self.config = config

    def merge(self, events: list[TimelineEvent]) -> list[TimelineEvent]:
        if not self.config.enabled:
            return events
        merged: list[TimelineEvent] = []
        for event in sorted(events, key=lambda item: (item.event_type, item.start_ms)):
            if not merged:
                merged.append(event)
                continue
            previous = merged[-1]
            if self._should_merge(previous, event):
                merged[-1] = self._merge_pair(previous, event)
            else:
                merged.append(event)
        return sorted(merged, key=lambda item: (item.start_ms, item.end_ms))

    def _should_merge(self, left: TimelineEvent, right: TimelineEvent) -> bool:
        if left.event_type != right.event_type:
            return False
        taxonomy = TAXONOMY[left.event_type]
        if not taxonomy.mergeable:
            return False
        gap_ms = right.start_ms - left.end_ms
        threshold = (
            self.config.cloth_rustle_merge_gap_ms
            if left.event_type == "cloth_rustle"
            else self.config.same_event_gap_ms
        )
        return gap_ms <= threshold

    def _merge_pair(self, left: TimelineEvent, right: TimelineEvent) -> TimelineEvent:
        return replace(
            left,
            event_id=f"{left.event_id}+{right.event_id}",
            anchor_text=left.anchor_text,
            start_ms=min(left.start_ms, right.start_ms),
            end_ms=max(left.end_ms, right.end_ms),
            gain_db=max(left.gain_db, right.gain_db),
            source_event_ids=left.source_event_ids + right.source_event_ids,
        )
