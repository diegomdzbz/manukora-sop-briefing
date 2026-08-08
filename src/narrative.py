"""The narrative layer.

Receives the fact pack, returns prose. It never calculates anything, and the schema in
`schema.py` makes that structural rather than aspirational: the model can only return the
fields defined there, and none of them is a number.

Requires ANTHROPIC_API_KEY. Everything else in this project — the engine, the tests, and
the `--no-llm` briefing — runs without it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import config
from .render import compose_briefing
from .schema import BRIEFING_SCHEMA, check_against_facts

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = REPO_ROOT / "prompts" / "v2_final.md"

MODEL = "claude-opus-5"

# The reasoning is already done. Every number, ranking, threshold and tension in the fact
# pack was computed and tested before this call is made; the model's job is to write it up
# for a reader. Medium is the right tier for that, and it is a deliberate cost decision
# rather than a default we never revisited.
EFFORT = "medium"

# Generous because thinking and response text share this budget on this model, and a
# briefing that truncates mid-recommendation is worse than one that costs a few cents more.
MAX_TOKENS = 16000


class NarrativeError(RuntimeError):
    """The narrative layer could not produce a briefing. See RUNBOOK.md."""


def _load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise NarrativeError(f"Prompt not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def write_prose(facts: dict) -> dict:
    """Call the model and return the validated prose object.

    Separated from `write_briefing` so tests can exercise assembly without a network call.
    """
    try:
        import anthropic
    except ImportError as exc:  # noqa: TRY003 - the fix is one command, say it
        raise NarrativeError(
            "The `anthropic` package is not installed. Run `pip install anthropic`, "
            "or use `--no-llm` to render the briefing without a model."
        ) from exc

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise NarrativeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in, "
            "or use `--no-llm` to render the briefing without a model."
        )

    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_load_prompt(),
            output_config={
                "effort": EFFORT,
                "format": {"type": "json_schema", "schema": BRIEFING_SCHEMA},
            },
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Here is the fact pack for this month's review. Write the briefing.\n\n"
                        f"```json\n{json.dumps(facts, indent=2)}\n```"
                    ),
                }
            ],
        )
    except anthropic.APIStatusError as exc:
        raise NarrativeError(f"Claude API returned {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise NarrativeError(f"Could not reach the Claude API: {exc}") from exc

    if response.stop_reason == "max_tokens":
        raise NarrativeError(
            f"Response hit the {MAX_TOKENS} token ceiling and is incomplete. "
            "Raise MAX_TOKENS or lower EFFORT."
        )
    if response.stop_reason == "refusal":
        raise NarrativeError("The model declined this request. See RUNBOOK.md.")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise NarrativeError("The model returned no text block.")

    prose = json.loads(text)

    # The schema guarantees shape; this guarantees the prose is about the SKUs we asked
    # about. A briefing that silently drops a reorder recommendation is worse than one
    # that fails loudly.
    check_against_facts(prose, facts)
    return prose


def write_briefing(facts: dict) -> str:
    """Produce the finished markdown briefing.

    The model writes the prose; `render.py` renders every table and every figure from the
    fact pack. Neither half can produce the document alone, which is the point.
    """
    return compose_briefing(facts, prose=write_prose(facts))
