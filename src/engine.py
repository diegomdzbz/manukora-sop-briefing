"""All arithmetic for the S&OP briefing.

This module is the only place numbers are produced. The narrative layer receives its output
and writes prose around it; it never calculates. See CLAUDE.md for why that split exists.

Everything here is deterministic: same input, same output, no clock, no randomness. That is
what makes `tests/` able to assert on exact figures.
"""

from __future__ import annotations

from datetime import date, timedelta

from . import config
from .loader import SkuRecord


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------


def _human_date(value: date | str) -> str:
    """Dates in prose read as `13 May 2026`, never as an ISO string.

    The machine-readable form stays in the fact pack alongside it; this is only for the
    sentences a person reads.
    """
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime("%d %B %Y").lstrip("0")


def _units(value: int) -> str:
    return f"{value:,}"


def _months_to_days(months: float) -> int:
    return int(round(months * config.DAYS_PER_MONTH))


def _add_months(start: date, months: float) -> date:
    return start + timedelta(days=_months_to_days(months))


def _compound_monthly_growth(start_units: int, end_units: int, months_apart: int) -> float:
    """Average month-on-month growth rate between two points.

    Compounded rather than averaged: a SKU that goes 100 -> 200 over three months grew
    ~26% a month, not 33%. Using the arithmetic mean would overstate every trend and push
    fast-looking SKUs up the reorder ranking on a maths artefact.
    """
    if start_units <= 0 or months_apart <= 0:
        return 0.0
    return (end_units / start_units) ** (1 / months_apart) - 1


# --------------------------------------------------------------------------------------
# Per-SKU analysis
# --------------------------------------------------------------------------------------


