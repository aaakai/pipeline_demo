"""Generate multiple text supervision views for each sample."""

from __future__ import annotations

from src.schemas import PlannedEvent, StyleConfig, StyleViews

EMOTION_WORDS = {
    "angry": "\u6124\u6012",
    "sad": "\u4f4e\u843d",
    "neutral": "\u5e73\u9759",
    "tense": "\u7d27\u5f20",
    "tired": "\u75b2\u60eb",
}

EVENT_WORDS = {
    "cup_hit": "\u676f\u5b50\u649e\u51fb",
    "cloth_rustle": "\u8863\u7269\u6469\u64e6",
    "chair_move": "\u6905\u5b50\u79fb\u52a8",
    "door_close_hard": "\u91cd\u91cd\u5173\u95e8",
    "door_knock": "\u6572\u95e8",
    "footsteps_fast": "\u6025\u4fc3\u811a\u6b65",
    "footsteps_indoor": "\u5ba4\u5185\u811a\u6b65",
    "sigh": "\u53f9\u6c14",
    "breath_heavy": "\u6c89\u91cd\u547c\u5438",
    "room_tone": "\u623f\u95f4\u5e95\u566a",
    "air_conditioner_hum": "\u7a7a\u8c03\u55e1\u9e23",
    "fluorescent_light_hum": "\u65e5\u5149\u706f\u55e1\u9e23",
    "paper_rustle": "\u7eb8\u5f20\u7ffb\u52a8",
    "menu_page_turn": "\u7ffb\u83dc\u5355",
    "keyboard_typing": "\u952e\u76d8\u6572\u51fb",
    "phone_vibrate": "\u624b\u673a\u9707\u52a8",
    "light_switch_click": "\u5f00\u5173\u54d2\u55d2",
    "restaurant_murmur": "\u9910\u5385\u4eba\u58f0",
    "cutlery_clink": "\u9910\u5177\u78b0\u649e",
    "plate_set_down": "\u76d8\u5b50\u843d\u684c",
    "glass_clink": "\u73bb\u7483\u676f\u78b0\u676f",
    "pour_water": "\u5012\u6c34",
    "kitchen_clatter": "\u540e\u53a8\u6742\u54cd",
    "service_bell": "\u670d\u52a1\u94c3",
    "rain_light": "\u5c0f\u96e8",
    "street_noise": "\u8857\u9053\u8f66\u6d41",
    "crowd_murmur": "\u4eba\u7fa4\u4f4e\u8bed",
    "station_crowd": "\u7ad9\u53f0\u4eba\u6f6e",
    "car_passby_wet": "\u6e7f\u8def\u8f66\u8f86\u9a76\u8fc7",
    "car_passby_dry": "\u5e72\u8def\u8f66\u8f86\u9a76\u8fc7",
    "horn_short": "\u77ed\u4fc3\u5587\u53ed",
    "bus_arrive": "\u516c\u4ea4\u9760\u7ad9",
    "train_arrive": "\u5217\u8f66\u8fdb\u7ad9",
    "metro_announcement": "\u5730\u94c1\u64ad\u62a5",
    "ticket_gate_beep": "\u95f8\u673a\u63d0\u793a\u97f3",
    "puddle_step": "\u8e29\u8fc7\u6c34\u6d3c",
    "bicycle_bell": "\u81ea\u884c\u8f66\u94c3",
    "bird_chirp": "\u9e1f\u9e23",
    "crosswalk_beep": "\u8fc7\u8857\u63d0\u793a\u97f3",
    "shop_door_chime": "\u5e97\u95e8\u98ce\u94c3",
    "distant_construction": "\u8fdc\u5904\u65bd\u5de5",
    "wind_light": "\u8f7b\u5fae\u98ce\u58f0",
    "library_room_tone": "\u56fe\u4e66\u9986\u5e95\u566a",
    "book_page_turn": "\u7ffb\u4e66\u9875",
    "pen_write": "\u4e66\u5199\u7b14\u58f0",
    "hospital_ambience": "\u533b\u9662\u8d70\u5eca\u5e95\u566a",
    "medical_monitor_beep": "\u76d1\u62a4\u4eea\u63d0\u793a\u97f3",
    "trolley_roll": "\u63a8\u8f66\u6eda\u8f6e",
    "espresso_machine": "\u5496\u5561\u673a\u8403\u53d6",
    "coffee_grinder": "\u78e8\u8c46\u673a",
    "milk_steam": "\u6253\u5976\u84b8\u6c7d",
    "machine_hum": "\u673a\u68b0\u55e1\u9e23",
    "metal_clank": "\u91d1\u5c5e\u78b0\u54cd",
    "hydraulic_hiss": "\u6db2\u538b\u5616\u5636",
}

