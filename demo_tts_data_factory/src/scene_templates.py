"""Scene template loading and access."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.schemas import SceneTemplate


class SceneTemplateStore:
    def __init__(self, template_path: str | Path, project_root: Path):
        path = Path(template_path)
        self.template_path = path if path.is_absolute() else (project_root / path)
        if not self.template_path.exists():
            raise FileNotFoundError(f"Scene template file not found: {self.template_path}")
        self.templates = self._load_templates()

    def get(self, scene: str) -> SceneTemplate:
        if scene in self.templates:
            return self.templates[scene]
        if "indoor_argument" in self.templates:
            return self.templates["indoor_argument"]
        raise KeyError(f"Scene template not found: {scene}")

    def _load_templates(self) -> dict[str, SceneTemplate]:
        data: dict[str, Any] = yaml.safe_load(
            self.template_path.read_text(encoding="utf-8")
        ) or {}
        templates: dict[str, SceneTemplate] = {}
        for name, record in data.items():
            templates[name] = SceneTemplate(
                name=name,
                allowed_foreground_events=list(record.get("allowed_foreground_events") or []),
                allowed_background_events=list(record.get("allowed_background_events") or []),
                default_background_events=list(record.get("default_background_events") or []),
                max_foreground_events=int(record.get("max_foreground_events", 4)),
                max_total_events=int(record.get("max_total_events", 6)),
                overlap_policy=dict(record.get("overlap_policy") or {}),
                emotion_bias=dict(record.get("emotion_bias") or {}),
                event_density_level=record.get("event_density_level", "medium"),
                max_strong_events=int(record.get("max_strong_events", 2)),
            )
        return templates
