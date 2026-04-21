"""Approximate text-anchor to timeline mapping."""

from __future__ import annotations


def anchor_to_ms(text: str, anchor_text: str, total_duration_ms: int) -> int:
    if not text:
        return 0
    index = text.find(anchor_text)
    if index < 0:
        index = len(text) // 2
    ratio = min(max(index / max(len(text), 1), 0.0), 1.0)
    return int(total_duration_ms * ratio)
