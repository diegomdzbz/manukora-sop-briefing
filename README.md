# Manukora — Monthly S&OP Briefing Automation

Turns four months of SKU-level sales and inventory data into a monthly S&OP briefing an
executive can read in five minutes and act on.

Built as a practical exercise. Part 1 (this build) is below; Part 2 (the Morning Intelligence
Brief architecture) is in [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Status

Work in progress. Sections land as their branches merge — see the commit history.

- [x] Scaffold, mock data, build instructions
- [x] Calculation engine
- [ ] Tests and CI
- [ ] Narrative layer
- [ ] Output integrity checks
- [ ] n8n orchestration
- [ ] Final briefing and documentation

---

## The idea in one paragraph

The maths happens in Python, is covered by tests, and is serialised to `facts.json`. The
language model receives those facts and writes the prose around them — it never calculates
anything. That split is what makes the output checkable: `tests/test_output_integrity.py`
asserts that every figure in the generated briefing traces back to a computed fact. See
[`CLAUDE.md`](CLAUDE.md) for the rules this repo is built under.

---

## Quick start

```bash
git clone <this repo>
cd manukora-sop-briefing
pip install -r requirements.txt

# Full briefing, no API key required
python -m src.main --no-llm
```

The prompt stack and verification notes follow as the build lands.

---

## Business rules taken from the brief

All of these live in [`src/config.py`](src/config.py), tagged `BRIEF` where the exercise
states them and `ASSUMPTION` where it does not.

| Rule | How it is handled |
|---|---|
| M1 is December 2025, M4 is March 2026 | The output names months. `M4` is a column header, not something an executive should translate |
| Bioactive Blends launched mid-January | Their trend is measured from January onward. Including December would inflate growth on an artefact of the launch date and push them up the ranking |
| Propolis Tincture 30ml is phasing out in Q2 2026 | Flagged for stockout risk, but not reordered unless cover drops below 30 days |
| MGO 1700+ 100g targets 3 months of cover | Declared in config and cross-checked against the dataset on load |
| March demand is the sell-through baseline | Cover is stock divided by March units |
| Shopify and Amazon pool one inventory position | Demand is the sum of both channels everywhere a cover or reorder figure is derived |
| `Order_Arrival_Months = 0` means no order exists | Treated as "nothing inbound", never as "arrives immediately" |

## Assumptions I made

The brief is silent on these. Each is declared in `config.py` and listed in
[`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md) as something I would confirm before anyone acts on
the output.

- **Supplier lead time is 2 months, and 3 months for MGO 1700+ 100g.** Not in the data.
  Inferred from `Order_Arrival_Months`, where confirmed shipments land 1–2 months out; the
  brief says MGO 1700+ has longer lead times. This drives every reorder quantity and date,
  so it is the first thing to check.
- **Reorder when cover falls below target *plus* lead time.** Ordering at the target itself
  means the stock lands two months after the buffer was already breached.
- **Target cover is the buffer wanted on arrival**, so a reorder covers lead time and target
  rather than target alone.
- **Overstocked means more than twice the target.** A threshold, chosen to flag outliers
  rather than SKUs a few weeks above plan.
- **"Sold poorly" means falling behind the portfolio.** Nothing declined in absolute terms
  this month, so the honest reading is relative, and the briefing says so explicitly rather
  than implying a decline that did not happen.

---

## Repository layout

| Path | What it holds |
|---|---|
| `data/` | The mock dataset |
| `src/` | Engine, narrative layer, CLI |
| `prompts/` | The run-time prompt stack and its changelog |
| `tests/` | Business-rule and output-integrity tests |
| `output/` | The generated briefing and its fact pack |
| `n8n/` | Workflow export and canvas screenshot |
| `skills/` | Reusable procedure for running and adapting this |
| `CLAUDE.md` | Build-time instruction stack |
| `RUNBOOK.md` | What breaks and how to fix it |
| `OPEN-QUESTIONS.md` | What I would have asked the stakeholder on day one |
