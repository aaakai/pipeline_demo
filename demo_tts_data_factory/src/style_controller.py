"""Generate multiple text supervision views for each sample."""

from __future__ import annotations

from src.schemas import PlannedEvent, StyleConfig, StyleViews

EMOTION_WORDS = {
    "angry": "愤怒",
    "sad": "低落",
    "neutral": "平静",
    "tense": "紧张",
}

EVENT_WORDS = {
    "cup_hit": "杯子撞击",
    "cloth_rustle": "衣物摩擦",
    "chair_move": "椅子移动",
    "door_close_hard": "重重关门",
    "footsteps_fast": "急促脚步",
    "sigh": "叹气",
    "breath_heavy": "沉重呼吸",
    "rain_light": "小雨",
    "street_noise": "街道车流",
    "crowd_murmur": "人群低语",
    "car_passby_wet": "湿路车辆驶过",
    "horn_short": "短促喇叭",
    "bus_arrive": "公交靠站",
    "puddle_step": "踩过水洼",
    "wind_light": "轻微夜风",
}

SCENE_WORDS = {
    "indoor_argument": "室内对峙",
    "office_talk": "办公室谈话",
    "rainy_street_chat": "雨夜街头",
    "cafe_chat": "咖啡馆闲谈",
    "street_argument": "街边争吵",
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
            marker = f"（{event.event_type}）"
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
