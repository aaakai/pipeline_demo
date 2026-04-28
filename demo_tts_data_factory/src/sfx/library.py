"""SFX manifest loading."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.schemas import SFXTOSConfig, SfxAsset
from src.utils.files import ensure_dir
from src.utils.tos import fetch_sfx_event_dir


class SfxLibrary:
    def __init__(
        self,
        manifest_path: str | Path,
        project_root: Path,
        sfx_tos: SFXTOSConfig | None = None,
    ):
        self.manifest_path = (project_root / manifest_path).resolve()
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"SFX manifest not found: {self.manifest_path}")
        self.project_root = project_root
        self.sfx_tos = sfx_tos or SFXTOSConfig()
        self.logger = logging.getLogger("demo_tts_data_factory")
        self.base_dir = (
            ensure_dir((project_root / self.sfx_tos.local_cache_dir).resolve())
            if self.sfx_tos.enabled
            else self.manifest_path.parent
        )
        self._hydrated_event_types: set[str] = set()
        self.assets = self._load_assets()

    def _load_assets(self) -> list[SfxAsset]:
        records = json.loads(self.manifest_path.read_text(encoding="utf-8-sig"))
        assets = [SfxAsset(**record) for record in records]
        return assets

    def resolve_path(self, asset: SfxAsset) -> Path:
        path = Path(asset.path)
        return path if path.is_absolute() else (self.base_dir / path).resolve()

    def by_event_type(self, event_type: str) -> list[SfxAsset]:
        self._ensure_event_type_available(event_type)
        return [asset for asset in self.assets if asset.event_type == event_type]

    def _ensure_event_type_available(self, event_type: str) -> None:
        if not self.sfx_tos.enabled or event_type in self._hydrated_event_types:
            return

        event_dir_names = sorted(
            {
                Path(asset.path).parts[0]
                for asset in self.assets
                if asset.event_type == event_type and Path(asset.path).parts
            }
        )
        for event_dir_name in event_dir_names:
            fetch_sfx_event_dir(
                event_dir_name=event_dir_name,
                local_cache_dir=self.base_dir,
                config=self.sfx_tos,
                logger=self.logger,
            )
        self._hydrated_event_types.add(event_type)
