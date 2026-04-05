"""Optional FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.exceptions import AppError
from app.schemas import (
    ExtractionRequest,
    ExtractionResponse,
    ScriptRequest,
    ScriptResponse,
)
from app.service import run_extract, run_script
from app.utils import configure_logging, ensure_outdir, get_runtime_config

app = FastAPI(title="Pipeline Demo API", version="0.1.0")


@app.post("/extract", response_model=ExtractionResponse)
def extract_endpoint(payload: ExtractionRequest) -> ExtractionResponse:
    outdir = ensure_outdir(payload.outdir or "./output")
    configure_logging(outdir)
    config = get_runtime_config()
    try:
        document = run_extract(
            url=str(payload.url),
            outdir=outdir,
            user_agent=config.user_agent,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        return ExtractionResponse(
            title=document.title,
            source_url=document.source_url,
            cleaned_text=document.cleaned_text,
            metadata=document.metadata,
        )
    except AppError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/script", response_model=ScriptResponse)
def script_endpoint(payload: ScriptRequest) -> ScriptResponse:
    outdir = ensure_outdir(payload.outdir or "./output")
    configure_logging(outdir)
    config = get_runtime_config()
    try:
        document, manifest = run_script(
            url=str(payload.url),
            outdir=outdir,
            user_agent=config.user_agent,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
            mode=payload.mode,
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
            model=config.openai_model,
        )
        return ScriptResponse(
            title=document.title,
            source_url=document.source_url,
            cleaned_text=document.cleaned_text,
            script_manifest=manifest,
        )
    except AppError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
