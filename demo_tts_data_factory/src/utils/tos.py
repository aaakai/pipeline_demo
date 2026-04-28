"""Helpers for syncing generated output folders to and from Volcengine TOS."""

from __future__ import annotations

import re
import shutil
import subprocess
from logging import Logger
from pathlib import Path

from src.schemas import SFXTOSConfig, TOSInputConfig, TOSSyncConfig
from src.utils.files import ensure_dir


def list_sfx_objects(
    config: SFXTOSConfig,
    logger: Logger,
    allowed_extensions: set[str] | None = None,
    allowed_names: set[str] | None = None,
) -> list[str]:
    if not config.enabled:
        return []
    if not config.source_uri:
        raise ValueError("SFX TOS is enabled but source_uri is empty.")

    util_path = Path(config.util_path).expanduser()
    command = [str(util_path), "ls", config.source_uri]
    completed = _run_tos_command(
        command,
        logger,
        action=f"list TOS SFX objects under {config.source_uri}",
        fail_on_error=config.fail_on_error,
    )
    if completed is None:
        return []

    object_uris = _parse_tos_ls_output(completed.stdout, config.source_uri)
    if allowed_extensions or allowed_names:
        lowered_extensions = {item.lower() for item in allowed_extensions or set()}
        allowed_names = allowed_names or set()
        object_uris = [
            uri
            for uri in object_uris
            if Path(uri).suffix.lower() in lowered_extensions or Path(uri).name in allowed_names
        ]
    logger.info("Discovered %s SFX object(s) from TOS source %s", len(object_uris), config.source_uri)
    return object_uris


def list_input_objects(
    config: TOSInputConfig,
    logger: Logger,
    allowed_extensions: set[str] | None = None,
) -> list[str]:
    if not config.enabled:
        return []
    if not config.source_uri:
        raise ValueError("TOS input is enabled but source_uri is empty.")

    util_path = Path(config.util_path).expanduser()
    command = [str(util_path), "ls", config.source_uri]
    completed = _run_tos_command(
        command,
        logger,
        action=f"list TOS input objects under {config.source_uri}",
        fail_on_error=config.fail_on_error,
    )
    if completed is None:
        return []

    object_uris = _parse_tos_ls_output(completed.stdout, config.source_uri)
    if allowed_extensions:
        lowered = {item.lower() for item in allowed_extensions}
        object_uris = [
            uri for uri in object_uris if Path(uri).suffix.lower() in lowered
        ]
    logger.info("Discovered %s input object(s) from TOS source %s", len(object_uris), config.source_uri)
    return object_uris


def fetch_input_object(remote_uri: str, local_path: Path, config: TOSInputConfig, logger: Logger) -> None:
    if not config.enabled:
        return

    ensure_dir(local_path.parent)
    util_path = Path(config.util_path).expanduser()
    command = [str(util_path), "cp", remote_uri, str(local_path)]
    completed = _run_tos_command(
        command,
        logger,
        action=f"fetch TOS input object {remote_uri}",
        fail_on_error=config.fail_on_error,
    )
    if completed is None:
        return

    output = completed.stdout.strip()
    if output:
        logger.info("TOS input fetch completed for %s: %s", remote_uri, output)
    else:
        logger.info("TOS input fetch completed for %s", remote_uri)


def fetch_sfx_object(remote_uri: str, local_path: Path, config: SFXTOSConfig, logger: Logger) -> None:
    if not config.enabled:
        return

    ensure_dir(local_path.parent)
    util_path = Path(config.util_path).expanduser()
    command = [str(util_path), "cp", remote_uri, str(local_path)]
    completed = _run_tos_command(
        command,
        logger,
        action=f"fetch TOS SFX object {remote_uri}",
        fail_on_error=config.fail_on_error,
    )
    if completed is None:
        return

    output = completed.stdout.strip()
    if output:
        logger.info("TOS SFX object fetch completed for %s: %s", remote_uri, output)
    else:
        logger.info("TOS SFX object fetch completed for %s", remote_uri)


