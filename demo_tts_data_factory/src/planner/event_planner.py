"""Convert candidate events into a scene-template constrained event plan."""

from __future__ import annotations

from src.schemas import CandidateEvent, EnhancementResult, PlannedEvent, SceneTemplate
from src.sfx.taxonomy import TAXONOMY


class EventPlanner:
    def plan(
        self,
        enhancement: EnhancementResult,
        scene_template: SceneTemplate,
        allowed_events: list[str],
    ) -> list[PlannedEvent]:
        template_allowed = set(scene_template.allowed_foreground_events) | set(
            scene_template.allowed_background_events
        )
        global_allowed = set(allowed_events)
        candidates = [
            event
            for event in enhancement.candidate_events
            if event.event_type in TAXONOMY
            and event.event_type in template_allowed
            and event.event_type in global_allowed
        ]

        candidates.extend(
            self._default_background_candidates(
                enhancement,
                scene_template,
                global_allowed,
                existing_event_types={event.event_type for event in candidates},
            )
        )

        candidates = sorted(
            candidates,
            key=lambda item: self._priority(item, enhancement.emotion, scene_template),
            reverse=True,
        )

        planned: list[PlannedEvent] = []
        foreground_count = 0
        strong_count = 0
        for candidate in candidates:
            taxonomy = TAXONOMY[candidate.event_type]
            is_strong = candidate.strength >= 0.65 and taxonomy.foreground
            if taxonomy.foreground and foreground_count >= scene_template.max_foreground_events:
                continue
            if is_strong and strong_count >= scene_template.max_strong_events:
                continue
            if len(planned) >= scene_template.max_total_events:
                break
            if taxonomy.foreground:
                foreground_count += 1
            if is_strong:
                strong_count += 1
            planned.append(
                PlannedEvent(
                    event_id=f"evt_{len(planned) + 1:03d}",
                    event_type=candidate.event_type,
                    anchor_text=candidate.anchor_text,
                    position=candidate.position,
                    strength=candidate.strength,
                    foreground=taxonomy.foreground,
                    optional_duration_ms=candidate.optional_duration_ms,
                    source=candidate.reason or "candidate",
                )
            )
        return planned

    def _priority(
        self,
        event: CandidateEvent,
        emotion: str,
        scene_template: SceneTemplate,
    ) -> float:
        emotion_bias = scene_template.emotion_bias.get(emotion, {})
        return event.strength + float(emotion_bias.get(event.event_type, 0.0))

    def _default_background_candidates(
        self,
        enhancement: EnhancementResult,
        scene_template: SceneTemplate,
        global_allowed: set[str],
        existing_event_types: set[str],
    ) -> list[CandidateEvent]:
        candidates: list[CandidateEvent] = []
        for event_type in scene_template.default_background_events:
            if event_type in existing_event_types or event_type not in global_allowed:
                continue
            if event_type not in TAXONOMY:
                continue
            candidates.append(
                CandidateEvent(
                    event_type=event_type,
                    anchor_text=enhancement.plain_text[:1],
                    position="sentence_start",
                    strength=0.45,
                    reason="scene default background",
                    optional_duration_ms=None,
                )
            )
        return candidates
