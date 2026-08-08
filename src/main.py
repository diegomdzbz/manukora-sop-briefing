"""Command line entry point.

    python -m src.main --no-llm      full briefing, no API key needed
    python -m src.main               briefing written by the narrative layer
    python -m src.main --facts-only  just the fact pack, for the n8n workflow
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config
from .engine import build_facts
from .loader import DataValidationError, load

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = REPO_ROOT / "data" / "mock_sales.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="Generate the monthly S&OP briefing from the sales dataset.",
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Path to the dataset CSV")
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Where to write the briefing"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--no-llm",
        action="store_true",
        help="Render the briefing from a deterministic template instead of calling the model. "
        "Requires no API key and produces the same figures.",
    )
    mode.add_argument(
        "--facts-only",
        action="store_true",
        help="Write only the fact pack. Used by the n8n workflow.",
    )
    parser.add_argument(
        "--stdout", action="store_true", help="Also print the briefing to standard output"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        records = load(args.data)
    except DataValidationError as exc:
        print(f"Dataset rejected: {exc}", file=sys.stderr)
        return 2

    facts = build_facts(records)
    month_slug = facts["meta"]["reporting_month"].replace(" ", "-").lower()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    facts_path = args.output_dir / f"facts_{month_slug}.json"
    facts_path.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    print(f"Fact pack written to {facts_path}")

    if args.facts_only:
        return 0

    if args.no_llm:
        from .render import render_briefing

        briefing = render_briefing(facts)
        source = "deterministic template"
    else:
        from .narrative import write_prose
        from .render import compose_briefing

        try:
            prose, source = write_prose(facts)
        except Exception as exc:  # noqa: BLE001 - surfaced to the operator, see RUNBOOK.md
            print(f"Narrative layer failed: {exc}", file=sys.stderr)
            print("Re-run with --no-llm for the template briefing.", file=sys.stderr)
            return 1
        briefing = compose_briefing(facts, prose)

    from .render import prose_word_count

    # The two paths write to different files so both can be committed. The model-written
    # briefing is the deliverable; the template render is the control that CI regenerates
    # and diffs, since only it is deterministic.
    suffix = "_template" if args.no_llm else ""
    briefing_path = args.output_dir / f"sop_briefing_{month_slug}{suffix}.md"
    briefing_path.write_text(briefing, encoding="utf-8")
    words = prose_word_count(briefing)
    budget = "within" if words <= config.MAX_BRIEFING_WORDS else "OVER"
    print(
        f"Briefing written to {briefing_path} "
        f"({source}, {words} prose words, {budget} the {config.MAX_BRIEFING_WORDS} budget)"
    )

    if args.stdout:
        print()
        print(briefing)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
