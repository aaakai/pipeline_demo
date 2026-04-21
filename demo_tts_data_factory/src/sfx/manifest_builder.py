"""Build SFX manifests by scanning the local asset directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from src.audio.analyze import analyze_audio
from src.schemas import AssetScanConfig
from src.sfx.taxonomy import TAXONOMY
from src.utils.files import write_json


def build_manifest(
    sfx_dir: str | Path,
    manifest_path: str | Path,
    config: AssetScanConfig,
) -> list[dict[str, Any]]:
    root = Path(sfx_dir).expanduser().resolve()
    manifest = Path(manifest_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"SFX directory not found: {root}")

    existing_by_path = _load_existing(manifest) if config.preserve_manual_overrides else {}
    overrides = _load_overrides(root / "manifest_overrides.yaml")
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    extensions = {item.lower() for item in config.audio_extensions}
    for path in sorted(root.glob("*/*")):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        event_type = path.parent.name
        if event_type not in TAXONOMY:
            continue
        rel_path = path.relative_to(root).as_posix()
        previous = existing_by_path.get(rel_path, {})
        analysis = analyze_audio(path, event_type)
        asset_id = _unique_asset_id(previous.get("asset_id") or path.stem, seen_ids)
        record: dict[str, Any] = {
            "asset_id": asset_id,
            "path": rel_path,
            "event_type": event_type,
            "duration_ms": analysis.duration_ms,
            "tags": previous.get("tags") or _default_tags(event_type),
            "intensity": previous.get("intensity")
            if not config.auto_intensity and "intensity" in previous
            else analysis.estimated_intensity,
            "sample_rate": analysis.sample_rate,
            "channels": analysis.channels,
            "analysis": analysis.as_dict(),
        }
        record.update(overrides.get(rel_path, {}))
        record.update(overrides.get(asset_id, {}))
        records.append(record)

    write_json(manifest, records)
    return records


def _load_existing(manifest_path: Path) -> dict[str, dict[str, Any]]:
    if not manifest_path.exists():
        return {}
    records = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {record["path"]: record for record in records if "path" in record}


def _load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _default_tags(event_type: str) -> list[str]:
    taxonomy = TAXONOMY[event_type]
    layer = "foreground" if taxonomy.foreground else "background"
    return [*taxonomy.tags, taxonomy.category, layer]


def _unique_asset_id(candidate: str, seen_ids: set[str]) -> str:
    safe = candidate.replace(" ", "_")
    if safe not in seen_ids:
        seen_ids.add(safe)
        return safe
    index = 2
    while f"{safe}_{index}" in seen_ids:
        index += 1
    unique = f"{safe}_{index}"
    seen_ids.add(unique)
    return unique
