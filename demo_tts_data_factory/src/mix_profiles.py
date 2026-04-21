"""Small mix/profile presets for demo variants."""

from __future__ import annotations


VARIANT_PROFILES: dict[str, dict[str, float]] = {
    "subtle": {
        "background_density": 0.55,
        "foreground_density": 0.75,
        "background_gain_offset_db": -4.0,
        "foreground_gain_offset_db": -2.0,
        "ducking_offset_db": 1.5,
        "accent_repeat_scale": 0.6,
    },
    "balanced": {
        "background_density": 1.0,
        "foreground_density": 1.0,
        "background_gain_offset_db": 0.0,
        "foreground_gain_offset_db": 0.0,
        "ducking_offset_db": 0.0,
        "accent_repeat_scale": 1.0,
    },
    "cinematic": {
        "background_density": 1.45,
        "foreground_density": 1.2,
        "background_gain_offset_db": 2.5,
        "foreground_gain_offset_db": 1.5,
        "ducking_offset_db": -1.5,
        "accent_repeat_scale": 1.45,
    },
}


def get_variant_profile(name: str | None) -> dict[str, float]:
    if not name:
        return VARIANT_PROFILES["balanced"]
    return VARIANT_PROFILES.get(name, VARIANT_PROFILES["balanced"])
