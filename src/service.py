"""HTTP endpoint that serves the fact pack.

This exists because of a constraint that is easy to miss until it breaks: **n8n cannot run
this project's Python.** The n8n container ships no interpreter and has no access to the
repo on the host, so "n8n runs the engine" is not a thing you can wire up — the two have to
talk over the network.

So the engine runs as its own service and n8n calls it. That is also how you would build
it in production, and it means the orchestration layer depends on an interface rather than
on a filesystem layout.

Run locally:
    uvicorn src.service:app --port 8000
Or via the compose stack, where n8n reaches it at http://engine:8000/facts
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from .engine import build_facts
from .loader import DataValidationError, load
from .schema import BRIEFING_SCHEMA

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = REPO_ROOT / "data" / "mock_sales.csv"
PROMPT_PATH = REPO_ROOT / "prompts" / "v2_final.md"

app = FastAPI(
    title="Manukora S&OP engine",
    description=(
        "Serves the computed fact pack for the monthly S&OP briefing. Every number in the "
        "briefing originates here. The narrative layer consumes this and writes prose "
        "around it; it never calculates."
    ),
    version="1.0.0",
)


@app.get("/health")
def health() -> dict:
    """Liveness check for the compose healthcheck.

    Loads and validates the dataset rather than just returning 200, so a malformed dataset
    stops the stack from reporting healthy while being unable to do its job.
    """
    try:
        records = load(DEFAULT_DATA)
    except DataValidationError as exc:
        raise HTTPException(status_code=503, detail=f"Dataset invalid: {exc}") from exc
    return {"status": "ok", "skus": len(records)}


@app.get("/facts")
def facts() -> dict:
    """The complete fact pack for the current reporting month.

    A 422 here means the dataset was rejected, not that the request was wrong — the detail
    names the offending line. See RUNBOOK.md.
    """
    try:
        records = load(DEFAULT_DATA)
    except DataValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return build_facts(records)


@app.get("/prompt")
def prompt() -> dict:
    """The run-time prompt and the output schema, served rather than copied.

    The n8n workflow fetches these instead of carrying its own copy. Without this the
    prompt would exist in two places — a markdown file and a node parameter — and they
    would drift the first time either was edited. The workflow orchestrates; it does not
    own the instructions.
    """
    if not PROMPT_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Prompt not found: {PROMPT_PATH}")
    return {
        "system": PROMPT_PATH.read_text(encoding="utf-8"),
        "schema": BRIEFING_SCHEMA,
        "source": "prompts/v2_final.md",
    }
