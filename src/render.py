"""Deterministic briefing renderer.

Two jobs. It is the `--no-llm` path, so a reviewer with no API key still gets a complete
briefing rather than a JSON dump. And it is a control on the narrative layer: both paths
read the same fact pack, so if a figure differs between them, something is wrong.

The prose here is fixed. Its job is to be correct and readable, not to sound written.
"""

from __future__ import annotations

from datetime import date

from . import config


def _usd(value: float) -> str:
    return f"${value:,.0f}"


def _units(value: int) -> str:
    return f"{value:,}"


def _pct(value: float) -> str:
    return f"{value:+.1f}%"


def _long_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d %B %Y").lstrip("0")


def render_briefing(facts: dict) -> str:
    meta = facts["meta"]
    portfolio = facts["portfolio"]
    lines: list[str] = []
    add = lines.append

    add(f"# S&OP Briefing — {meta['reporting_month']}")
    add("")
    add(
        f"{_units(portfolio['current_month_units'])} units sold, "
        f"{_pct(portfolio['month_on_month_pct'])} against {meta['prior_month']}. "
        f"Forward revenue opportunity across the range is "
        f"{_usd(portfolio['total_revenue_opportunity_usd'])} a month."
    )
    add("")

    lines += _headline(facts)
    lines += _actions(facts)
    lines += _performance(facts)
    lines += _watch(facts)
    lines += _noise(facts)
    lines += _appendix(facts)

    return "\n".join(lines).rstrip() + "\n"


def prose_word_count(briefing: str) -> int:
    """Words a reader actually reads.

    Table rows are excluded. They are scanned column by column, not read as sentences, so
    counting them against a reading-time budget would penalise exactly the format that
    makes a briefing quick to get through. Headings and prose count; pipes do not.
    """
    return sum(
        len(line.split())
        for line in briefing.splitlines()
        if not line.lstrip().startswith("|")
    )


def _headline(facts: dict) -> list[str]:
    """Lead with the decision, not the data."""
    tensions = facts["tensions"]
    if not tensions:
        return []

    # Already ordered by how hard the call is, not by the size of the number. Taking the
    # largest capital figure instead would lead with the easiest problem in the set.
    top = tensions[0]
    queue = facts["reorder_queue"]

    out = ["## The decision this month", ""]
    out.append(f"**{top['sku']}** is the clearest call. {top['detail']} {top['recommended_action']}")
    out.append("")
    if queue:
        overdue = [r for r in queue if r["is_overdue"]]
        total_qty = sum(r["quantity_units"] for r in queue)
        out.append(
            f"Meanwhile {len(queue)} SKUs need orders totalling {_units(total_qty)} units, "
            f"{len(overdue)} of them already overdue. The capital is at the wrong end of the "
            f"range: sitting on stock that has stopped moving while the SKUs that are moving "
            f"run thin."
        )
        out.append("")
    return out


def _actions(facts: dict) -> list[str]:
    queue = facts["reorder_queue"]
    if not queue:
        return []

    out = ["## What to order, in priority order", ""]
    out.append(
        "Ranked by revenue at stake rather than by who runs out first, so the largest "
        "commercial exposure is covered before the smallest."
    )
    out.append("")
    out.append("| # | SKU | Order | By | Cover now | Revenue at stake |")
    out.append("|---|---|---|---|---|---|")
    for r in queue:
        by = "**Overdue**" if r["is_overdue"] else _long_date(r["order_by_date"])
        out.append(
            f"| {r['rank']} | {r['sku']} | {_units(r['quantity_units'])} units | {by} | "
            f"{r['current_cover_months']} of {r['target_months_cover']} months | "
            f"{_usd(r['revenue_opportunity_usd'])} |"
        )
    out.append("")

    # Depth where the money is, coverage everywhere. The brief asks for reasoning behind
    # each recommendation; six full paragraphs would bury the two that matter, so the top
    # two get the argument and the rest get the one clause that justifies their position.
    for r in queue[:2]:
        out.append(f"**{r['sku']}** — {_reasoning(facts, r)}")
        out.append("")

    if len(queue) > 2:
        out.append("The rest, briefly:")
        out.append("")
        for r in queue[2:]:
            out.append(f"- **{r['sku']}** — {_short_reasoning(facts, r)}")
        out.append("")
    return out


def _short_reasoning(facts: dict, row: dict) -> str:
    """One clause explaining why this SKU sits where it does in the ranking."""
    sku = next(s for s in facts["skus"] if s["sku"] == row["sku"])
    inv = sku["inventory"]

    if inv["has_order_placed"]:
        return (
            f"the {_units(inv['units_on_order'])} units already inbound only reach "
            f"{inv['cover_after_inbound_months']} months of cover against a "
            f"{inv['target_months_cover']}-month target, so it needs a top-up, not patience."
        )
    return (
        f"{inv['current_cover_months']} months of cover and growing "
        f"{_pct(sku['trend']['month_on_month_pct'])} a month; "
        f"{_usd(sku['money']['revenue_opportunity_usd'])} of monthly revenue is riding on it."
    )


