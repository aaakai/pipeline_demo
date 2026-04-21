"""SFX manifest loading."""

from __future__ import annotations

import json
from pathlib import Path

from src.schemas import SfxAsset


class SfxLibrary:
    def __init__(self, manifest_path: str | Path, project_root: Path):
        self.manifest_path = (project_root / manifest_path).resolve()
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"SFX manifest not found: {self.manifest_path}")
        self.base_dir = self.manifest_path.parent
        self.assets = self._load_assets()

    def _load_assets(self) -> list[SfxAsset]:
        records = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        assets = [SfxAsset(**record) for record in records]
        return assets

    def resolve_path(self, asset: SfxAsset) -> Path:
        path = Path(asset.path)
        return path if path.is_absolute() else (self.base_dir / path).resolve()

    def by_event_type(self, event_type: str) -> list[SfxAsset]:
        return [asset for asset in self.assets if asset.event_type == event_type]
