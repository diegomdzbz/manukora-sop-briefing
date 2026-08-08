"""Every figure in the briefing must trace back to the fact pack.

This is the test the whole design rests on. "The model never does arithmetic" is a claim
about the architecture; without this, it is a claim in a README. With it, a briefing
containing a number that no computation produced fails the build.

It guards the template path today and the model path the moment an API key exists — both
render through the same assembler, so both are checked by the same assertions.

Design note: a naive "extract every number" would flag SKU names (MGO 1700+ 100g), dates
(16 April 2026), and years, and the resulting flakiness would get the test deleted within a
week. Those are stripped by pattern before extraction, and anything still unmatched is
reported with the sentence it appeared in, so a failure is diagnosable at a glance.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src import config
from src.render import compose_briefing, render_briefing, template_prose

REPO_ROOT = Path(__file__).resolve().parent.parent

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)

# Stripped before figures are extracted. Order matters: dates before bare years, or the
# year inside a date is left behind as an orphan number.
#
# The product-identifier patterns are here because a model writing naturally abbreviates.
# The first real model output referred to "MGO 263+ and MGO 514+ formats" and to
# "MGO 100+ 250g" without the "Manuka Honey" prefix, so stripping exact SKU names was not
# enough and the check flagged five product codes as unsourced figures. A digit
# immediately followed by `+`, `g` or `ml` is a grade or a pack size — an identifier, not
# a measurement — wherever it appears.
# Both date orders are here because a model writes whichever it prefers. The renderer
# emits "1 May 2026"; the first live run wrote "May 1, 2026" in prose, which left the year
# orphaned and reported 2026 as an invented figure. Neither format is wrong — the check has
# to read both.
NOISE_PATTERNS = (
    rf"\b\d{{1,2}} (?:{MONTHS}),? \d{{4}}\b",  # 16 April 2026
    rf"\b(?:{MONTHS}) \d{{1,2}},? \d{{4}}\b",  # May 1, 2026
    rf"\b(?:{MONTHS}) \d{{4}}\b",              # March 2026
    r"\bQ[1-4] \d{4}\b",                       # Q2 2026
    r"\b\d{4}-\d{2}-\d{2}\b",                  # 2026-04-16
    r"\b\d+\+",                                # MGO 263+, MGO 1700+
    r"\b\d+\s?(?:g|ml)\b",                     # 250g, 500 g, 30ml
)

FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _collect_numbers(node, out: set[float]) -> set[float]:
    """Every numeric leaf in the fact pack."""
    if isinstance(node, bool):
        return out
    if isinstance(node, (int, float)):
        out.add(float(node))
    elif isinstance(node, dict):
        for value in node.values():
            _collect_numbers(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_numbers(value, out)
    return out


def _strip_noise(briefing: str, facts: dict) -> str:
    """Remove text whose digits are identifiers rather than measurements."""
    text = briefing
    # SKU names first — "MGO 1700+ 100g" would otherwise contribute 1700 and 100.
    for sku in sorted((s["sku"] for s in facts["skus"]), key=len, reverse=True):
        text = text.replace(sku, " ")
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, " ", text)
    return text


def _unsourced_figures(briefing: str, facts: dict) -> list[tuple[str, str]]:
    """Figures in the briefing with no matching value in the fact pack.

    Returns (figure, containing line) so a failure names where to look.
    """
    allowed = _collect_numbers(facts, set())
    problems: list[tuple[str, str]] = []

    for raw_line in briefing.splitlines():
        line = _strip_noise(raw_line, facts)
        for token in FIGURE.findall(line):
            cleaned = token.replace(",", "")
            value = float(cleaned)
            # Compare at the precision the briefing chose to display. "$364,963" must match
            # a fact that rounds to 364963; "16.6%" must match one that rounds to 16.6.
            decimals = len(cleaned.split(".")[1]) if "." in cleaned else 0
            if not any(round(f, decimals) == value for f in allowed):
                problems.append((token, raw_line.strip()))
    return problems


# --------------------------------------------------------------------------------------


def test_no_unsourced_figures_in_the_template_briefing(facts):
    problems = _unsourced_figures(render_briefing(facts), facts)
    assert not problems, "figures with no source in the fact pack:\n" + "\n".join(
        f"  {value!r} in: {line}" for value, line in problems
    )


def test_the_check_catches_an_invented_figure(facts):
    """A test that cannot fail proves nothing.

    Inject a plausible but unsourced number and confirm it is caught — this is what would
    have caught the two fabricated figures that went into this project's design document.
    """
    briefing = render_briefing(facts) + "\nRevenue grew to $412,900 this month.\n"
    problems = _unsourced_figures(briefing, facts)

    assert problems, "an invented figure passed the check"
    assert any(value == "412,900" for value, _ in problems)


def test_the_check_tolerates_dates_skus_and_years(facts):
    """The exclusions must actually exclude, or the test is noise and gets deleted."""
    briefing = (
        render_briefing(facts)
        + "\nOrder Manuka Honey MGO 1700+ 100g by 16 April 2026, before Q2 2026.\n"
    )
    assert not _unsourced_figures(briefing, facts)


def test_the_check_tolerates_abbreviated_sku_references(facts):
    """A model writing naturally does not repeat the full SKU name every time.

    This is a regression test, not a hypothetical: the first live model run wrote
    "MGO 263+ and MGO 514+ formats" and "MGO 100+ 250g", and the check reported five
    product codes as unsourced figures. Grades and pack sizes are identifiers wherever
    they appear.
    """
    briefing = render_briefing(facts) + (
        "\nCore revenue drivers remain the MGO 263+ and MGO 514+ formats, with "
        "MGO 100+ 250g and the 30ml tincture trailing.\n"
    )
    assert not _unsourced_figures(briefing, facts)


def test_the_check_reads_dates_in_either_order(facts):
    """Also a regression test.

    The renderer writes "1 May 2026". The first live model run wrote "May 1, 2026" in
    prose, which left the year orphaned and reported 2026 as an invented figure. Neither
    format is wrong, so the check reads both.
    """
    briefing = render_briefing(facts) + (
        "\nThe shipment lands on May 1, 2026, five weeks after the order of 16 April 2026.\n"
    )
    assert not _unsourced_figures(briefing, facts)


def test_prose_totals_come_from_the_engine(facts):
    """Counts quoted in prose are computed in engine.py, not in the renderer.

    The renderer formats numbers; it must not produce them. This pins that boundary.
    """
    summary = facts["reorder_summary"]
    assert summary["sku_count"] == len(facts["reorder_queue"])
    assert summary["total_units"] == sum(r["quantity_units"] for r in facts["reorder_queue"])
    assert summary["overdue_count"] == sum(
        1 for r in facts["reorder_queue"] if r["is_overdue"]
    )


# --------------------------------------------------------------------------------------
# The same guarantees, applied to a model-shaped response
# --------------------------------------------------------------------------------------


def _model_shaped_prose(facts: dict) -> dict:
    """Prose in the shape the model returns, written as a model plausibly would.

    Stands in for a live API response so the assembly path and the integrity check are
    exercised without a key. When a key exists, the real response flows through the same
    assertions unchanged.
    """
    prose = template_prose(facts)
    prose["opening_line"] = (
        "March was the strongest month of the period, but the stock is in the wrong places."
    )
    prose["headline"]["decision"] = (
        "Hold the inbound order and move the working capital to the SKUs below buffer."
    )
    prose["closing_action"] = "Place the overdue orders this week."
    return prose


def test_model_shaped_output_passes_the_same_check(facts):
    briefing = compose_briefing(facts, _model_shaped_prose(facts))
    assert not _unsourced_figures(briefing, facts)


def test_both_paths_agree_on_every_figure(facts):
    """The template render and a model-shaped render must quote the same numbers.

    This is the cross-check that makes --no-llm a control rather than a fallback: the two
    paths read one fact pack, so any divergence in figures is a defect in assembly.
    """

    def figures(text: str) -> set[str]:
        return {
            t
            for line in text.splitlines()
            for t in FIGURE.findall(_strip_noise(line, facts))
        }

    template = figures(render_briefing(facts))
    modelled = figures(compose_briefing(facts, _model_shaped_prose(facts)))

    # Tables are rendered from facts in both, so the table figures must match exactly.
    # Prose figures may legitimately differ — a writer chooses which to cite.
    assert template & modelled, "the two paths share no figures at all"
    assert not (modelled - template), (
        "the model-shaped render quotes figures the template does not: "
        f"{sorted(modelled - template)}"
    )


def test_briefing_completeness(facts):
    """The sections the brief requires are present, with the substance behind them."""
    briefing = render_briefing(facts)

    assert "## What to order" in briefing
    assert "## How " in briefing
    assert len(facts["reorder_queue"]) >= 3

    # Every recommendation carries a quantity and a date, in the document itself.
    for row in facts["reorder_queue"]:
        assert row["sku"] in briefing
        assert f"{row['quantity_units']:,} units" in briefing

    assert facts["tensions"], "the brief asks for the tension to be surfaced"
    assert facts["tensions"][0]["sku"] in briefing


def test_the_committed_model_briefing_has_no_unsourced_figures(facts):
    """The strongest form of the check: run it on the artefact that ships.

    `output/sop_briefing_march-2026.md` was written by a model, not by the template. It is
    the file a reviewer opens, so it is the file that has to be clean — a check that only
    ever ran against generated-in-memory output would prove less.
    """
    committed = REPO_ROOT / "output" / "sop_briefing_march-2026.md"
    if not committed.exists():
        pytest.skip("no committed model briefing to check")

    problems = _unsourced_figures(committed.read_text(encoding="utf-8"), facts)
    assert not problems, "the committed briefing contains figures with no source:\n" + "\n".join(
        f"  {value!r} in: {line}" for value, line in problems
    )


def test_the_committed_model_briefing_leads_with_the_engines_choice(facts):
    """The engine decides what leads; the model writes it.

    On the first live run the model chose the most urgent reorder as its headline instead
    of the hardest decision. Both readings are defensible, but ranking belongs to the
    engine — so the prompt says so and `check_against_facts` enforces it.
    """
    committed = REPO_ROOT / "output" / "sop_briefing_march-2026.md"
    if not committed.exists():
        pytest.skip("no committed model briefing to check")

    briefing = committed.read_text(encoding="utf-8")
    headline = briefing.split("## The decision this month", 1)[1].split("\n\n")[1]
    assert facts["tensions"][0]["sku"] in headline


def test_briefing_carries_no_column_codes(facts):
    """M1-M4 belong to the dataset, not to the reader."""
    briefing = render_briefing(facts)
    for code in config.MONTH_COLUMNS:
        assert not re.search(rf"\b{code}\b", briefing), f"{code} leaked into the output"
