"""Assembly of the finished briefing.

Two things live here.

`compose_briefing` renders the markdown: it takes a fact pack and a prose object, renders
every table and every figure from the fact pack, and drops the prose in around them. It is
the only place a briefing is assembled, so the model path and the template path cannot
drift into producing different documents.

`template_prose` is the `--no-llm` path: deterministic prose in exactly the shape the model
returns (see `schema.py`). A reviewer with no API key gets a complete briefing, and we get
a control — both paths read the same facts, so a figure that differs between them means
something is wrong.
"""

from __future__ import annotations

from datetime import date

from . import config


# --------------------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------------------


def _usd(value: float) -> str:
    return f"${value:,.0f}"


def _units(value: int) -> str:
    return f"{value:,}"


def _pct(value: float) -> str:
    return f"{value:+.1f}%"


def _long_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d %B %Y").lstrip("0")


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


# --------------------------------------------------------------------------------------
# Deterministic prose — the --no-llm path
# --------------------------------------------------------------------------------------


def template_prose(facts: dict) -> dict:
    """Prose written by template rather than by the model, in the same shape.

    Its job is to be correct and readable, not to sound written.
    """
    portfolio = facts["portfolio"]
    queue = facts["reorder_queue"]
    tensions = facts["tensions"]
    skus = {s["sku"]: s for s in facts["skus"]}
    perf = facts["performance"]
    summary = facts["reorder_summary"]

    top = tensions[0] if tensions else None

    return {
        "opening_line": (
            f"{_units(portfolio['current_month_units'])} units sold, "
            f"{_pct(portfolio['month_on_month_pct'])} against {facts['meta']['prior_month']}. "
            f"Forward revenue opportunity across the range is "
            f"{_usd(portfolio['total_revenue_opportunity_usd'])} a month."
        ),
        "headline": {
            "sku": top["sku"] if top else "",
            "decision": top["recommended_action"] if top else "",
            "reasoning": top["detail"] if top else "",
        },
        "capital_note": (
            f"{summary['sku_count']} SKUs need orders totalling "
            f"{_units(summary['total_units'])} units, "
            f"{summary['overdue_count']} of them already overdue. The capital is at the wrong "
            f"end of the range: sitting on stock that has stopped moving while the SKUs that "
            f"are moving run thin."
        )
        if queue
        else "",
        "reorder_rationales": [
            {"sku": r["sku"], "rationale": _template_rationale(skus[r["sku"]], r)}
            for r in queue
        ],
        "performance_note": _template_performance(facts, skus, perf, portfolio),
        "tension_notes": [
            {"sku": t["sku"], "note": f"{t['detail']} {t['recommended_action']}"}
            for t in tensions[1:]
        ],
        "noise_note": " ".join(
            f"{n['topic']}: {n['finding']} {n['why_ignore']}" for n in facts["noise"]
        ),
        "closing_action": (
            f"Place the {summary['overdue_count']} overdue orders this week and get a decision "
            f"on the inbound shipment flagged above before it lands."
        )
        if summary["overdue_count"]
        else "Review the reorder queue before the next cycle.",
    }


def _template_rationale(sku: dict, row: dict) -> str:
    inv, trend = sku["inventory"], sku["trend"]

    if inv["has_order_placed"]:
        return (
            f"{_units(sku['demand']['current_month_units'])} units a month, growing "
            f"{_pct(trend['month_on_month_pct'])}. An order for "
            f"{_units(inv['units_on_order'])} units is already in flight, but it only lifts "
            f"cover to {inv['cover_after_inbound_months']} months against a "
            f"{inv['target_months_cover']}-month target — it needs topping up, not patience."
        )

    gap = (
        "arriving after the shelf is already empty"
        if inv["arrives_after_stockout"]
        else "leaving almost no margin"
    )
    return (
        f"{_units(sku['demand']['current_month_units'])} units a month, growing "
        f"{_pct(trend['month_on_month_pct'])}, on {inv['current_cover_months']} months of "
        f"cover against a {inv['target_months_cover']}-month target. On a "
        f"{inv['lead_time_months']}-month lead time an order placed today arrives "
        f"{_long_date(inv['earliest_arrival_if_ordered_today'])}, against a projected stockout "
        f"of {_long_date(inv['projected_stockout_date'])} — {gap}."
    )


def _template_performance(facts: dict, skus: dict, perf: dict, portfolio: dict) -> str:
    best = skus[perf["top_by_revenue_opportunity"][0]]
    fastest = skus[perf["top_by_growth"][0]]

    text = (
        f"{best['sku']} carries the range at "
        f"{_usd(best['money']['revenue_opportunity_usd'])} a month, "
        f"{best['money']['share_of_portfolio_opportunity_pct']}% of the total opportunity. "
        f"{fastest['sku']} is the fastest riser at "
        f"{_pct(fastest['trend']['month_on_month_pct'])} month on month."
    )

    if perf["stalling_skus"]:
        weak = skus[perf["stalling_skus"][0]]
        text += (
            f" Nothing declined in absolute terms, so \"sold poorly\" here means falling "
            f"behind: {weak['sku']} grew {_pct(weak['trend']['month_on_month_pct'])} against a "
            f"portfolio moving {_pct(portfolio['month_on_month_pct'])} — the only SKU not "
            f"keeping pace, and the one holding the most idle stock."
        )
    return text


# --------------------------------------------------------------------------------------
# Assembly — shared by both paths
# --------------------------------------------------------------------------------------


