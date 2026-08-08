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
    # utf-8-sig, not utf-8: Notepad and PowerShell both write a BOM by default on Windows,
    # and a BOM turns the first line's key into "﻿ANTHROPIC_API_KEY". Nothing matches
    # it, so the file loads without error and the key silently is not there — which is how
    # this was found, on a run that quietly used the other provider.
    for raw in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_prompt(facts: dict) -> str:
    """The run-time prompt, with its one figure filled in from the engine.

    `{{WORD_ALLOWANCE}}` is what the model may write once the renderer's headings and
    fixed phrases are accounted for. Interpolated rather than typed into the file, for the
    same reason nothing else here is typed: a hand-written 750 sent the model to 755 —
    exactly on target and still over budget, because the frame costs more than 200 on top.

    `src/service.py` serves the prompt through this function too, so n8n and the CLI get
    the same instructions with the same figure.
    """
    if not PROMPT_PATH.exists():
        raise NarrativeError(f"Prompt not found: {PROMPT_PATH}")

    from .render import word_allowance

    return PROMPT_PATH.read_text(encoding="utf-8").replace(
        "{{WORD_ALLOWANCE}}", str(word_allowance(facts))
    )


class OverReadingBudget(NarrativeError):
    """The model would not come in under the five-minute ceiling.

    Its own subclass so a caller can distinguish "this briefing is too long" — a property
    of the output — from "the API failed", which is a property of the run. Only the first
    is something `--allow-over-budget` should be able to wave through.
    """

    def __init__(self, provider: str, written: int, ceiling: int) -> None:
        self.written, self.ceiling = written, ceiling
        super().__init__(
            f"{provider} stayed over the reading budget after one rewrite: {written} words "
            f"against a ceiling of {ceiling}. This is a known characteristic of some models "
            "rather than a fault — see RUNBOOK.md. Use --no-llm for the template render, or "
            "--allow-over-budget to ship it anyway."
        )


def write_prose(
    facts: dict,
    *,
    allow_over_budget: bool = False,
    provider=None,
) -> tuple[dict, str]:
    """Call the model and return the validated prose plus a label for who wrote it.

    `allow_over_budget` overrides the reading-budget refusal. It defaults to off, so the
    ceiling is enforced unless a caller explicitly opts out — the flag has to be typed, and
    its name says what typing it means.

    `provider` is injectable so tests can exercise the budget logic without a network call
    or an API key.

    Separated from `write_briefing` so tests can exercise assembly without a model.
    """
    from . import config
    from .render import compose_briefing, prose_word_count, word_allowance

    if provider is None:
        load_dotenv()
        try:
            provider = select_provider()
        except ProviderError as exc:
            raise NarrativeError(str(exc)) from exc

    user = (
        "Here is the fact pack for this month's review. Write the briefing.\n\n"
        f"```json\n{json.dumps(facts, indent=2)}\n```"
    )
    system = load_prompt(facts)

    def ask(extra: str = "") -> dict:
        try:
            return provider.generate(system, user + extra, BRIEFING_SCHEMA)
        except ProviderError as exc:
            raise NarrativeError(str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise NarrativeError(
                f"{provider.info.label} returned malformed JSON: {exc}"
            ) from exc

    def vetted(p: dict) -> int:
        """Check the contract, then measure. In that order, always.

        Rendering assumes the prose covers every SKU it was asked about — a response
        missing a rationale raises a KeyError deep inside the renderer instead of the
        contract error that says what actually went wrong. Validating first turns an
        obscure crash into a diagnosable message, and costs nothing.
        """
        check_against_facts(p, facts)
        return prose_word_count(compose_briefing(facts, p))

    prose = ask()

    # The reading budget was advisory for most of this project: over-length was printed and
    # shipped anyway. It is a stated requirement, so it gets enforced like one.
    #
    # One retry, not a loop. Models overshoot a length target by a fairly stable margin —
    # asked for 653 words, Claude wrote 713 — and quoting the actual count back is the one
    # correction worth paying for. A loop would spend money rediscovering the same thing,
    # and a model that ignores the number twice will ignore it five times.
    #
    # The retry runs whether or not the override is set: even when the caller is willing to
    # ship a long briefing, the shorter one is the better briefing.
    written = vetted(prose)
    if written > config.MAX_BRIEFING_WORDS:
        over = written - config.MAX_BRIEFING_WORDS
        prose = ask(
            f"\n\nYour draft came to {written} words once the headings and tables around it "
            f"are counted, which is {over} over the ceiling. Rewrite it at "
            f"{word_allowance(facts) - over} words or fewer. Cut whole sentences that do not "
            f"change what the reader would do — do not compress the writing into fragments, "
            f"and do not drop a recommendation."
        )
        rewritten = vetted(prose)
        if rewritten > config.MAX_BRIEFING_WORDS and not allow_over_budget:
            raise OverReadingBudget(
                provider.info.label, rewritten, config.MAX_BRIEFING_WORDS
            )

    return prose, provider.info.label


def write_briefing(facts: dict, *, allow_over_budget: bool = False) -> str:
    """Produce the finished markdown briefing.

    The model writes the prose; `render.py` renders every table and every figure from the
    fact pack. Neither half can produce the document alone, which is the point.
    """
    prose, _ = write_prose(facts, allow_over_budget=allow_over_budget)
    return compose_briefing(facts, prose)
