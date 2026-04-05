"""Adapt cleaned text into a structured radio-drama style script."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests
from pydantic import ValidationError

from app.exceptions import LLMError
from app.schemas import Character, ScriptManifest, ScriptSegment
from app.utils import detect_language

LOGGER = logging.getLogger("pipeline_demo")
SPEECH_VERBS = (
    "说",
    "问",
    "答",
    "道",
    "喊",
    "叫",
    "笑",
    "表示",
    "嘀咕",
    "低声",
    "开口",
    "said",
    "asked",
    "replied",
    "whispered",
    "murmured",
)
STOPWORD_NAMES = {
    "他",
    "她",
    "他们",
    "她们",
    "我们",
    "你",
    "你们",
    "我",
    "大家",
    "有人",
    "自己",
    "对方",
    "时候",
    "声音",
    "平安夜",
    "Chapter",
    "Text",
}
LATIN_NAME_PATTERN = r"(?<![A-Za-z0-9_-])[A-Z][A-Za-z0-9_-]{1,30}(?![A-Za-z0-9_-])"
CJK_NAME_PATTERN = r"[\u4e00-\u9fff]{2,4}"
TRIMMABLE_CJK_EDGE_CHARS = "说道问答喊叫笑看想走望点听站捏抱开回拿给将把着了过地得的里上下去来进出很也还又都在向跟和与让便正就却并"

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


def _extract_name_candidates(text: str) -> list[str]:
    patterns = [LATIN_NAME_PATTERN, CJK_NAME_PATTERN]
    candidates: list[str] = []
    for pattern in patterns:
        candidates.extend(re.findall(pattern, text))
    normalized: list[str] = []
    for name in candidates:
        if re.fullmatch(CJK_NAME_PATTERN, name):
            trimmed = name.strip(TRIMMABLE_CJK_EDGE_CHARS)
            while len(trimmed) >= 2 and trimmed[-1] in TRIMMABLE_CJK_EDGE_CHARS:
                trimmed = trimmed[:-1]
            while len(trimmed) >= 2 and trimmed[0] in TRIMMABLE_CJK_EDGE_CHARS:
                trimmed = trimmed[1:]
            name = trimmed
        if len(name) >= 2 and name not in STOPWORD_NAMES:
            normalized.append(name)
    return normalized


def _infer_known_names(cleaned_text: str) -> set[str]:
    counts: dict[str, int] = {}
    for match in re.finditer(r'"([^"]+)"', cleaned_text):
        window = cleaned_text[max(0, match.start() - 80) : min(len(cleaned_text), match.end() + 80)]
        for name in _extract_name_candidates(window):
            counts[name] = counts.get(name, 0) + 1

    known_names: set[str] = set()
    for name, count in counts.items():
        full_count = cleaned_text.count(name)
        if re.fullmatch(LATIN_NAME_PATTERN, name) and count >= 1 and full_count >= 2:
            known_names.add(name)
        elif re.fullmatch(CJK_NAME_PATTERN, name) and count >= 2 and full_count >= 2:
            known_names.add(name)
    return known_names


def _pick_named_speaker(before: str, after: str, known_names: set[str]) -> str | None:
    before_window = before[-60:]
    after_window = after[:60]

    known_name_pattern = "|".join(sorted((re.escape(name) for name in known_names), key=len, reverse=True))
    if not known_name_pattern:
        return None

    explicit_patterns = [
        rf"({known_name_pattern})[^\"\n]{{0,16}}(?:{'|'.join(SPEECH_VERBS)})",
        rf"(?:{'|'.join(SPEECH_VERBS)})[^\"\n]{{0,16}}({known_name_pattern})",
    ]
    for window in (before_window, after_window):
        for pattern in explicit_patterns:
            matches = re.findall(pattern, window, flags=re.IGNORECASE)
            for match in reversed(matches):
                if match and match not in STOPWORD_NAMES:
                    return match

    before_names = [name for name in _extract_name_candidates(before_window) if name in known_names]
    if before_names:
        return before_names[-1]
    after_names = [name for name in _extract_name_candidates(after_window) if name in known_names]
    if after_names:
        return after_names[0]
    return None


def _next_placeholder(state: dict[str, Any]) -> str:
    placeholders = ["CHARACTER_A", "CHARACTER_B"]
    index = state.get("placeholder_index", 0)
    speaker = placeholders[index % len(placeholders)]
    state["placeholder_index"] = index + 1
    return speaker


def _split_dialogue(
    paragraph: str,
    state: dict[str, Any],
    known_names: set[str],
) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    pattern = r'"([^"]+)"'
    matches = list(re.finditer(pattern, paragraph))
    if not matches:
        return [("NARRATOR", paragraph)]

    cursor = 0
    for match in matches:
        before = paragraph[cursor:match.start()].strip(" ,")
        after = paragraph[match.end() :].strip(" ,")
        if before:
            parts.append(("NARRATOR", before))
        speaker = _pick_named_speaker(before, after, known_names)
        if not speaker:
            previous = state.get("last_dialogue_speaker")
            speaker = previous if previous and previous != "NARRATOR" else _next_placeholder(state)
        parts.append((speaker, match.group(1).strip()))
        state["last_dialogue_speaker"] = speaker
        cursor = match.end()
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
    state: dict[str, Any] = {"placeholder_index": 0, "last_dialogue_speaker": None}
    known_names = _infer_known_names(cleaned_text)

    for paragraph in paragraphs:
        for speaker, text in _split_dialogue(paragraph, state, known_names):
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