def analyse_sku(record: SkuRecord, portfolio_mom_growth: float) -> dict:
    """Everything the briefing can say about one SKU, as plain data."""
    units = record.units
    current_demand = units[config.CURRENT_MONTH]
    prior_demand = units[config.PRIOR_MONTH]
    price = record.retail_price_usd

    # --- trend ---------------------------------------------------------------------
    baseline_month = config.trend_baseline_month(record.sku)
    months_apart = config.MONTH_COLUMNS.index(config.CURRENT_MONTH) - config.MONTH_COLUMNS.index(
        baseline_month
    )
    monthly_growth = _compound_monthly_growth(units[baseline_month], current_demand, months_apart)
    mom_growth = (current_demand / prior_demand - 1) if prior_demand else 0.0

    # A SKU can be growing and still be losing ground. With every SKU in this dataset up
    # month on month, "sold poorly" has to mean falling behind the portfolio, not shrinking.
    is_stalling = mom_growth < portfolio_mom_growth * config.STALLING_VS_PORTFOLIO_RATIO

    # --- demand and money ----------------------------------------------------------
    # Cover uses the current month as the sell-through baseline, exactly as the brief
    # specifies. Revenue opportunity uses *projected* demand, which the brief words
    # differently and on purpose: "retail price x projected monthly demand".
    projected_demand = int(round(current_demand * (1 + monthly_growth)))
    revenue_opportunity = round(projected_demand * price, 2)
    current_run_rate = round(current_demand * price, 2)

    # --- inventory position --------------------------------------------------------
    current_cover_months = current_demand and record.stock_on_hand / current_demand
    current_cover_days = _months_to_days(current_cover_months)
    target = record.target_months_cover
    lead_time = config.lead_time_months(record.sku)

    stockout_date = _add_months(config.PLANNING_DATE, current_cover_months)
    # Where a purchase order placed today would actually land. Held separately from the
    # stockout date because conflating the two is an easy way to write a confident sentence
    # that is wrong.
    earliest_arrival = _add_months(config.PLANNING_DATE, lead_time)
    arrives_after_stockout = earliest_arrival > stockout_date

    if record.has_order_placed:
        arrival = record.order_arrival_months
        stock_at_arrival = record.stock_on_hand - current_demand * arrival + record.units_on_order
        cover_after_inbound = round(stock_at_arrival / current_demand, 2)
        arrival_date = _add_months(config.PLANNING_DATE, arrival)
        stocks_out_before_arrival = current_cover_months < arrival
    else:
        cover_after_inbound = None
        arrival_date = None
        stocks_out_before_arrival = False

    # --- classification ------------------------------------------------------------
    below_target = current_cover_months < target
    overstocked = current_cover_months > target * config.OVERSTOCK_MULTIPLE
    phasing_out = config.is_phasing_out(record.sku)

    # The reorder point is target *plus* lead time, not target alone. Waiting until cover
    # dips below the buffer means the replenishment lands two months after the buffer was
    # already breached — by then the SKU has been under-covered for the whole lead time.
    # Ordering when cover reaches target + lead time is what makes the stock arrive as the
    # buffer is reached rather than long after.
    reorder_point_months = target + lead_time
    reorder_point_breached = current_cover_months < reorder_point_months

    phase_out_floor_days = None
    if phasing_out:
        # The brief deprioritises this SKU unless cover drops below its floor. Being under
        # target is not enough; a product being retired does not need a full buffer.
        rule = config.phase_out_rule(record.sku)
        # Exposed as a number, not only inside the sentence below. The briefing cites this
        # threshold to justify not reordering, and a figure that exists only inside a
        # prose string cannot be traced — which tests/test_output_integrity.py caught.
        phase_out_floor_days = rule["reorder_floor_days"]
        needs_reorder = current_cover_days < phase_out_floor_days
        deprioritised_reason = (
            f"Phasing out in {rule['phase_out_period']}; reorder only below "
            f"{phase_out_floor_days} days of cover"
        )
    elif record.has_order_placed:
        # An inbound order does not automatically settle the question. What matters is
        # where cover lands once it arrives: if the shipment still leaves the SKU under
        # its target, a top-up is needed regardless of the order already in flight.
        needs_reorder = cover_after_inbound is not None and cover_after_inbound < target
        deprioritised_reason = None
    else:
        needs_reorder = reorder_point_breached
        deprioritised_reason = None

    if needs_reorder:
        # Order enough to cover the lead time *and* land on the target buffer. Ordering
        # only `target x demand` would arrive at zero cover on the day it lands, which is
        # not what a buffer means.
        wanted_units = reorder_point_months * projected_demand
        reorder_qty = max(0, int(round(wanted_units - (record.stock_on_hand + record.units_on_order))))
        order_by = _add_months(config.PLANNING_DATE, max(0.0, current_cover_months - lead_time))
        is_overdue = order_by <= config.PLANNING_DATE
    else:
        reorder_qty = 0
        order_by = None
        is_overdue = False

    if below_target:
        urgency = "critical"       # already under the buffer
    elif needs_reorder:
        urgency = "act_now"        # will breach the buffer before a new order could land
    elif overstocked:
        urgency = "overstocked"    # the opposite problem: capital sitting still
    else:
        urgency = "healthy"

    # Capital sitting above the target buffer, valued at retail. Only meaningful for the
    # overstocked SKUs, where it is the whole point.
    excess_units = max(0, record.stock_on_hand + record.units_on_order - int(target * current_demand))
    excess_value = round(excess_units * price, 2)

    return {
        "sku": record.sku,
        "retail_price_usd": price,
        "units_by_month": {config.MONTH_LABELS[m]: units[m] for m in config.MONTH_COLUMNS},
        "channel_split_current_month": {
            "shopify": record.shopify[config.CURRENT_MONTH],
            "amazon": record.amazon[config.CURRENT_MONTH],
        },
        "trend": {
            "baseline_month": config.MONTH_LABELS[baseline_month],
            "baseline_excludes_launch_month": baseline_month != config.DEFAULT_TREND_BASELINE,
            "monthly_growth_pct": round(monthly_growth * 100, 1),
            "month_on_month_pct": round(mom_growth * 100, 1),
            "is_stalling_vs_portfolio": is_stalling,
        },
        "demand": {
            "current_month_units": current_demand,
            "projected_next_month_units": projected_demand,
        },
        "money": {
            "current_run_rate_usd": current_run_rate,
            "revenue_opportunity_usd": revenue_opportunity,
        },
        "inventory": {
            "stock_on_hand": record.stock_on_hand,
            "units_on_order": record.units_on_order,
            "order_arrival_months": record.order_arrival_months,
            "has_order_placed": record.has_order_placed,
            "target_months_cover": target,
            "lead_time_months": lead_time,
            "reorder_point_months": reorder_point_months,
            "current_cover_months": round(current_cover_months, 2),
            "current_cover_days": current_cover_days,
            "cover_after_inbound_months": cover_after_inbound,
            "projected_stockout_date": stockout_date.isoformat(),
            "earliest_arrival_if_ordered_today": earliest_arrival.isoformat(),
            "arrives_after_stockout": arrives_after_stockout,
            "inbound_arrival_date": arrival_date.isoformat() if arrival_date else None,
            "stocks_out_before_inbound_arrives": stocks_out_before_arrival,
            "excess_units_above_target": excess_units,
            "excess_value_usd": excess_value,
        },
        "flags": {
            "below_target_cover": below_target,
            "reorder_point_breached": reorder_point_breached,
            "overstocked": overstocked,
            "phasing_out": phasing_out,
            "phase_out_floor_days": phase_out_floor_days,
            "needs_reorder": needs_reorder,
            "deprioritised_reason": deprioritised_reason,
            "urgency": urgency,
        },
        "reorder": {
            "quantity_units": reorder_qty,
            "order_by_date": order_by.isoformat() if order_by else None,
            "is_overdue": is_overdue,
        },
    }