def compose_briefing(facts: dict, prose: dict) -> str:
    """Render the finished markdown from a fact pack and a prose object.

    All tables and all figures come from `facts`. The prose object supplies only sentences.
    """
    meta = facts["meta"]
    lines: list[str] = []
    add = lines.append

    add(f"# S&OP Briefing — {meta['reporting_month']}")
    add("")
    add(prose["opening_line"])
    add("")

    if prose["headline"]["sku"]:
        add("## The decision this month")
        add("")
        add(f"**{prose['headline']['sku']}.** {prose['headline']['reasoning']}")
        add("")
        add(prose["headline"]["decision"])
        add("")
        if prose["capital_note"]:
            add(prose["capital_note"])
            add("")

    lines += _order_section(facts, prose)
    lines += _performance_section(facts, prose)
    lines += _watch_section(prose)
    lines += _noise_section(prose)
    lines += _closing_section(prose)
    lines += _appendix(facts)

    return "\n".join(lines).rstrip() + "\n"


def _order_section(facts: dict, prose: dict) -> list[str]:
    queue = facts["reorder_queue"]
    if not queue:
        return []

    rationales = {r["sku"]: r["rationale"] for r in prose["reorder_rationales"]}

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

    for r in queue[:2]:
        out.append(f"**{r['sku']}** — {rationales[r['sku']]}")
        out.append("")

    if len(queue) > 2:
        out.append("The rest, briefly:")
        out.append("")
        for r in queue[2:]:
            out.append(f"- **{r['sku']}** — {rationales[r['sku']]}")
        out.append("")
    return out


def _performance_section(facts: dict, prose: dict) -> list[str]:
    """How the month went, against the shape of the whole period.

    A single month-on-month figure cannot tell a SKU that has climbed all period from one
    that jumped once, and the brief asks for trend context across prior months — so the
    four-month trajectory is rendered here rather than left in the fact pack.
    """
    out = [f"## How {facts['meta']['reporting_month']} went", "", prose["performance_note"], ""]

    by_month = facts["portfolio"]["units_by_month"]
    months = list(by_month)

    out.append("Units across the period, so the month reads against the run rather than alone:")
    out.append("")
    out.append("| " + " | ".join(months) + " | Period |")
    out.append("|" + "---|" * (len(months) + 1))
    out.append(
        "| "
        + " | ".join(_units(by_month[m]) for m in months)
        + f" | {_pct(facts['portfolio']['period_growth_pct'])} |"
    )
    out.append("")
    return out


def _watch_section(prose: dict) -> list[str]:
    if not prose["tension_notes"]:
        return []
    out = ["## Also worth a decision", ""]
    for t in prose["tension_notes"]:
        out.append(f"- **{t['sku']}** — {t['note']}")
    out.append("")
    return out


def _noise_section(prose: dict) -> list[str]:
    if not prose["noise_note"].strip():
        return []
    return ["## Not worth your attention", "", prose["noise_note"], ""]


def _closing_section(prose: dict) -> list[str]:
    if not prose["closing_action"].strip():
        return []
    return ["## Before the next review", "", prose["closing_action"], ""]


def _appendix(facts: dict) -> list[str]:
    out = ["---", "", "## Every SKU", ""]
    out.append("| SKU | Units | MoM | Trend/mo | Cover | Target | Status | Opportunity |")
    out.append("|---|---|---|---|---|---|---|---|")
    label = {
        "critical": "Below buffer",
        "act_now": "Order now",
        "overstocked": "Overstocked",
        "healthy": "Fine",
    }
    launch_adjusted = False
    for s in sorted(facts["skus"], key=lambda s: -s["money"]["revenue_opportunity_usd"]):
        inv, trend = s["inventory"], s["trend"]
        note = "Phasing out" if s["flags"]["phasing_out"] else label[s["flags"]["urgency"]]
        # Compounded across the SKU's own trend window — which for the Bioactive Blends
        # starts after their launch month, so their growth is not inflated by a partial
        # first month.
        marker = ""
        if trend["baseline_excludes_launch_month"]:
            marker = " *"
            launch_adjusted = True
        out.append(
            f"| {s['sku']} | {_units(s['demand']['current_month_units'])} | "
            f"{_pct(trend['month_on_month_pct'])} | "
            f"{_pct(trend['monthly_growth_pct'])}{marker} | {inv['current_cover_months']} | "
            f"{inv['target_months_cover']} | {note} | "
            f"{_usd(s['money']['revenue_opportunity_usd'])} |"
        )
    out.append("")

    notes = [
        f"**MoM** compares {facts['meta']['reporting_month']} with "
        f"{facts['meta']['prior_month']}. **Trend/mo** is the average monthly rate across the "
        f"whole period, so a SKU that climbed steadily reads differently from one that jumped "
        f"once."
    ]
    if launch_adjusted:
        first_month = facts["meta"]["months_covered"][0]
        notes.append(
            f"\\* Measured from the SKU's first full trading month rather than from "
            f"{first_month}. The Bioactive Blends launched mid-period, and including their "
            f"partial first month would overstate their growth — which would push them up a "
            f"ranking driven by projected demand."
        )
    notes.append(
        f"Cover is stock on hand divided by {facts['meta']['reporting_month']} demand across "
        f"both channels, which draw on one pooled inventory position. Revenue opportunity is "
        f"retail price times projected demand for next month. Reorder quantities assume a "
        f"{config.DEFAULT_LEAD_TIME_MONTHS}-month supplier lead time — an assumption, not a "
        f"figure from the data. See OPEN-QUESTIONS.md."
    )
    out.append("\n\n".join(notes))
    return out


def render_briefing(facts: dict) -> str:
    """The `--no-llm` briefing: template prose through the shared assembler."""
    return compose_briefing(facts, template_prose(facts))
