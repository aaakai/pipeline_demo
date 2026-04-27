"""Rule-based text-to-event enhancer."""

from __future__ import annotations

from src.enhancer.base import ScriptEnhancer
from src.sfx.taxonomy import TAXONOMY
from src.schemas import CandidateEvent, EnhancementResult


class RuleBasedEnhancer(ScriptEnhancer):
    def enhance(
        self,
        plain_text: str,
        scene: str,
        emotion: str,
        allowed_events: list[str],
    ) -> EnhancementResult:
        if not plain_text.strip():
            raise ValueError("plain_text is empty; cannot enhance script.")

        allowed = {event for event in allowed_events if event in TAXONOMY}
        events: list[CandidateEvent] = []
        notes: list[str] = []

        def add(
            event_type: str,
            anchor: str,
            position: str,
            strength: float,
            reason: str,
            duration_ms: int | None = None,
        ) -> None:
            if event_type in allowed and anchor in plain_text:
                events.append(
                    CandidateEvent(
                        event_type=event_type,
                        anchor_text=anchor,
                        position=position,  # type: ignore[arg-type]
                        strength=strength,
                        reason=reason,
                        optional_duration_ms=duration_ms,
                    )
                )

        why = "\u4e3a\u4ec0\u4e48"
        what_now = "\u600e\u4e48\u6837"
        you = "\u4f60"
        crowd = "\u4eba\u7fa4"
        murmur = "\u4f4e\u8bed"
        traffic = "\u8f66\u6d41"
        vehicle_sound = "\u8f66\u58f0"
        vehicle = "\u8f66\u8f86"
        horn = "\u55c7\u53ed"
        bus_stop = "\u516c\u4ea4\u7ad9"
        puddle = "\u6c34\u6d3c"
        approach = "\u5f80\u524d\u903c\u8fd1"
        coat = "\u5916\u5957"
        rain = "\u96e8"
        sigh_word = "\u53f9"

        if scene in {"indoor_argument", "street_argument"} or emotion in {"angry", "tense"}:
            add("cup_hit", why, "after_anchor", 0.7, "angry keyword")
            add("cloth_rustle", what_now, "before_anchor", 0.4, "tense movement")
            add("chair_move", "\u5230\u5e95", "around_anchor", 0.5, "confrontation")
            add("breath_heavy", you, "before_anchor", 0.5, "tense breathing")

        if scene in {"street_argument", "rainy_street_chat"}:
            if "street_noise" in allowed:
                events.append(
                    CandidateEvent(
                        event_type="street_noise",
                        anchor_text=plain_text[:1],
                        position="sentence_start",
                        strength=0.6,
                        reason="scene default street ambience",
                    )
                )
            if "wind_light" in allowed:
                events.append(
                    CandidateEvent(
                        event_type="wind_light",
                        anchor_text=plain_text[:1],
                        position="sentence_start",
                        strength=0.35,
                        reason="scene default light wind",
                    )
                )
            if "crowd_murmur" in allowed and (crowd in plain_text or murmur in plain_text):
                events.append(
                    CandidateEvent(
                        event_type="crowd_murmur",
                        anchor_text=crowd if crowd in plain_text else plain_text[:1],
                        position="sentence_start",
                        strength=0.45,
                        reason="crowd ambience keyword",
                    )
                )
            if "car_passby_wet" in allowed and any(
                word in plain_text for word in (traffic, vehicle_sound, vehicle)
            ):
                anchor = (
                    traffic if traffic in plain_text else vehicle_sound if vehicle_sound in plain_text else vehicle
                )
                events.append(
                    CandidateEvent(
                        event_type="car_passby_wet",
                        anchor_text=anchor,
                        position="around_anchor",
                        strength=0.65,
                        reason="wet traffic passby keyword",
                    )
                )
            add("horn_short", horn, "after_anchor", 0.75, "short horn keyword")
            add("bus_arrive", bus_stop, "around_anchor", 0.5, "bus stop ambience")
            add("puddle_step", puddle, "around_anchor", 0.6, "puddle step keyword")
            add("footsteps_fast", approach, "around_anchor", 0.6, "movement keyword")
            add("cloth_rustle", coat, "around_anchor", 0.4, "clothing keyword")

        if rain in plain_text or scene == "rainy_street_chat":
            add("rain_light", rain, "sentence_start", 0.4, "rain keyword")

        if sigh_word in plain_text or emotion in {"sad", "tired"}:
            anchor = sigh_word if sigh_word in plain_text else plain_text[:1]
            if "sigh" in allowed:
                events.append(CandidateEvent("sigh", anchor, "after_anchor", 0.5, "sigh emotion"))

        if not events:
            notes.append("rule_based enhancer found no keyword events")

        return EnhancementResult(
            plain_text=plain_text,
            scene=scene,
            emotion=emotion,
            candidate_events=events,
            notes=notes,
        )
