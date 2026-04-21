"""CLI entry point."""

from __future__ import annotations

from pathlib import Path

import typer

from src.pipeline import run_from_config

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


@app.command(hidden=True)
def version() -> None:
    """Keep Typer in multi-command mode while preserving the requested run command."""
    typer.echo("demo_tts_data_factory 0.1.0")


if __name__ == "__main__":
    app()
