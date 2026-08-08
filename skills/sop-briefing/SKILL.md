---
name: sop-briefing
description: >
  Generate a monthly S&OP briefing from SKU-level sales and inventory data. Use when
  someone needs a stock and reorder review turned into a decision document an executive
  can act on, or when adapting this pipeline to a new dataset, a new product line, or a
  changed business rule.
---

# S&OP briefing

Turns a table of monthly sales and inventory into a briefing that names decisions, not
observations. This file is the procedure; the reasoning behind the design is in
[`../../CLAUDE.md`](../../CLAUDE.md) and operational failures are in
[`../../RUNBOOK.md`](../../RUNBOOK.md).

## When this applies

You have per-SKU monthly units, a pooled stock position, and a price. You want to know what
to reorder, in what quantity, by when, and in what order of priority.

You do **not** need this for a single-SKU question or a straight stock count. It earns its
keep when the ranking matters — when several SKUs need attention and the question is which
one gets the capital.

## What the data must look like

One row per SKU. Monthly unit columns per channel, and:

| Column | Meaning |
|---|---|
| `Stock_On_Hand` | Current pooled units, all channels |
| `Units_On_Order` | Quantity in the next confirmed shipment |
| `Order_Arrival_Months` | Months until it lands. **`0` means no order exists** |
| `Target_Months_Cover` | Desired buffer, in months |
| `Retail_Price_USD` | Current list price |

Channel columns are summed. If channels draw on *separate* inventory, this pipeline is
wrong for your data and the cover maths needs rewriting first.

## Running it

```bash
python -m src.main --no-llm     # complete briefing, no API key
python -m src.main              # model writes the prose
python -m pytest -q             # verify before you send anything
```

## Adapting it

Every business rule lives in `src/config.py`. Nothing is inlined in the engine, so this is
the only file you edit — and each rule is tagged `BRIEF` (given, non-negotiable) or
`ASSUMPTION` (a judgement call, listed in `OPEN-QUESTIONS.md`).

**A SKU needs a different cover target.** Add it to `TARGET_COVER_OVERRIDES`, and make sure
the dataset column agrees. The loader cross-checks the two and refuses to run if they
disagree — that check exists so a quiet upstream change fails loudly instead of producing a
plausible wrong answer.

**A product line launched mid-period.** Add it to `TREND_BASELINE_OVERRIDES` with the first
month that reflects normal trading. A partial launch month inflates growth, and growth
drives projected demand, which drives the ranking — so the wrong baseline does not just
misreport a trend, it reorders the recommendations.

**A SKU is being discontinued.** Add it to `PHASE_OUT_SKUS` with a reorder floor in days.
It will still be flagged for stockout risk — deprioritised is not the same as ignored — but
it stops competing for capital with products that have a future.

**The supplier lead time changed.** `DEFAULT_LEAD_TIME_MONTHS` and `LEAD_TIME_OVERRIDES`.
Expect every quantity and every date to move; this is the assumption with the widest reach.

After any change: `pytest`. The business-rule tests are written to fail on exactly these
edits, so a red suite here means the guard is working. Update the test in the same commit
as the rule, with the reason.

## Before you send it

1. `pytest` green — including `test_output_integrity.py`, which asserts every figure in the
   briefing traces back to a computed fact.
2. Read it with a clock. The reading budget is prose only; tables are scanned, not read.
3. Check the assumptions still hold. `OPEN-QUESTIONS.md` lists what was guessed. If lead
   time or the phase-out date has been answered since, update `config.py` first.

## The one rule that is not negotiable

**No figure is typed by hand into any document — briefing, README, commit message, or
this file.** Every number is read from `facts.json` or produced by the engine.

This is not fastidiousness. During this project's design phase two figures were written in
by hand because they seemed right; both were wrong, and both sat in the document that
proposed a test against exactly that failure. If a number feels too small to route through
the engine, that is the one to route through the engine.
