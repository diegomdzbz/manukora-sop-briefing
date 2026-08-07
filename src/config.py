"""Every business rule in this project, declared in one place.

A reviewer should be able to read this file alone and know every assumption in play.
Nothing here is inlined in `engine.py`, and no rule is implied by a magic number.

Each rule carries its source: `BRIEF` means it is stated in the exercise brief and is not
negotiable; `ASSUMPTION` means the brief is silent and I chose a value. Every ASSUMPTION is
also listed in OPEN-QUESTIONS.md as something to confirm with the stakeholder.
"""

from datetime import date

# --------------------------------------------------------------------------------------
# Calendar
# --------------------------------------------------------------------------------------

# BRIEF: "M1 = December 2025. M4 = March 2026, the most recent month."
# The dataset speaks in M1-M4. The briefing speaks in month names — an executive should
# never have to translate a column header.
MONTH_COLUMNS = ("M1", "M2", "M3", "M4")

MONTH_LABELS = {
    "M1": "December 2025",
    "M2": "January 2026",
    "M3": "February 2026",
    "M4": "March 2026",
}

CURRENT_MONTH = "M4"
PRIOR_MONTH = "M3"

# The briefing is produced at the close of the reporting month, so all forward-looking
# dates count from the first day of the following month. Fixed rather than `date.today()`
# on purpose: a deterministic engine is a testable engine, and a reviewer running this in
# 2027 should still get the briefing the data describes.
REPORTING_MONTH_END = date(2026, 3, 31)
PLANNING_DATE = date(2026, 4, 1)

DAYS_PER_MONTH = 30.44  # mean Gregorian month, for converting cover in months to days

# --------------------------------------------------------------------------------------
# Trend baselines
# --------------------------------------------------------------------------------------

# BRIEF: "Bioactive Blends launched mid-January 2026. For those SKUs, assess trend from
# M2 to M4, not against M1."
#
# M1 for these SKUs is a partial month of a product that barely existed. Including it
# inflates the growth rate and would push them up the reorder ranking on an artefact of
# the launch date rather than real demand.
TREND_BASELINE_OVERRIDES = {
    "Bioactive Blend Immunity 250g": "M2",
    "Bioactive Blend Energy 250g": "M2",
    "Bioactive Blend Recovery 250g": "M2",
}

DEFAULT_TREND_BASELINE = "M1"

# --------------------------------------------------------------------------------------
# Cover targets
# --------------------------------------------------------------------------------------

# BRIEF: "MGO 1700+ 100g has a target cover of 3 months instead of 2 months because it has
# a premium price point and longer supplier lead times."
#
# The CSV already carries this in Target_Months_Cover. It is restated here so the loader
# can assert the data agrees with the brief — if a future dataset quietly changes that
# column, the run fails loudly instead of producing a plausible wrong answer.
TARGET_COVER_OVERRIDES = {
    "Manuka Honey MGO 1700+ 100g": 3,
}

DEFAULT_TARGET_COVER_MONTHS = 2

# --------------------------------------------------------------------------------------
# Phase-outs
# --------------------------------------------------------------------------------------

# BRIEF: "Propolis Tincture 30ml is being phased out in Q2 2026. Flag if it risks stockout
# before then, but deprioritize reorder unless cover drops below 30 days."
PHASE_OUT_SKUS = {
    "Propolis Tincture 30ml": {
        "phase_out_period": "Q2 2026",
        "phase_out_starts": date(2026, 4, 1),
        "reorder_floor_days": 30,
    },
}

# --------------------------------------------------------------------------------------
# Supplier lead times
# --------------------------------------------------------------------------------------

# ASSUMPTION. The brief gives no lead time. It is inferred from Order_Arrival_Months in the
# dataset, where confirmed shipments land 1-2 months out, so an order placed today is
# assumed to take 2 months to arrive. MGO 1700+ gets 3 because the brief explicitly says it
# has "longer supplier lead times".
#
# This assumption drives every reorder quantity and every order-by date, so it is the first
# thing to confirm with supply chain. See OPEN-QUESTIONS.md.
DEFAULT_LEAD_TIME_MONTHS = 2

LEAD_TIME_OVERRIDES = {
    "Manuka Honey MGO 1700+ 100g": 3,
}

# ASSUMPTION: target cover is the buffer wanted *on arrival*, so a reorder covers the lead
# time plus the target. Ordering only `target x demand` would land the SKU at zero cover on
# the day the stock arrives, which is not what a buffer means.
COVER_INCLUDES_LEAD_TIME = False

# --------------------------------------------------------------------------------------
# Thresholds used to classify SKUs
# --------------------------------------------------------------------------------------

# ASSUMPTION: a SKU sitting at more than this multiple of its target cover has capital tied
# up that could be working elsewhere. Set at 2x so it flags genuine outliers, not the
# ordinary noise of a SKU a few weeks above target.
OVERSTOCK_MULTIPLE = 2.0

# ASSUMPTION: a SKU growing at less than this share of the portfolio's month-on-month rate
# is stalling relative to the business, even if its own growth is positive. Used to say
# "sold poorly" honestly when nothing actually declined.
STALLING_VS_PORTFOLIO_RATIO = 0.5

# BRIEF: the briefing must be readable in five minutes. At a business-prose pace of roughly
# 200 words per minute with time to look at the tables, this is the working ceiling.
# Enforced by test rather than judged by eye.
MAX_BRIEFING_WORDS = 900

# --------------------------------------------------------------------------------------
# Derived helpers
# --------------------------------------------------------------------------------------


def trend_baseline_month(sku: str) -> str:
    """The first month that reflects a normal trading period for this SKU."""
    return TREND_BASELINE_OVERRIDES.get(sku, DEFAULT_TREND_BASELINE)


def lead_time_months(sku: str) -> int:
    """Months between placing an order and receiving it."""
    return LEAD_TIME_OVERRIDES.get(sku, DEFAULT_LEAD_TIME_MONTHS)


def expected_target_cover(sku: str) -> int:
    """What the brief says this SKU's target cover should be."""
    return TARGET_COVER_OVERRIDES.get(sku, DEFAULT_TARGET_COVER_MONTHS)


def is_phasing_out(sku: str) -> bool:
    return sku in PHASE_OUT_SKUS


def phase_out_rule(sku: str) -> dict | None:
    return PHASE_OUT_SKUS.get(sku)