# --------------------------------------------------------------------------------------
# Portfolio analysis
# --------------------------------------------------------------------------------------


def analyse_portfolio(records: list[SkuRecord]) -> dict:
    """Totals and channel mix, used to judge individual SKUs against the whole."""
    units_by_month = {
        m: sum(r.units[m] for r in records) for m in config.MONTH_COLUMNS
    }
    shopify_by_month = {m: sum(r.shopify[m] for r in records) for m in config.MONTH_COLUMNS}
    amazon_by_month = {m: sum(r.amazon[m] for r in records) for m in config.MONTH_COLUMNS}

    current = units_by_month[config.CURRENT_MONTH]
    prior = units_by_month[config.PRIOR_MONTH]
    mom_growth = (current / prior - 1) if prior else 0.0

    first, last = config.MONTH_COLUMNS[0], config.CURRENT_MONTH
    # Growth across the whole period, so the briefing can show the run and not just the
    # last step. Computed here rather than in the renderer: the renderer formats numbers,
    # it does not produce them — a boundary tests/test_output_integrity.py enforces, and
    # caught being crossed when this figure was first added to the template by mistake.
    period_growth = (units_by_month[last] / units_by_month[first] - 1) if units_by_month[first] else 0.0
    amazon_share = {
        config.MONTH_LABELS[m]: round(amazon_by_month[m] / units_by_month[m] * 100, 1)
        for m in config.MONTH_COLUMNS
    }
    shares = list(amazon_share.values())

    return {
        "units_by_month": {config.MONTH_LABELS[m]: units_by_month[m] for m in config.MONTH_COLUMNS},
        "current_month_units": current,
        "month_on_month_pct": round(mom_growth * 100, 1),
        "period_growth_pct": round(period_growth * 100, 1),
        "channel": {
            "shopify_units_by_month": {
                config.MONTH_LABELS[m]: shopify_by_month[m] for m in config.MONTH_COLUMNS
            },
            "amazon_units_by_month": {
                config.MONTH_LABELS[m]: amazon_by_month[m] for m in config.MONTH_COLUMNS
            },
            "amazon_share_pct_by_month": amazon_share,
            "amazon_share_swing_pct_points": round(max(shares) - min(shares), 1),
            "shopify_growth_full_period_pct": round(
                (shopify_by_month[last] / shopify_by_month[first] - 1) * 100, 1
            ),
            "amazon_growth_full_period_pct": round(
                (amazon_by_month[last] / amazon_by_month[first] - 1) * 100, 1
            ),
        },
    }


# --------------------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------------------


