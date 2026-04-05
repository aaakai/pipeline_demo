"""Shared helpers for configuration, logging, and file IO."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from app.schemas import MetaRecord, RuntimeConfig

LOGGER_NAME = "pipeline_demo"


def get_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    )


def ensure_outdir(path: str | Path) -> Path:
    outdir = Path(path).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def configure_logging(outdir: Path) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )

    file_handler = logging.FileHandler(outdir / "pipeline.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_meta(path: Path, meta: MetaRecord) -> None:
    write_json(path, meta.model_dump(mode="json"))


def detect_language(text: str) -> str:
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    if has_cjk and has_latin:
        return "mixed"
    if has_cjk:
        return "zh"
    return "en"
