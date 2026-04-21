"""Small built-in sound event taxonomy."""

from __future__ import annotations

from src.schemas import EventTaxonomyItem

TAXONOMY: dict[str, EventTaxonomyItem] = {
    "cup_hit": EventTaxonomyItem("cup_hit", "object", True, True, 350, (-4, 2), False, ["impact", "indoor"]),
    "cloth_rustle": EventTaxonomyItem("cloth_rustle", "movement", True, True, 500, (-10, -2), True, ["cloth", "indoor"]),
    "chair_move": EventTaxonomyItem("chair_move", "movement", True, True, 700, (-8, 0), False, ["chair", "indoor"]),
    "door_close_hard": EventTaxonomyItem("door_close_hard", "door", True, False, 700, (-4, 3), False, ["impact", "indoor"]),
    "footsteps_fast": EventTaxonomyItem("footsteps_fast", "footsteps", True, True, 1200, (-9, -1), True, ["movement"]),
    "sigh": EventTaxonomyItem("sigh", "vocal_reaction", True, True, 800, (-12, -4), True, ["breath"]),
    "breath_heavy": EventTaxonomyItem("breath_heavy", "vocal_reaction", True, True, 900, (-14, -5), True, ["breath"]),
    "rain_light": EventTaxonomyItem("rain_light", "ambience", False, True, 3000, (-24, -12), True, ["rain", "outdoor"]),
    "street_noise": EventTaxonomyItem("street_noise", "ambience", False, True, 12000, (-24, -10), True, ["street", "outdoor", "traffic"]),
    "crowd_murmur": EventTaxonomyItem("crowd_murmur", "ambience", False, True, 3000, (-22, -10), True, ["crowd"]),
    "car_passby_wet": EventTaxonomyItem("car_passby_wet", "vehicle", False, True, 4500, (-20, -8), True, ["street", "traffic", "wet"]),
    "horn_short": EventTaxonomyItem("horn_short", "vehicle", True, True, 1200, (-14, -4), False, ["street", "traffic", "horn"]),
    "bus_arrive": EventTaxonomyItem("bus_arrive", "vehicle", False, True, 5000, (-21, -9), True, ["street", "bus", "brake"]),
    "puddle_step": EventTaxonomyItem("puddle_step", "footsteps", True, True, 1300, (-10, -2), True, ["street", "water", "footsteps"]),
    "wind_light": EventTaxonomyItem("wind_light", "ambience", False, True, 8000, (-28, -16), True, ["outdoor", "wind"]),
}