def build_facts(records: list[SkuRecord]) -> dict:
    """The complete fact pack. This is the only input the narrative layer ever sees."""
    portfolio = analyse_portfolio(records)
    mom = portfolio["month_on_month_pct"] / 100

    skus = [analyse_sku(r, portfolio_mom_growth=mom) for r in records]

    total_revenue_opportunity = round(sum(s["money"]["revenue_opportunity_usd"] for s in skus), 2)
    for sku in skus:
        sku["money"]["share_of_portfolio_opportunity_pct"] = round(
            sku["money"]["revenue_opportunity_usd"] / total_revenue_opportunity * 100, 1
        )

    by_opportunity = sorted(skus, key=lambda s: -s["money"]["revenue_opportunity_usd"])
    by_growth = sorted(skus, key=lambda s: -s["trend"]["month_on_month_pct"])

    # The reorder queue is ranked by money at stake, not by who is closest to running out.
    # The brief is explicit about this, and it is the difference between a briefing that
    # reports risk and one that allocates capital.
    reorder_queue = [
        {
            "rank": i + 1,
            "sku": s["sku"],
            "quantity_units": s["reorder"]["quantity_units"],
            "order_by_date": s["reorder"]["order_by_date"],
            "is_overdue": s["reorder"]["is_overdue"],
            "urgency": s["flags"]["urgency"],
            "revenue_opportunity_usd": s["money"]["revenue_opportunity_usd"],
            "current_cover_months": s["inventory"]["current_cover_months"],
            "target_months_cover": s["inventory"]["target_months_cover"],
            "reorder_point_months": s["inventory"]["reorder_point_months"],
            "month_on_month_pct": s["trend"]["month_on_month_pct"],
            "has_order_placed": s["inventory"]["has_order_placed"],
        }
        for i, s in enumerate(
            sorted(
                (s for s in skus if s["flags"]["needs_reorder"]),
                key=lambda s: -s["money"]["revenue_opportunity_usd"],
            )
        )
    ]

    # Totals the briefing quotes in prose. Computed here rather than in the renderer so
    # that every figure in the finished document traces back to this file — the renderer
    # formats numbers, it does not produce them.
    reorder_summary = {
        "sku_count": len(reorder_queue),
        "overdue_count": sum(1 for r in reorder_queue if r["is_overdue"]),
        "total_units": sum(r["quantity_units"] for r in reorder_queue),
        "revenue_at_stake_usd": round(
            sum(r["revenue_opportunity_usd"] for r in reorder_queue), 2
        ),
    }

    # Capital sitting above target across the whole range. A natural figure to want in the
    # narrative, and one the model reached for by adding two numbers together on a live run
    # — which the integrity check rejected, correctly. Computing it here makes it citable.
    overstock_summary = {
        "sku_count": sum(1 for s in skus if s["flags"]["overstocked"]),
        "total_excess_units": sum(
            s["inventory"]["excess_units_above_target"] for s in skus if s["flags"]["overstocked"]
        ),
        "total_excess_value_usd": round(
            sum(s["inventory"]["excess_value_usd"] for s in skus if s["flags"]["overstocked"]), 2
        ),
    }

    return {
        "meta": {
            "reporting_month": config.MONTH_LABELS[config.CURRENT_MONTH],
            "prior_month": config.MONTH_LABELS[config.PRIOR_MONTH],
            "months_covered": [config.MONTH_LABELS[m] for m in config.MONTH_COLUMNS],
            "planning_date": config.PLANNING_DATE.isoformat(),
            "sku_count": len(skus),
        },
        "reorder_summary": reorder_summary,
        "overstock_summary": overstock_summary,
        "portfolio": {
            **portfolio,
            "total_revenue_opportunity_usd": total_revenue_opportunity,
        },
        "performance": {
            "top_by_revenue_opportunity": [s["sku"] for s in by_opportunity[:3]],
            "top_by_growth": [s["sku"] for s in by_growth[:3]],
            "weakest_by_growth": [s["sku"] for s in by_growth[-3:]][::-1],
            "stalling_skus": [s["sku"] for s in skus if s["trend"]["is_stalling_vs_portfolio"]],
        },
        "reorder_queue": reorder_queue,
        "tensions": _find_tensions(skus),
        "noise": _find_noise(portfolio),
        "skus": skus,
    }


