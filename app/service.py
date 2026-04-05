"""High-level orchestration for CLI and API entry points."""

from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

from app.extractors import extract_document
from app.llm import create_script_outputs
from app.schemas import ExtractedDocument, MetaRecord, ScriptManifest
from app.utils import save_meta, write_json, write_text


def run_extract(
    url: str,
    outdir: Path,
    user_agent: str,
    timeout_seconds: int,
    max_retries: int,
) -> ExtractedDocument:
    document = extract_document(
        url=url,
        outdir=outdir,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
    write_text(outdir / "raw_text.txt", document.raw_text)
    write_text(outdir / "cleaned_text.txt", document.cleaned_text)
    save_meta(
        outdir / "meta.json",
        MetaRecord(
            title=document.title,
            source_url=document.source_url,
            site_type=document.metadata["site_type"],
            fetched_at=datetime.now(UTC),
            raw_html_path=document.raw_html_path,
        ),
    )
    return document


def run_script(
    url: str,
    outdir: Path,
    user_agent: str,
    timeout_seconds: int,
    max_retries: int,
    mode: str,
    api_key: str | None,
    base_url: str | None,
    model: str,
) -> tuple[ExtractedDocument, ScriptManifest]:
    document = run_extract(url, outdir, user_agent, timeout_seconds, max_retries)
    manifest, script_text = create_script_outputs(
        title=document.title,
        source_url=document.source_url,
        cleaned_text=document.cleaned_text,
        mode=mode,
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    write_text(outdir / "script.txt", script_text)
    write_json(outdir / "script_manifest.json", manifest.model_dump(mode="json"))
    save_meta(
        outdir / "meta.json",
        MetaRecord(
            title=document.title,
            source_url=document.source_url,
            site_type=document.metadata["site_type"],
            fetched_at=datetime.now(UTC),
            mode=mode,
            raw_html_path=document.raw_html_path,
        ),
    )
    return document, manifest
