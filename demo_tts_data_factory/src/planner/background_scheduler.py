"""Dynamic background and ambience event scheduling."""

from __future__ import annotations

import random

from src.mix_profiles import get_variant_profile
from src.schemas import BackgroundSchedulerConfig, SceneTemplate, TimelineEvent
from src.sfx.taxonomy import TAXONOMY


class BackgroundScheduler:
    def __init__(self, config: BackgroundSchedulerConfig, rng: random.Random):
        self.config = config
        self.rng = rng

    def schedule(
        self,
        timeline: list[TimelineEvent],
        scene_template: SceneTemplate,
        speech_duration_ms: int,
        background_gain_db: float,
        default_ducking_db: float,
        variant: str | None,
    ) -> list[TimelineEvent]:
        if not self.config.enabled or speech_duration_ms <= 0:
            return timeline

        profile = get_variant_profile(variant)
        scheduled = list(timeline)
        scheduled.extend(
            self._background_beds(
                timeline=scheduled,
                scene_template=scene_template,
                speech_duration_ms=speech_duration_ms,
                background_gain_db=background_gain_db,
                profile=profile,
            )
        )
        existing_types = {event.event_type for event in scheduled}
        accent_budget = int(self.config.max_accent_events * profile["accent_repeat_scale"])
        accent_budget = max(0, accent_budget)

        for event_type in self._accent_event_types(scene_template, existing_types):
            if accent_budget <= 0:
                break
            repeats = min(accent_budget, self._repeat_count(event_type, profile))
            for _ in range(repeats):
                if accent_budget <= 0:
                    break
                event = self._make_event(
                    event_type=event_type,
                    timeline=scheduled,
                    speech_duration_ms=speech_duration_ms,
                    background_gain_db=background_gain_db,
                    default_ducking_db=default_ducking_db,
                    profile=profile,
                )
                if event is None:
                    continue
                scheduled.append(event)
                accent_budget -= 1
        return sorted(scheduled, key=lambda item: (item.start_ms, item.end_ms))

    def _background_beds(
        self,
        timeline: list[TimelineEvent],
        scene_template: SceneTemplate,
        speech_duration_ms: int,
        background_gain_db: float,
        profile: dict[str, float],
    ) -> list[TimelineEvent]:
        """Add long ambience layers so the scene has a continuous acoustic floor."""
        existing_background = {
            event.event_type
            for event in timeline
            if not event.foreground and event.end_ms - event.start_ms >= speech_duration_ms * 0.6
        }
        current_layers = len(existing_background)
        beds: list[TimelineEvent] = []
        for event_type in scene_template.default_background_events:
            if current_layers >= self.config.max_background_layers:
                break
            if event_type in existing_background or event_type not in TAXONOMY:
                continue
            taxonomy = TAXONOMY[event_type]
            if taxonomy.foreground:
                continue
            strength = self._background_bed_strength(event_type, profile)
            gain_low, gain_high = taxonomy.gain_db_range
            gain_db = gain_low + (gain_high - gain_low) * strength
            gain_db = min(gain_db + profile["background_gain_offset_db"], background_gain_db + 6.0)
            beds.append(
                TimelineEvent(
                    event_id=f"bed_{event_type}",
                    event_type=event_type,
                    anchor_text=event_type,
                    position="around_anchor",
                    foreground=False,
                    start_ms=0,
                    end_ms=speech_duration_ms,
                    gain_db=round(gain_db, 2),
                    ducking_db=0.0,
                    asset_id=None,
                    asset_path=None,
                    source_event_ids=["background_bed"],
                    gain_trace={"background_bed_strength": round(strength, 3)},
                )
            )
            existing_background.add(event_type)
            current_layers += 1
        return beds

    def _accent_event_types(
        self,
        scene_template: SceneTemplate,
        existing_types: set[str],
    ) -> list[str]:
        preferred = [
            "car_passby_wet",
            "car_passby_dry",
            "bus_arrive",
            "horn_short",
            "puddle_step",
            "bicycle_bell",
            "crosswalk_beep",
            "shop_door_chime",
            "distant_construction",
            "bird_chirp",
            "phone_vibrate",
            "door_knock",
            "paper_rustle",
            "menu_page_turn",
            "cutlery_clink",
            "plate_set_down",
            "glass_clink",
            "pour_water",
            "service_bell",
            "keyboard_typing",
            "chair_move",
            "footsteps_indoor",
            "light_switch_click",
            "wind_light",
            "street_noise",
        ]
        allowed = set(scene_template.allowed_background_events) | set(scene_template.allowed_foreground_events)
        return [event_type for event_type in preferred if event_type in allowed and event_type in TAXONOMY]

    def _repeat_count(self, event_type: str, profile: dict[str, float]) -> int:
        base = {
            "car_passby_wet": 3,
            "car_passby_dry": 3,
            "bus_arrive": 2,
            "horn_short": 2,
            "puddle_step": 3,
            "bicycle_bell": 2,
            "crosswalk_beep": 2,
            "shop_door_chime": 1,
            "distant_construction": 1,
            "bird_chirp": 2,
            "phone_vibrate": 1,
            "door_knock": 1,
            "paper_rustle": 2,
            "menu_page_turn": 1,
            "cutlery_clink": 3,
            "plate_set_down": 1,
            "glass_clink": 2,
            "pour_water": 1,
            "service_bell": 1,
            "keyboard_typing": 1,
            "chair_move": 1,
            "footsteps_indoor": 2,
            "light_switch_click": 1,
            "wind_light": 1,
            "street_noise": 1,
        }.get(event_type, 1)
        scaled = base * profile["accent_repeat_scale"]
        return max(0, int(round(scaled)))

    def _make_event(
        self,
        event_type: str,
        timeline: list[TimelineEvent],
        speech_duration_ms: int,
        background_gain_db: float,
        default_ducking_db: float,
        profile: dict[str, float],
    ) -> TimelineEvent | None:
        taxonomy = TAXONOMY[event_type]
        duration_ms = min(taxonomy.default_duration_ms, max(500, speech_duration_ms // 3))
        latest_start = max(0, speech_duration_ms - duration_ms)
        for _ in range(10):
            start_ms = self.rng.randint(0, latest_start) if latest_start else 0
            start_ms += self.rng.randint(-self.config.random_offset_ms, self.config.random_offset_ms)
            start_ms = max(0, min(start_ms, latest_start))
            end_ms = min(speech_duration_ms, start_ms + duration_ms)
            if self._too_close(event_type, start_ms, timeline):
                continue
            strength = self._strength_for(event_type, profile)
            gain_low, gain_high = taxonomy.gain_db_range
            gain_db = gain_low + (gain_high - gain_low) * strength
            if taxonomy.foreground:
                gain_db += profile["foreground_gain_offset_db"]
            else:
                gain_db = min(gain_db + profile["background_gain_offset_db"], background_gain_db + 4.0)
            ducking_db = default_ducking_db + profile["ducking_offset_db"] if taxonomy.foreground else 0.0
            return TimelineEvent(
                event_id=f"sched_{event_type}_{start_ms}",
                event_type=event_type,
                anchor_text=event_type,
                position="around_anchor",
                foreground=taxonomy.foreground,
                start_ms=start_ms,
                end_ms=end_ms,
                gain_db=round(gain_db, 2),
                ducking_db=round(ducking_db, 2),
                asset_id=None,
                asset_path=None,
                source_event_ids=["background_scheduler"],
            )
        return None

    def _too_close(self, event_type: str, start_ms: int, timeline: list[TimelineEvent]) -> bool:
        for event in timeline:
            if event.event_type != event_type:
                continue
            if abs(event.start_ms - start_ms) < self.config.min_gap_ms:
                return True
        return False

    def _strength_for(self, event_type: str, profile: dict[str, float]) -> float:
        base = {
            "car_passby_wet": 0.58,
            "car_passby_dry": 0.5,
            "horn_short": 0.48,
            "puddle_step": 0.42,
            "bicycle_bell": 0.34,
            "crosswalk_beep": 0.32,
            "shop_door_chime": 0.32,
            "bus_arrive": 0.5,
            "distant_construction": 0.3,
            "bird_chirp": 0.26,
            "phone_vibrate": 0.36,
            "door_knock": 0.42,
            "paper_rustle": 0.32,
            "menu_page_turn": 0.3,
            "cutlery_clink": 0.36,
            "plate_set_down": 0.42,
            "glass_clink": 0.34,
            "pour_water": 0.3,
            "service_bell": 0.32,
            "keyboard_typing": 0.28,
            "chair_move": 0.34,
            "footsteps_indoor": 0.32,
            "light_switch_click": 0.28,
            "wind_light": 0.32,
            "street_noise": 0.38,
        }.get(event_type, 0.45)
        if TAXONOMY[event_type].foreground:
            return max(0.1, min(0.9, base * profile["foreground_density"]))
        return max(0.1, min(0.9, base * profile["background_density"]))

    def _background_bed_strength(self, event_type: str, profile: dict[str, float]) -> float:
        base = {
            "rain_light": 0.5,
            "street_noise": 0.46,
            "wind_light": 0.34,
            "crowd_murmur": 0.28,
            "bird_chirp": 0.24,
            "distant_construction": 0.22,
            "room_tone": 0.42,
            "air_conditioner_hum": 0.34,
            "fluorescent_light_hum": 0.24,
            "restaurant_murmur": 0.42,
            "kitchen_clatter": 0.3,
        }.get(event_type, 0.36)
        return max(0.12, min(0.85, base * profile["background_density"]))
