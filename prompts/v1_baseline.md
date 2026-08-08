# v1 — the first prompt

This is where I started: hand the model the spreadsheet and ask for a briefing. It is
committed because the brief asks for the first instruction as well as the final one, and
because the reasons it fails are the reasons the rest of this repo is shaped the way it is.

**This prompt is not used by the code.** See `v2_final.md` for the one that is, and
`CHANGELOG.md` for what changed and why.

---

You are a supply chain analyst at Manukora, a New Zealand Manuka honey brand selling into
the US through Shopify, Amazon and retail.

Below is monthly sales and inventory data for our SKUs across the last four months (M1 is
December 2025, M4 is March 2026, the most recent month).

Write a monthly S&OP briefing that a non-technical executive can read in five minutes and
act on. Cover:

- What sold well and what sold poorly in the most recent month
- Trend context across the prior months
- Any SKUs where stock cover is at risk
- Reorder recommendations for at least three SKUs, ranked by revenue opportunity
  (retail price x projected monthly demand)
- The business reasoning behind each recommendation

Be thorough and make sure your numbers are accurate.

```csv
{{DATA}}
```

---

## What it actually produced

v1 **was run** — same model as the production path, so the prompt is the only variable.
Output in [`v1_baseline_output.md`](v1_baseline_output.md), findings in
[`CHANGELOG.md`](CHANGELOG.md). Short version: it is a confident, well-formatted document
with a recommendation in it that would lose money, and nothing on the page says which parts
to trust.

---

## Why this fails

Four problems, in order of how much they matter.

**1. The model does the arithmetic, so nothing can be verified.** Cover, growth rates,
projected demand, revenue opportunity and reorder quantities are all derived inside the
response. There is no intermediate artefact to test, so "is this briefing correct?" can
only be answered by recomputing every figure by hand — every month, forever. "Make sure
your numbers are accurate" is a wish, not a control.

**2. The trap rules are absent.** Nothing here tells the model that Bioactive Blends
launched mid-January and must be trended from M2, that MGO 1700+ carries a three-month
target, that Propolis is being retired, or that `Order_Arrival_Months = 0` means no order
exists rather than one arriving today. A model reading this prompt will apply the obvious
reading of each column and be confidently wrong in four places.

**3. Nothing constrains the shape.** The tension section, the reorder quantities, the
order-by dates — all of them are things the model might include. Some months it will,
some months it won't, and the difference will only be noticed by whoever reads it.

**4. "Be thorough" is the wrong instruction.** It produces length, not decisions. The
brief is explicit that a weak output restates the spreadsheet; asking for thoroughness is
asking for exactly that.
