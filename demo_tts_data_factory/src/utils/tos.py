"""Helpers for syncing generated output folders to Volcengine TOS."""

from __future__ import annotations

import subprocess
from logging import Logger
from pathlib import Path

from src.schemas import TOSSyncConfig


def sync_case_dir(case_dir: Path, config: TOSSyncConfig, logger: Logger) -> None:
    if not config.enabled:
        return

    util_path = Path(config.util_path).expanduser()
    command = [str(util_path), "cp", str(case_dir), config.destination_uri]
    if config.recursive:
        command.append("-r")

    logger.info("Syncing case directory to TOS: %s -> %s", case_dir, config.destination_uri)
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("TOS sync failed for %s: %s", case_dir, exc.stderr.strip() or exc.stdout.strip())
        if config.fail_on_error:
            raise RuntimeError(f"Failed to sync case directory to TOS: {case_dir}") from exc
        return

    output = completed.stdout.strip()
    if output:
        logger.info("TOS sync completed for %s: %s", case_dir, output)
    else:
        logger.info("TOS sync completed for %s", case_dir)
