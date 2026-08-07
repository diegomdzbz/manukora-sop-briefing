"""One test per rule the brief states about how to read this data.

These are the rules that are easy to miss and expensive to get wrong. Each test does more
than confirm the current output: where it can, it also demonstrates what the wrong reading
would have produced, so the test documents the trap as well as guarding against it.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src import config
from src.engine import analyse_sku, build_facts
from src.loader import DataValidationError, SkuRecord, load

BIOACTIVE = "Bioactive Blend Recovery 250g"
PREMIUM = "Manuka Honey MGO 1700+ 100g"
PHASE_OUT = "Propolis Tincture 30ml"


# --------------------------------------------------------------------------------------
# "Bioactive Blends launched mid-January 2026. For those SKUs, assess trend from M2 to M4."
# --------------------------------------------------------------------------------------


def test_bioactive_trend_excludes_launch_month(by_sku):
    sku = by_sku[BIOACTIVE]
    assert sku["trend"]["baseline_month"] == "January 2026"
    assert sku["trend"]["baseline_excludes_launch_month"] is True


def test_non_bioactive_skus_still_trend_from_december(by_sku):
    assert by_sku["Manuka Honey MGO 100+ 250g"]["trend"]["baseline_month"] == "December 2025"


def test_measuring_bioactive_from_december_would_overstate_its_growth(records):
    """The trap, made explicit.

    December is a partial month for a product that launched mid-January. Anchoring to it
    inflates the growth rate, which inflates projected demand, which inflates revenue
    opportunity — and revenue opportunity is what ranks the reorder queue. The wrong
    baseline does not just misreport a trend, it reorders the recommendations.
    """
    record = next(r for r in records if r.sku == BIOACTIVE)
    correct = analyse_sku(record, portfolio_mom_growth=0.075)

    original = config.TREND_BASELINE_OVERRIDES.pop(BIOACTIVE)
    try:
        naive = analyse_sku(record, portfolio_mom_growth=0.075)
    finally:
        config.TREND_BASELINE_OVERRIDES[BIOACTIVE] = original

    assert naive["trend"]["monthly_growth_pct"] > correct["trend"]["monthly_growth_pct"]
    assert naive["money"]["revenue_opportunity_usd"] > correct["money"]["revenue_opportunity_usd"]


# --------------------------------------------------------------------------------------
# "MGO 1700+ 100g has a target cover of 3 months instead of 2 months."
# --------------------------------------------------------------------------------------


def test_premium_sku_uses_three_month_target(by_sku):
    assert by_sku[PREMIUM]["inventory"]["target_months_cover"] == 3


def test_every_other_sku_uses_the_two_month_default(by_sku):
    for name, sku in by_sku.items():
        if name != PREMIUM:
            assert sku["inventory"]["target_months_cover"] == 2, name


def test_premium_sku_would_look_healthy_under_the_default_target(by_sku):
    """At 2.8 months of cover it clears a 2-month target and misses a 3-month one.

    Applying the default would drop it out of the reorder queue entirely. This SKU is the
    reason the rule exists, and the reason the rule is worth a test.
    """
    cover = by_sku[PREMIUM]["inventory"]["current_cover_months"]
    assert cover > config.DEFAULT_TARGET_COVER_MONTHS
    assert cover < by_sku[PREMIUM]["inventory"]["target_months_cover"]
    assert by_sku[PREMIUM]["flags"]["below_target_cover"] is True


def test_dataset_disagreeing_with_the_brief_is_rejected(records, tmp_path):
    """The cross-check, not just the happy path."""
    original = config.TARGET_COVER_OVERRIDES[PREMIUM]
    config.TARGET_COVER_OVERRIDES[PREMIUM] = 4
    try:
        with pytest.raises(DataValidationError, match="target cover"):
            load("data/mock_sales.csv")
    finally:
        config.TARGET_COVER_OVERRIDES[PREMIUM] = original


# --------------------------------------------------------------------------------------
# "Propolis Tincture 30ml is being phased out in Q2 2026. Flag if it risks stockout before
#  then, but deprioritize reorder unless cover drops below 30 days."
# --------------------------------------------------------------------------------------


def test_phase_out_sku_is_flagged_but_not_reordered(by_sku, facts):
    sku = by_sku[PHASE_OUT]
    assert sku["flags"]["phasing_out"] is True
    assert sku["flags"]["below_target_cover"] is True, "it is genuinely short of the usual buffer"
    assert sku["flags"]["needs_reorder"] is False, "but the rule deprioritises it"
    assert sku["inventory"]["current_cover_days"] > 30
    assert PHASE_OUT not in [r["sku"] for r in facts["reorder_queue"]]


def test_phase_out_stockout_risk_is_still_surfaced(facts):
    """Deprioritised is not the same as ignored. The brief asks for the flag either way."""
    flagged = [t for t in facts["tensions"] if t["sku"] == PHASE_OUT]
    assert flagged, "a phase-out SKU running dry inside its own phase-out window must surface"
    assert "phase_out" in flagged[0]["type"]


def test_phase_out_sku_is_reordered_once_cover_drops_below_thirty_days(records):
    """The other side of the threshold."""
    record = next(r for r in records if r.sku == PHASE_OUT)
    starved = replace(record, stock_on_hand=100)  # 100 / 168 per month is under 30 days

    result = analyse_sku(starved, portfolio_mom_growth=0.075)
    assert result["inventory"]["current_cover_days"] < 30
    assert result["flags"]["needs_reorder"] is True


# --------------------------------------------------------------------------------------
# "Order_Arrival_Months = 0 means no order is currently placed. It does not mean the order
#  arrives immediately."
# --------------------------------------------------------------------------------------


def test_zero_arrival_months_means_no_order_placed(records):
    for record in records:
        if record.order_arrival_months == 0:
            assert record.has_order_placed is False, record.sku


def test_skus_with_no_order_are_not_credited_with_incoming_stock(by_sku):
    for name, sku in by_sku.items():
        inv = sku["inventory"]
        if not inv["has_order_placed"]:
            assert inv["cover_after_inbound_months"] is None, name
            assert inv["inbound_arrival_date"] is None, name


def test_reading_zero_as_immediate_arrival_would_hide_real_reorders(records):
    """The trap, made explicit.

    Every SKU in the reorder queue that has no order placed reports zero in both order
    columns. Reading that as "stock landing today" would credit them with inventory they do
    not have and empty the queue of exactly the SKUs that need attention.
    """
    unordered = [r for r in records if r.order_arrival_months == 0]
    assert unordered, "the dataset must exercise this rule for the test to mean anything"

    facts = build_facts(records)
    queue = {r["sku"] for r in facts["reorder_queue"]}
    assert queue & {r.sku for r in unordered}, "unordered SKUs must be able to reach the queue"


# --------------------------------------------------------------------------------------
# "All Shopify and Amazon orders draw from one pooled inventory position."
# --------------------------------------------------------------------------------------


def test_demand_pools_both_channels(records, by_sku):
    for record in records:
        expected = record.shopify["M4"] + record.amazon["M4"]
        assert by_sku[record.sku]["demand"]["current_month_units"] == expected


def test_cover_is_measured_against_pooled_demand_not_one_channel(records, by_sku):
    """Using a single channel's demand would roughly double every cover figure.

    A SKU at 1.8 months of pooled cover would report over 3 months on Shopify alone, clear
    its target, and disappear from the reorder queue while genuinely running out.
    """
    record = next(r for r in records if r.sku == "Manuka Honey MGO 850+ 500g")
    pooled_cover = by_sku[record.sku]["inventory"]["current_cover_months"]
    shopify_only_cover = record.stock_on_hand / record.shopify["M4"]

    assert pooled_cover < record.target_months_cover
    assert shopify_only_cover > record.target_months_cover
