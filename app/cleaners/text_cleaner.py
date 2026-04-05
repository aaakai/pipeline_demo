"""Text cleaning routines for extracted article content."""

from __future__ import annotations

import re

from app.exceptions import CleaningError

NOISE_PATTERNS = [
    re.compile(r"^\s*(share|subscribe|comments?|kudos|bookmark)\b", re.I),
    re.compile(r"^\s*chapter\s+\d+\s*$", re.I),
    re.compile(r"^\s*posted\s+on\b", re.I),
]


def _normalize_quotes(text: str) -> str:
    replacements = {
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u00a0": " ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _is_noise_line(line: str) -> bool:
    return any(pattern.search(line) for pattern in NOISE_PATTERNS)


def clean_text(raw_text: str) -> str:
    if not raw_text or not raw_text.strip():
        raise CleaningError("无法清洗空文本。")

    text = _normalize_quotes(raw_text)
    text = re.sub(r"\r\n?", "\n", text)
    lines = [line.strip() for line in text.split("\n")]

    paragraphs: list[str] = []
    buffer: list[str] = []
    for line in lines:
        if not line:
            if buffer:
                paragraphs.append(" ".join(buffer))
                buffer = []
            continue
        if _is_noise_line(line):
            continue
        if line.endswith((".", "!", "?", '"', "'", "\u3002", "\uff01", "\uff1f")):
            buffer.append(line)
            paragraphs.append(" ".join(buffer))
            buffer = []
        else:
            buffer.append(line)

    if buffer:
        paragraphs.append(" ".join(buffer))

    cleaned = "\n\n".join(
        re.sub(r"[ \t]+", " ", paragraph).strip() for paragraph in paragraphs
    ).strip()
    if len(cleaned) < 20:
        raise CleaningError("清洗后的正文过短，可能没有提取到有效内容。")
    return cleaned