SCENE_WORDS = {
    "indoor_argument": "\u5ba4\u5185\u5bf9\u5cd9",
    "office_talk": "\u529e\u516c\u5ba4\u8c08\u8bdd",
    "indoor_room_chat": "\u5ba4\u5185\u804a\u5929",
    "restaurant_chat": "\u9910\u5385\u5bf9\u8bdd",
    "rainy_street_chat": "\u96e8\u591c\u8857\u5934",
    "sunny_street_chat": "\u6674\u5929\u8857\u5934",
    "cafe_chat": "\u5496\u5561\u9986\u95f2\u804a",
    "library_study_chat": "\u56fe\u4e66\u9986\u4f4e\u58f0\u4ea4\u8c08",
    "factory_workshop_chat": "\u5de5\u4e1a\u8f66\u95f4\u5bf9\u8bdd",
    "after_exercise_chat": "\u8fd0\u52a8\u540e\u4f11\u606f\u5bf9\u8bdd",
    "street_argument": "\u8857\u8fb9\u4e89\u5435",
}


class StyleController:
    def build(
        self,
        plain_text: str,
        scene: str,
        emotion: str,
        events: list[PlannedEvent],
        config: StyleConfig,
    ) -> StyleViews:
        keyword_style = self._keyword_style(scene, emotion, events) if config.enable_keyword_style else ""
        brief_style = self._brief_style(plain_text, events) if config.enable_brief_style else plain_text
        script_text = self._script_text(scene, emotion, plain_text, keyword_style, brief_style, events)
        return StyleViews(
            keyword_style=keyword_style,
            brief_style=brief_style,
            script_text=script_text,
        )

    def _keyword_style(self, scene: str, emotion: str, events: list[PlannedEvent]) -> str:
        words = [EMOTION_WORDS.get(emotion, emotion), SCENE_WORDS.get(scene, scene)]
        for event in events:
            word = EVENT_WORDS.get(event.event_type, event.event_type)
            if word not in words:
                words.append(word)
        return " ".join(words)

    def _brief_style(self, plain_text: str, events: list[PlannedEvent]) -> str:
        text = plain_text
        for event in sorted(events, key=lambda item: plain_text.find(item.anchor_text), reverse=True):
            marker = f"({event.event_type})"
            if marker in text:
                continue
            index = text.find(event.anchor_text)
            if index < 0:
                continue
            if event.position in {"before_anchor", "sentence_start"}:
                text = text[:index] + marker + text[index:]
            else:
                end = index + len(event.anchor_text)
                text = text[:end] + marker + text[end:]
        return text

    def _script_text(
        self,
        scene: str,
        emotion: str,
        plain_text: str,
        keyword_style: str,
        brief_style: str,
        events: list[PlannedEvent],
    ) -> str:
        event_lines = [
            f"- {event.event_id}: {event.event_type} @ {event.anchor_text} "
            f"({event.position}, strength={event.strength:.2f})"
            for event in events
        ]
        return "\n".join(
            [
                f"Scene: {scene}",
                f"Emotion: {emotion}",
                f"Text: {plain_text}",
                f"Brief: {brief_style}",
                f"Keywords: {keyword_style}",
                "Events:",
                *event_lines,
            ]
        )
