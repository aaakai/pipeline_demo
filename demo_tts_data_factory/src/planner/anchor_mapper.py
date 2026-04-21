"""Approximate text anchor to audio timeline mapping."""

from __future__ import annotations

from src.schemas import PlannedEvent, TimelineEvent
from src.sfx.taxonomy import TAXONOMY
from src.utils.time import anchor_to_ms


class AnchorMapper:
    def map_events(
        self,
        plain_text: str,
        planned_events: list[PlannedEvent],
        speech_duration_ms: int,
        default_ducking_db: float,
        background_gain_db: float,
    ) -> list[TimelineEvent]:
        timeline: list[TimelineEvent] = []
        for event in planned_events:
            taxonomy = TAXONOMY[event.event_type]
            duration_ms = event.optional_duration_ms or taxonomy.default_duration_ms
            if not event.foreground and event.position == "sentence_start":
                duration_ms = speech_duration_ms
            anchor_ms = anchor_to_ms(plain_text, event.anchor_text, speech_duration_ms)
            start_ms = self._start_for_position(event, anchor_ms, duration_ms, speech_duration_ms)
            end_ms = min(speech_duration_ms, start_ms + duration_ms)
            gain_low, gain_high = taxonomy.gain_db_range
            gain_db = gain_low + (gain_high - gain_low) * max(0.0, min(event.strength, 1.0))
            if not event.foreground:
                gain_db = min(gain_db, background_gain_db)
            timeline.append(
                TimelineEvent(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    anchor_text=event.anchor_text,
                    position=event.position,
                    foreground=event.foreground,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    gain_db=round(gain_db, 2),
                    ducking_db=default_ducking_db if event.foreground else 0.0,
                    asset_id=None,
                    asset_path=None,
                    source_event_ids=[event.event_id],
                )
            )
        return sorted(timeline, key=lambda item: (item.start_ms, item.end_ms))

    def _start_for_position(
        self,
        event: PlannedEvent,
        anchor_ms: int,
        duration_ms: int,
        speech_duration_ms: int,
    ) -> int:
        if event.position == "before_anchor":
            start_ms = anchor_ms - duration_ms
        elif event.position == "after_anchor":
            start_ms = anchor_ms
        elif event.position == "sentence_start":
            start_ms = 0
        elif event.position == "sentence_end":
            start_ms = speech_duration_ms - duration_ms
        else:
            start_ms = anchor_ms - duration_ms // 2
        return max(0, min(start_ms, max(0, speech_duration_ms - 1)))
