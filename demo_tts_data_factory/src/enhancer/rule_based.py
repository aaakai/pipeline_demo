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

        if scene in {"indoor_argument", "street_argument"} or emotion in {"angry", "tense"}:
            add("cup_hit", "为什么", "after_anchor", 0.7, "angry keyword")
            add("cloth_rustle", "想怎么样", "before_anchor", 0.4, "tense movement")
            add("chair_move", "到底", "around_anchor", 0.5, "confrontation")
            add("breath_heavy", "你", "before_anchor", 0.5, "tense breathing")

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
            if "crowd_murmur" in allowed and ("人群" in plain_text or "低语" in plain_text):
                events.append(
                    CandidateEvent(
                        event_type="crowd_murmur",
                        anchor_text="人群" if "人群" in plain_text else plain_text[:1],
                        position="sentence_start",
                        strength=0.45,
                        reason="crowd ambience keyword",
                    )
                )
            if "car_passby_wet" in allowed and any(word in plain_text for word in ("车流", "车声", "车辆")):
                anchor = "车流" if "车流" in plain_text else "车声" if "车声" in plain_text else "车辆"
                events.append(
                    CandidateEvent(
                        event_type="car_passby_wet",
                        anchor_text=anchor,
                        position="around_anchor",
                        strength=0.65,
                        reason="wet traffic passby keyword",
                    )
                )
            add("horn_short", "喇叭", "after_anchor", 0.75, "short horn keyword")
            add("bus_arrive", "公交站", "around_anchor", 0.5, "bus stop ambience")
            add("puddle_step", "水洼", "around_anchor", 0.6, "puddle step keyword")
            add("footsteps_fast", "往前逼近", "around_anchor", 0.6, "movement keyword")
            add("cloth_rustle", "外套", "around_anchor", 0.4, "clothing keyword")

        if "雨" in plain_text or scene == "rainy_street":
            add("rain_light", "雨", "sentence_start", 0.4, "rain keyword")

        if "叹" in plain_text or emotion in {"sad", "tired"}:
            anchor = "叹" if "叹" in plain_text else plain_text[:1]
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