def _reasoning(facts: dict, row: dict) -> str:
    """The business case for one reorder, in one paragraph."""
    sku = next(s for s in facts["skus"] if s["sku"] == row["sku"])
    inv, trend = sku["inventory"], sku["trend"]

    parts = [
        f"{_units(sku['demand']['current_month_units'])} units a month, growing "
        f"{_pct(trend['month_on_month_pct'])}, on {inv['current_cover_months']} months of cover "
        f"against a {inv['target_months_cover']}-month target."
    ]

    if inv["has_order_placed"]:
        parts.append(
            f"An order for {_units(inv['units_on_order'])} units is already in flight, but it "
            f"only lifts cover to {inv['cover_after_inbound_months']} months — still short of "
            f"target, so it needs topping up rather than waiting on."
        )
    else:
        # Two distinct dates: when a new order could arrive, and when the shelf empties.
        # Whether the first falls after the second is the whole question.
        gap = (
            "arriving after the shelf is already empty"
            if inv["arrives_after_stockout"]
            else "leaving almost no margin"
        )
        parts.append(
            f"On a {inv['lead_time_months']}-month lead time an order placed today arrives "
            f"{_long_date(inv['earliest_arrival_if_ordered_today'])}, against a projected "
            f"stockout of {_long_date(inv['projected_stockout_date'])} — {gap}."
        )

    parts.append(
        f"At {_usd(sku['money']['revenue_opportunity_usd'])} a month it is the largest "
        f"exposure on this list."
        if row["rank"] == 1
        else f"At {_usd(sku['money']['revenue_opportunity_usd'])} a month the cost of getting "
        f"this wrong outweighs everything below it."
    )
    return " ".join(parts)


def _performance(facts: dict) -> list[str]:
    perf, portfolio = facts["performance"], facts["portfolio"]
    skus = {s["sku"]: s for s in facts["skus"]}

    best = skus[perf["top_by_revenue_opportunity"][0]]
    fastest = skus[perf["top_by_growth"][0]]

    out = [f"## How {facts['meta']['reporting_month']} went", ""]
    out.append(
        f"**{best['sku']}** carries the range: "
        f"{_usd(best['money']['revenue_opportunity_usd'])} a month, "
        f"{best['money']['share_of_portfolio_opportunity_pct']}% of the total opportunity. "
        f"**{fastest['sku']}** is the fastest riser at "
        f"{_pct(fastest['trend']['month_on_month_pct'])} month on month."
    )
    out.append("")

    if perf["stalling_skus"]:
        weak = skus[perf["stalling_skus"][0]]
        out.append(
            f"Nothing declined in absolute terms, so \"sold poorly\" here means falling behind. "
            f"**{weak['sku']}** grew {_pct(weak['trend']['month_on_month_pct'])} against a "
            f"portfolio moving {_pct(portfolio['month_on_month_pct'])} — the only SKU not "
            f"keeping pace, and the one holding the most idle stock."
        )
        out.append("")
    return out


def _watch(facts: dict) -> list[str]:
    others = facts["tensions"][1:]
    if not others:
        return []
    out = ["## Also worth a decision", ""]
    for t in others:
        out.append(f"- **{t['sku']}** — {t['detail']} {t['recommended_action']}")
    out.append("")
    return out


def _noise(facts: dict) -> list[str]:
    if not facts["noise"]:
        return []
    out = ["## Not worth your attention", ""]
    for n in facts["noise"]:
        out.append(f"- **{n['topic']}** — {n['finding']} {n['why_ignore']}")
    out.append("")
    return out


def _appendix(facts: dict) -> list[str]:
    out = ["---", "", "## Every SKU", ""]
    out.append("| SKU | Units | MoM | Cover | Target | Status | Opportunity |")
    out.append("|---|---|---|---|---|---|---|")
    label = {
        "critical": "Below buffer",
        "act_now": "Order now",
        "overstocked": "Overstocked",
        "healthy": "Fine",
    }
    for s in sorted(facts["skus"], key=lambda s: -s["money"]["revenue_opportunity_usd"]):
        inv = s["inventory"]
        note = label[s["flags"]["urgency"]]
        if s["flags"]["phasing_out"]:
            note = "Phasing out"
        out.append(
            f"| {s['sku']} | {_units(s['demand']['current_month_units'])} | "
            f"{_pct(s['trend']['month_on_month_pct'])} | {inv['current_cover_months']} | "
            f"{inv['target_months_cover']} | {note} | "
            f"{_usd(s['money']['revenue_opportunity_usd'])} |"
        )
    out.append("")
    out.append(
        f"Cover is stock on hand divided by {facts['meta']['reporting_month']} demand across "
        f"both channels, which draw on one pooled inventory position. Revenue opportunity is "
        f"retail price times projected demand for next month. Reorder quantities assume a "
        f"{config.DEFAULT_LEAD_TIME_MONTHS}-month supplier lead time — an assumption, not a "
        f"figure from the data. See OPEN-QUESTIONS.md."
    )
    return out
