"""LLM enhancer placeholder.

TODO: Replace this class with an OpenAI-compatible client when real semantic
event tagging is desired. It intentionally does not call any external API.
"""

from __future__ import annotations

from src.enhancer.base import ScriptEnhancer
from src.enhancer.rule_based import RuleBasedEnhancer
from src.schemas import EnhancementResult


class LLMEnhancerStub(ScriptEnhancer):
    def __init__(self) -> None:
        self._fallback = RuleBasedEnhancer()

    def enhance(
        self,
        plain_text: str,
        scene: str,
        emotion: str,
        allowed_events: list[str],
    ) -> EnhancementResult:
        return self._fallback.enhance(plain_text, scene, emotion, allowed_events)