def fetch_sfx_event_dir(
    event_dir_name: str,
    local_cache_dir: Path,
    config: SFXTOSConfig,
    logger: Logger,
) -> Path:
    if not config.enabled:
        return local_cache_dir / event_dir_name
    if not config.source_uri:
        raise ValueError("SFX TOS is enabled but source_uri is empty.")

    target_dir = ensure_dir(local_cache_dir)
    remote_uri = _join_tos_uri(config.source_uri, event_dir_name)
    util_path = Path(config.util_path).expanduser()
    command = [str(util_path), "cp", remote_uri, str(target_dir)]
    if config.recursive:
        command.append("-r")
    completed = _run_tos_command(
        command,
        logger,
        action=f"fetch SFX event directory {remote_uri}",
        fail_on_error=config.fail_on_error,
    )
    if completed is None:
        return target_dir

    output = completed.stdout.strip()
    if output:
        logger.info("TOS SFX fetch completed for %s: %s", remote_uri, output)
    else:
        logger.info("TOS SFX fetch completed for %s", remote_uri)
    return target_dir / event_dir_name


def sync_case_dir(case_dir: Path, config: TOSSyncConfig, logger: Logger) -> None:
    if not config.enabled:
        return

    util_path = Path(config.util_path).expanduser()
    command = [str(util_path), "cp", str(case_dir), config.destination_uri]
    if config.recursive:
        command.append("-r")

    logger.info("Syncing case directory to TOS: %s -> %s", case_dir, config.destination_uri)
    completed = _run_tos_command(
        command,
        logger,
        action=f"sync case directory to TOS: {case_dir}",
        fail_on_error=config.fail_on_error,
    )
    if completed is None:
        return

    output = completed.stdout.strip()
    if output:
        logger.info("TOS sync completed for %s: %s", case_dir, output)
    else:
        logger.info("TOS sync completed for %s", case_dir)


def _clear_directory(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def clear_local_input_dir(local_dir: Path) -> None:
    if local_dir.exists():
        _clear_directory(local_dir)


def remote_uri_to_relative_path(remote_uri: str, source_uri: str) -> Path:
    _, source_key = _split_tos_uri(source_uri)
    _, remote_key = _split_tos_uri(remote_uri)
    source_prefix = source_key.strip("/")
    remote_path = remote_key.strip("/")
    if source_prefix:
        prefix = source_prefix + "/"
        if remote_path == source_prefix:
            return Path(Path(remote_path).name)
        if remote_path.startswith(prefix):
            remote_path = remote_path[len(prefix):]
    return Path(remote_path)


def _parse_tos_ls_output(output: str, source_uri: str) -> list[str]:
    object_uris: list[str] = []
    bucket, source_key = _split_tos_uri(source_uri)
    source_prefix = source_key.strip("/")
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("tos://"):
            candidate = stripped
        else:
            match = re.search(r"tos://[^\s]+", stripped)
            if match:
                candidate = match.group(0)
            else:
                parts = stripped.split()
                if not parts:
                    continue
                last_part = parts[-1].strip()
                if last_part.endswith("/"):
                    continue
                if source_prefix and not last_part.startswith(source_prefix):
                    continue
                if "/" not in last_part and "." not in last_part:
                    continue
                candidate = f"tos://{bucket}/{last_part.lstrip('/')}"
        if candidate.endswith("/"):
            continue
        object_uris.append(candidate)
    return sorted(dict.fromkeys(object_uris))


def _split_tos_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("tos://"):
        raise ValueError(f"Unsupported TOS URI: {uri}")
    remainder = uri[len("tos://") :]
    bucket, _, key = remainder.partition("/")
    return bucket, key


def _join_tos_uri(base_uri: str, suffix: str) -> str:
    return base_uri.rstrip("/") + "/" + suffix.strip("/")


def _run_tos_command(
    command: list[str],
    logger: Logger,
    action: str,
    fail_on_error: bool,
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("TOS command failed while trying to %s: %s", action, exc.stderr.strip() or exc.stdout.strip())
        if fail_on_error:
            raise RuntimeError(f"Failed to {action}") from exc
        return None
