"""Typer-powered command line interface."""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from app.exceptions import AppError
from app.service import run_extract, run_script
from app.utils import configure_logging, ensure_outdir, get_runtime_config

cli = typer.Typer(help="Single URL text extractor and script adapter.")


@cli.command()
def extract(
    url: str = typer.Option(..., "--url", help="Public webpage URL."),
    outdir: str = typer.Option("./output", "--outdir", help="Output directory."),
) -> None:
    target_dir = ensure_outdir(outdir)
    logger = configure_logging(target_dir)
    config = get_runtime_config()
    try:
        document = run_extract(
            url=url,
            outdir=target_dir,
            user_agent=config.user_agent,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        logger.info("Extraction completed for %s", url)
        typer.echo(f"title: {document.title}")
        typer.echo(f"cleaned_text_path: {target_dir / 'cleaned_text.txt'}")
    except AppError as exc:
        logger.error("Extraction failed: %s", exc)
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@cli.command()
def script(
    url: str = typer.Option(..., "--url", help="Public webpage URL."),
    outdir: str = typer.Option("./output", "--outdir", help="Output directory."),
    mode: str = typer.Option("heuristic", "--mode", help="heuristic or llm."),
) -> None:
    target_dir = ensure_outdir(outdir)
    logger = configure_logging(target_dir)
    config = get_runtime_config()
    try:
        document, manifest = run_script(
            url=url,
            outdir=target_dir,
            user_agent=config.user_agent,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
            mode=mode,
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
            model=config.openai_model,
        )
        logger.info("Script generation completed for %s with mode=%s", url, mode)
        typer.echo(f"title: {document.title}")
        typer.echo(f"segments: {len(manifest.segments)}")
        typer.echo(f"manifest_path: {target_dir / 'script_manifest.json'}")
    except AppError as exc:
        logger.error("Script generation failed: %s", exc)
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


def main() -> None:
    try:
        cli()
    except Exception as exc:  # pragma: no cover - defensive fallback
        logging.getLogger("pipeline_demo").exception("Unexpected error: %s", exc)
        raise


if __name__ == "__main__":
    main()