def _find_tensions(skus: list[dict]) -> list[dict]:
    """Where the obvious reading of the data and the right decision disagree.

    The brief asks for the case of high revenue opportunity against declining demand. In
    this dataset nothing declines, so the same tension shows up inverted: the SKUs with the
    most capital committed are not the ones with the most momentum. Reporting only the
    literal case asked for would have missed it.
    """
    # Ordered by how hard the decision is, not by how big the number is. A SKU that has
    # stopped growing while holding stock is a genuine call about where capital should sit;
    # a fast-selling SKU that happens to be well covered is only a scheduling question.
    # Ranking on raw capital alone would lead the briefing with the easier problem.
    priority = {
        "capital_committed_to_a_stalling_sku": 1,
        "phase_out_stockout_before_end_of_life": 2,
        "inbound_order_on_an_already_covered_sku": 3,
    }

    tensions = []

    for s in skus:
        inv, trend, money = s["inventory"], s["trend"], s["money"]

        if s["flags"]["overstocked"] and trend["is_stalling_vs_portfolio"]:
            detail = (
                f"Weakest growth in the portfolio at {trend['month_on_month_pct']}% month on "
                f"month, while holding {inv['current_cover_months']} months of cover against a "
                f"{inv['target_months_cover']}-month target."
            )
            if inv["has_order_placed"]:
                detail += (
                    f" A further {_units(inv['units_on_order'])} units land on "
                    f"{_human_date(inv['inbound_arrival_date'])}, taking cover to "
                    f"{inv['cover_after_inbound_months']} months."
                )
            tensions.append(
                {
                    "sku": s["sku"],
                    "type": "capital_committed_to_a_stalling_sku",
                    "detail": detail,
                    "capital_at_stake_usd": inv["excess_value_usd"],
                    "recommended_action": (
                        "Do not reorder. Review whether the inbound order can be deferred or "
                        "reduced, and redirect that working capital to the SKUs below target."
                    ),
                }
            )

        elif s["flags"]["overstocked"] and inv["has_order_placed"]:
            tensions.append(
                {
                    "sku": s["sku"],
                    "type": "inbound_order_on_an_already_covered_sku",
                    "detail": (
                        f"Already at {inv['current_cover_months']} months of cover against a "
                        f"{inv['target_months_cover']}-month target, with "
                        f"{_units(inv['units_on_order'])} units inbound taking it to "
                        f"{inv['cover_after_inbound_months']} months."
                    ),
                    "capital_at_stake_usd": inv["excess_value_usd"],
                    "recommended_action": (
                        "Demand is healthy, so this is a timing question rather than a demand "
                        "question. Check whether the shipment can be staged later."
                    ),
                }
            )

        if s["flags"]["phasing_out"] and inv["current_cover_months"] < inv["target_months_cover"]:
            tensions.append(
                {
                    "sku": s["sku"],
                    "type": "phase_out_stockout_before_end_of_life",
                    "detail": (
                        f"{inv['current_cover_days']} days of cover, running out around "
                        f"{_human_date(inv['projected_stockout_date'])}, which falls inside the "
                        f"phase-out window rather than after it."
                    ),
                    "capital_at_stake_usd": money["revenue_opportunity_usd"],
                    "recommended_action": (
                        "Cover sits above the reorder floor, so the rule says do not reorder. "
                        "The decision is to confirm the end-of-life date and tell customers, "
                        "not to buy more stock."
                    ),
                }
            )

    return sorted(tensions, key=lambda t: (priority[t["type"]], -t["capital_at_stake_usd"]))


def _find_noise(portfolio: dict) -> list[dict]:
    """Things that look like a story and are not.

    Knowing what not to raise is part of a briefing an executive can read in five minutes.
    """
    channel = portfolio["channel"]
    noise = []

    if channel["amazon_share_swing_pct_points"] <= 2.0:
        noise.append(
            {
                "topic": "Channel mix",
                "finding": (
                    f"Amazon's share of units moved by "
                    f"{channel['amazon_share_swing_pct_points']} percentage points across the "
                    f"whole period. Shopify grew {channel['shopify_growth_full_period_pct']}% and "
                    f"Amazon {channel['amazon_growth_full_period_pct']}%."
                ),
                "why_ignore": "The channels are growing together. There is no mix shift to act on.",
            }
        )

    return noise
