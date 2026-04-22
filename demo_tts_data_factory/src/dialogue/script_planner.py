"""LLM-backed scene and event planner for dialogue audio."""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from src.schemas import DialoguePlannerConfig
from src.sfx.taxonomy import TAXONOMY


SCENE_CHOICES = ["rainy_street_chat", "indoor_argument", "office_talk", "cafe_chat"]
EMOTION_CHOICES = ["angry", "tense", "sad", "neutral", "tired"]


def plan_dialogue_script(
    transcript: dict[str, Any],
    pauses: list[dict],
    energy_peaks: list[dict],
    audio_duration_ms: int,
    config: DialoguePlannerConfig,
) -> dict[str, Any]:
    api_key = os.getenv(config.api_key_env)
    if not api_key:
        raise RuntimeError(f"Dialogue planner requires environment variable {config.api_key_env}.")

    endpoint = config.base_url.rstrip("/") + "/chat/completions"
    prompt = _build_prompt(transcript, pauses, energy_peaks, audio_duration_ms)
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.model,
            "temperature": config.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an audio-drama sound designer. Return only valid JSON. "
                        "Use only allowed event types and avoid sound effects that would cover dialogue."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        },
        timeout=config.timeout_seconds,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Dialogue planner failed with HTTP {response.status_code}: {response.text[:1000]}"
        )
    content = response.json()["choices"][0]["message"]["content"]
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Dialogue planner returned invalid JSON: {content[:1000]}") from exc
    return _sanitize_plan(payload, audio_duration_ms)


def _build_prompt(
    transcript: dict[str, Any],
    pauses: list[dict],
    energy_peaks: list[dict],
    audio_duration_ms: int,
) -> str:
    compact_segments = transcript.get("segments", [])[:40]
    allowed_events = sorted(TAXONOMY.keys())
    return json.dumps(
        {
            "task": "Infer scene, emotion, speaker roles, and a cinematic-but-dialogue-safe acoustic event plan for a real dialogue audio clip.",
            "constraints": [
                "Choose scene from scene_choices.",
                "Choose primary emotion from emotion_choices.",
                "Event event_type must be one of allowed_events.",
                "For rainy_street_chat, prefer a layered ambience bed: rain_light plus street_noise and wind_light when appropriate.",
                "For long clips, plan enough sparse accents to keep the world alive: roughly 1 event every 12-20 seconds.",
                "Place strong foreground events in detected pauses or low-energy regions whenever possible.",
                "Use vehicle and street accents such as car_passby_wet, bus_arrive, horn_short, and puddle_step for outdoor street scenes.",
                "Dialogue clarity is still important: avoid placing loud foreground effects over dense speech.",
                "Return JSON with keys: scene, emotion, summary, speakers, script_notes, events.",
            ],
            "scene_choices": SCENE_CHOICES,
            "emotion_choices": EMOTION_CHOICES,
            "allowed_events": allowed_events,
            "audio_duration_ms": audio_duration_ms,
            "target_event_count": {
                "minimum": max(8, min(18, audio_duration_ms // 18000)),
                "maximum": max(12, min(28, audio_duration_ms // 10000)),
                "include_background_beds": True,
            },
            "transcript_text": transcript.get("text", ""),
            "segments": compact_segments,
            "detected_pauses": pauses[:18],
            "energy_peaks": energy_peaks[:10],
            "event_schema": {
                "event_type": "rain_light",
                "layer": "background|foreground|background_accent",
                "start_ms": 0,
                "end_ms": audio_duration_ms,
                "strength": 0.4,
                "reason": "why this event fits",
            },
        },
        ensure_ascii=False,
    )


def _sanitize_plan(payload: dict[str, Any], audio_duration_ms: int) -> dict[str, Any]:
    scene = payload.get("scene") if payload.get("scene") in SCENE_CHOICES else "rainy_street_chat"
    emotion = payload.get("emotion") if payload.get("emotion") in EMOTION_CHOICES else "tense"
    events: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("events") or [], start=1):
        event_type = item.get("event_type")
        if event_type not in TAXONOMY:
            continue
        taxonomy = TAXONOMY[event_type]
        start_ms = int(max(0, min(audio_duration_ms, int(item.get("start_ms", 0) or 0))))
        default_end = start_ms + taxonomy.default_duration_ms
        end_ms = int(item.get("end_ms", default_end) or default_end)
        end_ms = max(start_ms + 200, min(audio_duration_ms, end_ms))
        strength = float(item.get("strength", 0.45) or 0.45)
        events.append(
            {
                "event_id": f"llm_evt_{index:03d}",
                "event_type": event_type,
                "layer": item.get("layer") or ("foreground" if taxonomy.foreground else "background"),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "strength": max(0.05, min(0.95, strength)),
                "reason": str(item.get("reason") or "llm event"),
            }
        )
    if not events:
        events = _fallback_events(audio_duration_ms)
    return {
        "scene": scene,
        "emotion": emotion,
        "summary": str(payload.get("summary") or ""),
        "speakers": payload.get("speakers") or [],
        "script_notes": str(payload.get("script_notes") or ""),
        "events": events,
    }


def _fallback_events(audio_duration_ms: int) -> list[dict[str, Any]]:
    return [
        {
            "event_id": "fallback_evt_001",
            "event_type": "crowd_murmur",
            "layer": "background",
            "start_ms": 0,
            "end_ms": audio_duration_ms,
            "strength": 0.25,
            "reason": "fallback ambience",
        }
    ]
