"""Arithmetic and ranking.

The reference figures below were derived independently of the engine, by hand, from the
dataset in the brief. They are pinned here so that a change in the engine that alters a
published number fails loudly instead of quietly producing a different briefing.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src import config
from src.engine import _compound_monthly_growth, analyse_sku, build_facts
from src.render import prose_word_count, render_briefing

# Verified by hand against the dataset before the engine existed.
MARCH_UNITS = 7180
FEBRUARY_UNITS = 6676


# --------------------------------------------------------------------------------------
# Portfolio totals
# --------------------------------------------------------------------------------------


def test_portfolio_totals_match_the_dataset(facts, records):
    assert facts["portfolio"]["current_month_units"] == MARCH_UNITS
    assert sum(r.units["M4"] for r in records) == MARCH_UNITS
    assert facts["portfolio"]["units_by_month"]["February 2026"] == FEBRUARY_UNITS


def test_portfolio_month_on_month_growth(facts):
    expected = round((MARCH_UNITS / FEBRUARY_UNITS - 1) * 100, 1)
    assert facts["portfolio"]["month_on_month_pct"] == expected == 7.5


def test_total_opportunity_is_the_sum_of_its_parts(facts):
    parts = sum(s["money"]["revenue_opportunity_usd"] for s in facts["skus"])
    assert facts["portfolio"]["total_revenue_opportunity_usd"] == pytest.approx(parts, abs=0.01)


def test_shares_of_opportunity_sum_to_one_hundred(facts):
    total = sum(s["money"]["share_of_portfolio_opportunity_pct"] for s in facts["skus"])
    assert total == pytest.approx(100.0, abs=0.5)


# --------------------------------------------------------------------------------------
# Growth
# --------------------------------------------------------------------------------------


def test_growth_compounds_rather_than_averaging():
    """100 to 200 over three months is ~26% a month, not 33%.

    The arithmetic mean would overstate every trend in the portfolio and push fast-looking
    SKUs up a ranking that is supposed to be driven by money.
    """
    compound = _compound_monthly_growth(100, 200, months_apart=3)
    naive_mean = (200 / 100 - 1) / 3

    assert compound == pytest.approx(0.2599, abs=0.001)
    assert compound < naive_mean


def test_growth_of_a_flat_sku_is_zero():
    assert _compound_monthly_growth(500, 500, months_apart=3) == 0.0


def test_growth_handles_a_zero_baseline_without_dividing_by_zero():
    assert _compound_monthly_growth(0, 250, months_apart=3) == 0.0


# --------------------------------------------------------------------------------------
# Cover
# --------------------------------------------------------------------------------------


def test_cover_is_stock_divided_by_current_demand(records, by_sku):
    for record in records:
        expected = record.stock_on_hand / record.units["M4"]
        assert by_sku[record.sku]["inventory"]["current_cover_months"] == pytest.approx(
            round(expected, 2)
        )


def test_cover_in_days_agrees_with_cover_in_months(by_sku):
    for sku in by_sku.values():
        inv = sku["inventory"]
        expected = round(inv["current_cover_months"] * config.DAYS_PER_MONTH)
        assert abs(inv["current_cover_days"] - expected) <= 1


def test_cover_after_inbound_accounts_for_demand_during_the_wait(records, by_sku):
    """Stock does not sit still while a shipment is in transit.

    Adding the inbound units to today's stock without subtracting the months of demand
    consumed before it lands would overstate cover on every SKU with an order open.
    """
    record = next(r for r in records if r.sku == "Manuka Honey MGO 1700+ 100g")
    inv = by_sku[record.sku]["inventory"]

    demand = record.units["M4"]
    naive = (record.stock_on_hand + record.units_on_order) / demand
    correct = (
        record.stock_on_hand - demand * record.order_arrival_months + record.units_on_order
    ) / demand

    assert inv["cover_after_inbound_months"] == pytest.approx(round(correct, 2))
    assert inv["cover_after_inbound_months"] < naive


def test_an_inbound_order_can_still_leave_a_sku_short(by_sku):
    """MGO 1700+ has stock on order and still needs a top-up.

    Treating "an order exists" as "handled" would drop it from the queue.
    """
    sku = by_sku["Manuka Honey MGO 1700+ 100g"]
    assert sku["inventory"]["has_order_placed"] is True
    assert sku["inventory"]["cover_after_inbound_months"] < sku["inventory"]["target_months_cover"]
    assert sku["flags"]["needs_reorder"] is True


# --------------------------------------------------------------------------------------
# Money
# --------------------------------------------------------------------------------------


def test_revenue_opportunity_uses_projected_demand_not_current(by_sku):
    """The brief words these two differently on purpose.

    Cover uses the current month as the sell-through baseline. Revenue opportunity is
    "retail price x projected monthly demand" — a forward number, not this month's.
    """
    for sku in by_sku.values():
        expected = round(sku["demand"]["projected_next_month_units"] * sku["retail_price_usd"], 2)
        assert sku["money"]["revenue_opportunity_usd"] == pytest.approx(expected, abs=0.01)


def test_projected_demand_reflects_the_trend(by_sku):
    growing = by_sku["Bioactive Blend Recovery 250g"]
    assert growing["trend"]["monthly_growth_pct"] > 0
    assert growing["demand"]["projected_next_month_units"] > growing["demand"]["current_month_units"]


# --------------------------------------------------------------------------------------
# Reorder logic
# --------------------------------------------------------------------------------------


def test_reorder_quantity_reaches_target_plus_lead_time(facts, by_sku):
    for row in facts["reorder_queue"]:
        sku = by_sku[row["sku"]]
        inv = sku["inventory"]
        wanted = inv["reorder_point_months"] * sku["demand"]["projected_next_month_units"]
        expected = round(wanted - (inv["stock_on_hand"] + inv["units_on_order"]))
        assert row["quantity_units"] == max(0, expected), row["sku"]


def test_reorder_point_includes_lead_time(by_sku):
    """MGO 263+ 500g is above its target today and still needs an order.

    At 2.49 months of cover against a 2-month target it looks fine. With a 2-month lead
    time, waiting until it hits target means the replenishment lands two months late. This
    SKU only appears in the queue because the trigger accounts for lead time.
    """
    sku = by_sku["Manuka Honey MGO 263+ 500g"]
    inv = sku["inventory"]

    assert inv["current_cover_months"] > inv["target_months_cover"]
    assert inv["current_cover_months"] < inv["reorder_point_months"]
    assert sku["flags"]["below_target_cover"] is False
    assert sku["flags"]["needs_reorder"] is True
    assert sku["flags"]["urgency"] == "act_now"


def test_queue_is_ranked_by_revenue_not_by_who_runs_out_first(facts):
    """The brief is explicit: rank by revenue opportunity, not stock-cover risk."""
    queue = facts["reorder_queue"]
    revenues = [r["revenue_opportunity_usd"] for r in queue]
    assert revenues == sorted(revenues, reverse=True)
    assert [r["rank"] for r in queue] == list(range(1, len(queue) + 1))

    covers = [r["current_cover_months"] for r in queue]
    assert covers != sorted(covers), "ranking by urgency alone would give a different order"


def test_queue_covers_at_least_three_skus(facts):
    """The brief asks for reorder actions on at least three SKUs."""
    assert len(facts["reorder_queue"]) >= 3


def test_every_recommendation_carries_a_quantity_and_a_date(facts):
    for row in facts["reorder_queue"]:
        assert row["quantity_units"] > 0, row["sku"]
        assert row["order_by_date"], row["sku"]


def test_order_by_date_is_marked_overdue_when_it_has_already_passed(facts):
    for row in facts["reorder_queue"]:
        expected = row["order_by_date"] <= config.PLANNING_DATE.isoformat()
        assert row["is_overdue"] is expected, row["sku"]


def test_arrival_and_stockout_dates_are_kept_separate(by_sku):
    """Two different questions: when stock could land, and when the shelf empties."""
    sku = by_sku["Manuka Honey MGO 850+ 500g"]
    inv = sku["inventory"]
    assert inv["earliest_arrival_if_ordered_today"] != inv["projected_stockout_date"]


# --------------------------------------------------------------------------------------
# Tensions and noise
# --------------------------------------------------------------------------------------


def test_the_stalling_overstocked_sku_leads_the_tensions(facts):
    """The hardest decision goes first, ahead of the largest number.

    MGO 263+ 250g has more capital tied up, but its demand is healthy, so it is a
    scheduling question. MGO 100+ 250g has stopped growing while holding stock, which is a
    capital allocation question and the one worth an executive's attention.
    """
    assert facts["tensions"][0]["sku"] == "Manuka Honey MGO 100+ 250g"
    assert facts["tensions"][0]["type"] == "capital_committed_to_a_stalling_sku"

    larger = next(t for t in facts["tensions"] if t["sku"] == "Manuka Honey MGO 263+ 250g")
    assert larger["capital_at_stake_usd"] > facts["tensions"][0]["capital_at_stake_usd"]


def test_the_stalling_sku_is_not_recommended_for_reorder(facts, by_sku):
    sku = by_sku["Manuka Honey MGO 100+ 250g"]
    assert sku["flags"]["overstocked"] is True
    assert sku["flags"]["needs_reorder"] is False
    assert "Manuka Honey MGO 100+ 250g" not in [r["sku"] for r in facts["reorder_queue"]]


def test_stable_channel_mix_is_reported_as_noise(facts):
    assert any(n["topic"] == "Channel mix" for n in facts["noise"])
    assert facts["portfolio"]["channel"]["amazon_share_swing_pct_points"] <= 2.0


def test_a_real_channel_shift_would_not_be_dismissed_as_noise(records):
    """The noise rule must be capable of not firing, or it says nothing."""
    shifted = [
        replace(r, amazon={m: v * (4 if m == "M4" else 1) for m, v in r.amazon.items()})
        for r in records
    ]
    facts = build_facts(shifted)
    assert not any(n["topic"] == "Channel mix" for n in facts["noise"])


# --------------------------------------------------------------------------------------
# Output shape
# --------------------------------------------------------------------------------------


def test_briefing_fits_the_reading_budget(facts):
    assert prose_word_count(render_briefing(facts)) <= config.MAX_BRIEFING_WORDS


def test_briefing_names_months_and_never_shows_column_codes(facts):
    briefing = render_briefing(facts)
    assert "March 2026" in briefing
    for code in config.MONTH_COLUMNS:
        assert f" {code} " not in briefing, f"{code} leaked into the executive output"


def test_determinism(records):
    assert build_facts(records) == build_facts(records)
