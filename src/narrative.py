"""The narrative layer.

Receives the fact pack, returns prose. It never calculates anything, and the schema in
`schema.py` makes that structural rather than aspirational: the model can only return the
fields defined there, and none of them is a number.

The provider is chosen by whichever key is present — see `providers.py`. Everything else in
this project (the engine, the tests, the `--no-llm` briefing) runs with no key at all.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .providers import ProviderError, select_provider
from .render import compose_briefing
from .schema import BRIEFING_SCHEMA, check_against_facts

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = REPO_ROOT / "prompts" / "v2_final.md"


class NarrativeError(RuntimeError):
    """The narrative layer could not produce a briefing. See RUNBOOK.md."""


def load_dotenv() -> None:
    """Read `.env` into the environment if it exists.

    Hand-rolled rather than pulling in python-dotenv: it is a dozen lines, and the point of
    this project is that a reviewer can clone it and run everything without installing
    dependencies they did not choose. An already-set environment variable wins, so CI and
    shell exports are never silently overridden by a stale file.
    """
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise NarrativeError(f"Prompt not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def write_prose(facts: dict) -> tuple[dict, str]:
    """Call the model and return the validated prose plus a label for who wrote it.

    Separated from `write_briefing` so tests can exercise assembly without a network call.
    """
    load_dotenv()

    try:
        provider = select_provider()
    except ProviderError as exc:
        raise NarrativeError(str(exc)) from exc

    user = (
        "Here is the fact pack for this month's review. Write the briefing.\n\n"
        f"```json\n{json.dumps(facts, indent=2)}\n```"
    )

    try:
        prose = provider.generate(_load_prompt(), user, BRIEFING_SCHEMA)
    except ProviderError as exc:
        raise NarrativeError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise NarrativeError(f"{provider.info.label} returned malformed JSON: {exc}") from exc

    # The schema guarantees shape; this guarantees the prose is about the SKUs we asked
    # about. A briefing that silently drops a reorder recommendation is worse than one
    # that fails loudly.
    check_against_facts(prose, facts)
    return prose, provider.info.label


def write_briefing(facts: dict) -> str:
    """Produce the finished markdown briefing.

    The model writes the prose; `render.py` renders every table and every figure from the
    fact pack. Neither half can produce the document alone, which is the point.
    """
    prose, _ = write_prose(facts)
    return compose_briefing(facts, prose)
