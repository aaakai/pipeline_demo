"""YAML configuration loading."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from src.schemas import (
    AppConfig,
    LLMEnhancerConfig,
    MergeConfig,
    MixConfig,
    OpenAITTSConfig,
    StyleConfig,
)


def load_dotenv_local(project_root: Path) -> None:
    """Load local env vars without requiring python-dotenv.

    Existing process environment values win. This keeps secrets out of YAML
    while still letting GUI-launched processes read a local key file.
    """
    for env_file in (project_root / ".env.local", project_root / ".env"):
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    load_dotenv_local(path.parents[1])

    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mix_data = data.get("mix") or {}
    merge_data = data.get("merge") or {}
    style_data = data.get("style") or {}
    llm_enhancer_data = data.get("llm_enhancer") or {}
    openai_tts_data = data.get("openai_tts") or {}
    return AppConfig(
        input_mode=data.get("input_mode", "single"),
        text=data.get("text", ""),
        scene=data.get("scene", "default"),
        emotion=data.get("emotion", "neutral"),
        allowed_events=list(data.get("allowed_events") or []),
        clean_voice_path=data.get("clean_voice_path"),
        sfx_manifest_path=data.get("sfx_manifest_path", "assets/sfx/manifest.json"),
        sample_rate=int(data.get("sample_rate", 24000)),
        channels=int(data.get("channels", 1)),
        output_dir=data.get("output_dir", "output"),
        batch_input_path=data.get("batch_input_path", "examples/demo_inputs.jsonl"),
        scene_templates_path=data.get("scene_templates_path", "configs/scene_templates.yaml"),
        enhancer=data.get("enhancer", "rule_based"),
        llm_enhancer=LLMEnhancerConfig(
            api_key_env=llm_enhancer_data.get("api_key_env", "OPENAI_API_KEY"),
            base_url=llm_enhancer_data.get("base_url", "https://api.openai.com/v1"),
            model=llm_enhancer_data.get("model", "gpt-4o-mini"),
            temperature=float(llm_enhancer_data.get("temperature", 0.2)),
            timeout_seconds=int(llm_enhancer_data.get("timeout_seconds", 60)),
        ),
        tts_provider=data.get("tts_provider", "mock"),
        openai_tts=OpenAITTSConfig(
            api_key_env=openai_tts_data.get("api_key_env", "OPENAI_API_KEY"),
            base_url=openai_tts_data.get("base_url", "https://api.openai.com/v1"),
            model=openai_tts_data.get("model", "gpt-4o-mini-tts"),
            voice=openai_tts_data.get("voice", "coral"),
            instructions=openai_tts_data.get("instructions"),
            response_format=openai_tts_data.get("response_format", "wav"),
            speed=float(openai_tts_data.get("speed", 1.0)),
        ),
        mix=MixConfig(
            speech_gain_db=float(mix_data.get("speech_gain_db", 0.0)),
            default_ducking_db=float(mix_data.get("default_ducking_db", -4.0)),
            fade_ms=int(mix_data.get("fade_ms", 15)),
            background_gain_db=float(mix_data.get("background_gain_db", -18.0)),
        ),
        merge=MergeConfig(
            enabled=bool(merge_data.get("enabled", True)),
            same_event_gap_ms=int(merge_data.get("same_event_gap_ms", 350)),
            cloth_rustle_merge_gap_ms=int(merge_data.get("cloth_rustle_merge_gap_ms", 700)),
        ),
        style=StyleConfig(
            enable_keyword_style=bool(style_data.get("enable_keyword_style", True)),
            enable_brief_style=bool(style_data.get("enable_brief_style", True)),
        ),
        random_seed=data.get("random_seed"),
    )
