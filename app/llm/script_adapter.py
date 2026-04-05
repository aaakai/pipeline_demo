"""Adapt cleaned text into a structured radio-drama style script."""

from __future__ import annotations

import json
import logging
import re

import requests
from pydantic import ValidationError

from app.exceptions import LLMError
from app.schemas import Character, ScriptManifest, ScriptSegment
from app.utils import detect_language

LOGGER = logging.getLogger("pipeline_demo")

SYSTEM_PROMPT = """You convert cleaned prose into a strict JSON script manifest for voice acting.
Return only JSON. Do not use markdown. Preserve meaning. Narration must use NARRATOR.
Dialogue should become character lines. If speaker names are unclear, use CHARACTER_A, CHARACTER_B, and so on.
Output schema:
{
  "title": "string",
  "source_url": "string",
  "language": "en|zh|mixed",
  "characters": [{"name": "string", "voice_hint": "string"}],
  "segments": [{"id": 1, "speaker": "string", "text": "string", "emotion": "neutral", "pause_ms": 300}]
}"""


def _guess_voice(name: str) -> str:
    if name == "NARRATOR":
        return "neutral"
    if name.endswith("A"):
        return "female_young"
    if name.endswith("B"):
        return "male_calm"
    return "neutral"


def _build_script_text(manifest: ScriptManifest) -> str:
    return "\n".join(f"{segment.speaker}: {segment.text}" for segment in manifest.segments)


def _split_dialogue(paragraph: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    pattern = r'"([^"]+)"'
    matches = list(re.finditer(pattern, paragraph))
    if not matches:
        return [("NARRATOR", paragraph)]

    cursor = 0
    speaker_index = 0
    for match in matches:
        before = paragraph[cursor:match.start()].strip(" ,")
        if before:
            parts.append(("NARRATOR", before))
        speaker = f"CHARACTER_{chr(ord('A') + min(speaker_index, 25))}"
        parts.append((speaker, match.group(1).strip()))
        cursor = match.end()
        speaker_index += 1
    after = paragraph[cursor:].strip(" ,")
    if after:
        parts.append(("NARRATOR", after))
    return parts


def build_manifest_heuristic(
    title: str,
    source_url: str,
    cleaned_text: str,
) -> ScriptManifest:
    paragraphs = [p.strip() for p in cleaned_text.split("\n\n") if p.strip()]
    segments: list[ScriptSegment] = []
    character_names: list[str] = ["NARRATOR"]

    for paragraph in paragraphs:
        for speaker, text in _split_dialogue(paragraph):
            if speaker not in character_names:
                character_names.append(speaker)
            segments.append(
                ScriptSegment(
                    id=len(segments) + 1,
                    speaker=speaker,
                    text=text,
                    emotion="neutral",
                    pause_ms=300,
                )
            )

    characters = [Character(name=name, voice_hint=_guess_voice(name)) for name in character_names]
    return ScriptManifest(
        title=title,
        source_url=source_url,
        language=detect_language(cleaned_text),
        characters=characters,
        segments=segments,
    )


def _call_openai_compatible(
    cleaned_text: str,
    title: str,
    source_url: str,
    api_key: str,
    base_url: str,
    model: str,
    timeout_seconds: int,
) -> str:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "title": title,
                        "source_url": source_url,
                        "cleaned_text": cleaned_text,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=timeout_seconds,
    )
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LLMError(f"LLM 请求失败：{response.text or exc}") from exc
    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"LLM 返回格式异常：{data}") from exc


def _extract_json_text(payload: str) -> str:
    candidate = payload.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.S)
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMError("LLM 未返回有效 JSON。")
    return candidate[start : end + 1]


def _validate_manifest(raw_json: str) -> ScriptManifest:
    try:
        data = json.loads(raw_json)
        return ScriptManifest.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LLMError(f"LLM 返回的 JSON 非法：{exc}") from exc


def build_manifest_llm(
    title: str,
    source_url: str,
    cleaned_text: str,
    api_key: str | None,
    base_url: str | None,
    model: str,
    timeout_seconds: int,
) -> ScriptManifest:
    if not api_key or not base_url:
        raise LLMError(
            "llm 模式需要设置 OPENAI_API_KEY 和 OPENAI_BASE_URL。"
        )

    payload = _call_openai_compatible(
        cleaned_text=cleaned_text,
        title=title,
        source_url=source_url,
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    try:
        return _validate_manifest(_extract_json_text(payload))
    except LLMError as first_error:
        LOGGER.warning("首次 JSON 校验失败，尝试修复重试：%s", first_error)
        repair_prompt = (
            "Fix this JSON to match the required schema exactly and return only JSON:\n"
            + payload
        )
        repaired = _call_openai_compatible(
            cleaned_text=repair_prompt,
            title=title,
            source_url=source_url,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
        )
        return _validate_manifest(_extract_json_text(repaired))


def create_script_outputs(
    title: str,
    source_url: str,
    cleaned_text: str,
    mode: str,
    api_key: str | None,
    base_url: str | None,
    model: str,
    timeout_seconds: int,
) -> tuple[ScriptManifest, str]:
    if mode == "heuristic":
        manifest = build_manifest_heuristic(title, source_url, cleaned_text)
    elif mode == "llm":
        manifest = build_manifest_llm(
            title=title,
            source_url=source_url,
            cleaned_text=cleaned_text,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    else:
        raise LLMError(f"不支持的 script 模式：{mode}")

    if not manifest.segments:
        raise LLMError("剧本生成失败：manifest 中没有有效 segments。")
    return manifest, _build_script_text(manifest)
