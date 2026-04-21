"""Enhancer interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.schemas import EnhancementResult


class ScriptEnhancer(ABC):
    @abstractmethod
    def enhance(
        self,
        plain_text: str,
        scene: str,
        emotion: str,
        allowed_events: list[str],
    ) -> EnhancementResult:
        """Convert plain text into candidate acoustic events."""
