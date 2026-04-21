"""OpenAI-powered script enhancer."""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from src.enhancer.base import ScriptEnhancer
from src.enhancer.rule_based import RuleBasedEnhancer
from src.schemas import EnhancedScript, LLMEnhancerConfig, ScriptEvent
from src.sfx.taxonomy import TAXONOMY

VALID_POSITIONS = {"before_anchor", "after_anchor", "around_anchor"}
MAX_ANCHOR_CHARS = 16


class OpenAILLMEnhancer(ScriptEnhancer):
    """Use an OpenAI-compatible chat endpoint to produce structured events."""

    def __init__(self, config: LLMEnhancerConfig):
        self.config = config
        self._fallback = RuleBasedEnhancer()

    def enhance(
        self,
        plain_text: str,
        scene: str,
        emotion: str,
        allowed_events: list[str],
    ) -> EnhancedScript:
        api_key = os.getenv(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"LLM enhancer requires environment variable {self.config.api_key_env}."
            )

        allowed = [event for event in allowed_events if event in TAXONOMY]
        if not allowed:
            raise ValueError("No allowed events are available for LLM enhancement.")

        payload = self._call_model(
            api_key=api_key,
            plain_text=plain_text,
            scene=scene,
            emotion=emotion,
            allowed_events=allowed,
            repair_text=None,
        )
        try:
            return self._parse_and_validate(
                payload,
                plain_text,
                scene,
                emotion,
                allowed,
                allow_fallback=False,
            )
        except Exception as first_error:
            repaired = self._call_model(
                api_key=api_key,
                plain_text=plain_text,
                scene=scene,
                emotion=emotion,
                allowed_events=allowed,
                repair_text=f"{first_error}\n\nInvalid payload:\n{payload}",
            )
            return self._parse_and_validate(
                repaired,
                plain_text,
                scene,
                emotion,
                allowed,
                allow_fallback=True,
            )

    def _call_model(
        self,
        api_key: str,
        plain_text: str,
        scene: str,
        emotion: str,
        allowed_events: list[str],
        repair_text: str | None,
    ) -> str:
        taxonomy_summary = {
            event_type: {
                "layer": item.layer,
                "category": item.category,
                "tags": item.tags,
                "can_overlap_speech": item.can_overlap_speech,
                "default_duration_ms": item.default_duration_ms,
            }
            for event_type, item in TAXONOMY.items()
            if event_type in allowed_events
        }
        system_prompt = (
            "You create audio-drama event scripts for TTS data generation. "
            "Return JSON only. Do not invent event types. Use only allowed_events. "
            "Every event anchor_text must be an exact short substring of plain_text, "
            f"preferably 2-8 characters and never longer than {MAX_ANCHOR_CHARS} characters. "
            "Create 4-8 useful events when the text supports them. "
            "Use background ambience for scene atmosphere and foreground events for actions. "
            "Keep the original plain_text unchanged."
        )
        user_payload: dict[str, Any] = {
            "plain_text": plain_text,
            "scene": scene,
            "emotion": emotion,
            "allowed_events": allowed_events,
            "event_taxonomy": taxonomy_summary,
            "positions": sorted(VALID_POSITIONS),
            "anchor_rules": [
                "anchor_text must be copied exactly from plain_text",
                f"anchor_text length must be <= {MAX_ANCHOR_CHARS}",
                "use short anchor spans such as 雨, 街口, 外套, 往前逼近, 为什么, 到底",
            ],
            "desired_output": {
                "plain_text": plain_text,
                "script_text": "Original text with full-width parenthesized event markers inserted, e.g. （street_noise）",
                "scene": scene,
                "emotion": emotion,
                "events": [
                    {
                        "type": "street_noise",
                        "anchor_text": "exact text span",
                        "position": "around_anchor",
                        "strength": 0.6,
                    }
                ],
            },
        }
        if repair_text:
            user_payload["repair_instruction"] = (
                "Repair the previous output so it validates. Return JSON only."
            )
            user_payload["validation_error"] = repair_text

        response = requests.post(
            self.config.base_url.rstrip("/") + "/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False),
                    },
                ],
                "temperature": self.config.temperature,
                "response_format": self._response_format_schema(),
            },
            timeout=self.config.timeout_seconds,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenAI LLM enhancer failed with HTTP {response.status_code}: "
                f"{response.text[:1000]}"
            )
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected OpenAI LLM response: {data}") from exc

    def _parse_and_validate(
        self,
        raw_payload: str,
        plain_text: str,
        scene: str,
        emotion: str,
        allowed_events: list[str],
        allow_fallback: bool,
    ) -> EnhancedScript:
        data = json.loads(self._extract_json(raw_payload))
        if data.get("plain_text") != plain_text:
            data["plain_text"] = plain_text
        events: list[ScriptEvent] = []
        invalid_reasons: list[str] = []
        allowed = set(allowed_events)
        for record in data.get("events", []):
            event_type = str(record.get("type", ""))
            anchor_text = str(record.get("anchor_text", ""))
            position = str(record.get("position", "around_anchor"))
            if event_type not in allowed:
                invalid_reasons.append(f"event type not allowed: {event_type}")
                continue
            if position not in VALID_POSITIONS:
                position = "around_anchor"
            if not anchor_text or anchor_text not in plain_text:
                invalid_reasons.append(f"anchor not found: {anchor_text}")
                continue
            if len(anchor_text) > MAX_ANCHOR_CHARS:
                invalid_reasons.append(f"anchor too long: {anchor_text[:32]}")
                continue
            strength = float(record.get("strength", 0.5))
            strength = min(max(strength, 0.0), 1.0)
            events.append(
                ScriptEvent(
                    type=event_type,
                    anchor_text=anchor_text,
                    position=position,  # type: ignore[arg-type]
                    strength=strength,
                )
            )
        if not events:
            if not allow_fallback:
                raise ValueError("LLM produced no valid events: " + "; ".join(invalid_reasons))
            return self._fallback.enhance(plain_text, scene, emotion, allowed_events)
        if len(events) < min(3, len(allowed_events)) and not allow_fallback:
            raise ValueError(
                "LLM produced too few valid events. "
                f"valid_count={len(events)} invalid={invalid_reasons}"
            )

        script_text = str(data.get("script_text") or plain_text)
        for event in events:
            marker = f"（{event.type}）"
            if marker not in script_text:
                script_text = self._insert_marker(script_text, event)
        return EnhancedScript(
            plain_text=plain_text,
            script_text=script_text,
            scene=str(data.get("scene") or scene),
            emotion=str(data.get("emotion") or emotion),
            events=events,
        )

    def _insert_marker(self, text: str, event: ScriptEvent) -> str:
        index = text.find(event.anchor_text)
        if index < 0:
            return text
        if event.position == "before_anchor":
            return text[:index] + f"（{event.type}）" + text[index:]
        end = index + len(event.anchor_text)
        return text[:end] + f"（{event.type}）" + text[end:]

    def _extract_json(self, text: str) -> str:
        stripped = text.strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM output did not contain a JSON object.")
        return stripped[start : end + 1]

    def _response_format_schema(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "enhanced_event_script",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["plain_text", "script_text", "scene", "emotion", "events"],
                    "properties": {
                        "plain_text": {"type": "string"},
                        "script_text": {"type": "string"},
                        "scene": {"type": "string"},
                        "emotion": {"type": "string"},
                        "events": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["type", "anchor_text", "position", "strength"],
                                "properties": {
                                    "type": {"type": "string"},
                                    "anchor_text": {"type": "string"},
                                    "position": {
                                        "type": "string",
                                        "enum": sorted(VALID_POSITIONS),
                                    },
                                    "strength": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
