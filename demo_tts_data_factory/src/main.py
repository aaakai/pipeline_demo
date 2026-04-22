"""CLI entry point."""

from __future__ import annotations

from pathlib import Path

import typer

from src.config import load_config
from src.dialogue.pipeline import run_dialogue_from_config
from src.pipeline import run_from_config
from src.sfx.manifest_builder import build_manifest

app = typer.Typer(help="Generate demo TTS data with SFX timeline mixing.")


@app.command()
def run(
    config: str = typer.Option("configs/demo.yaml", "--config", help="Path to YAML config."),
    plan_only: bool = typer.Option(
        False,
        "--plan-only",
        help="Only generate script and metadata; skip TTS and audio mixing.",
    ),
) -> None:
    config_path = Path(config)
    manifests = run_from_config(config_path, plan_only=plan_only)
    typer.echo(f"Generated {len(manifests)} case(s).")
    for item in manifests:
        target = item.get("final_mix") or item["metadata"]
        typer.echo(f"- {item['case_id']}: {target}")


@app.command("scan-assets")
def scan_assets(
    config: str = typer.Option("configs/demo.yaml", "--config", help="Path to YAML config."),
) -> None:
    config_path = Path(config).expanduser().resolve()
    project_root = config_path.parents[1]
    app_config = load_config(config_path)
    manifest_path = (project_root / app_config.sfx_manifest_path).resolve()
    records = build_manifest(
        sfx_dir=manifest_path.parent,
        manifest_path=manifest_path,
        config=app_config.asset_scan,
    )
    typer.echo(f"Wrote {len(records)} asset record(s): {manifest_path}")


@app.command("mix-dialogue")
def mix_dialogue(
    config: str = typer.Option(
        "configs/dialogue_audio.yaml",
        "--config",
        help="Path to YAML config.",
    ),
    audio: str | None = typer.Option(
        None,
        "--audio",
        help="Optional dialogue audio path. If omitted, the newest file in input/ is used.",
    ),
) -> None:
    manifests = run_dialogue_from_config(Path(config), audio_path=audio)
    typer.echo(f"Generated {len(manifests)} dialogue mix case(s).")
    for item in manifests:
        typer.echo(f"- {item['case_id']}: {item['final_mix']}")


@app.command(hidden=True)
def version() -> None:
    """Keep Typer in multi-command mode while preserving the requested run command."""
    typer.echo("demo_tts_data_factory 0.1.0")


if __name__ == "__main__":
    app()
