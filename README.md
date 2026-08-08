# Manukora — Monthly S&OP Briefing Automation

Turns four months of SKU-level sales and inventory data into a monthly S&OP briefing an
executive can read in five minutes and act on.

**→ [The generated briefing](output/sop_briefing_march-2026.md)** · **→ [Part 2 architecture](ARCHITECTURE.md)**

> **Ten minutes:** the [briefing](output/sop_briefing_march-2026.md) — it is the deliverable —
> then [where the AI was wrong](#where-the-ai-helped-and-where-it-was-wrong).
> **Twenty:** add [`prompts/CHANGELOG.md`](prompts/CHANGELOG.md), which is what happened when
> I ran the naive first prompt, and [`n8n/VERIFICATION.md`](n8n/VERIFICATION.md).

![The n8n workflow](n8n/canvas.png)

*The monthly workflow as imported. It [runs end to end in twenty seconds](n8n/VERIFICATION.md)
and writes a briefing held to the same tests as the CLI's. Slack is wired and deliberately
off; no credential warnings because the key comes from the container environment.*

---

## Quick start

```bash
git clone https://github.com/diembz/manukora-sop-briefing
cd manukora-sop-briefing
pip install pytest              # the only dependency, and only for the tests

python -m src.main --no-llm     # complete briefing, no API key required
python -m pytest -q             # 61 tests, no secrets needed
```

`--no-llm` renders the whole briefing from a deterministic template — same figures, plainer
prose. Nothing here needs a key, and the briefings are committed, so the output can be
evaluated without running anything.

To have a model write the prose: put `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` in `.env` and
drop the flag. Both providers enforce the output schema server-side and neither needs an
SDK — plain HTTPS over the standard library, so you are not installing a client for a
vendor you do not use.

| File in `output/` | Written by |
|---|---|
| `sop_briefing_march-2026.md` | **A model, via the CLI.** The deliverable |
| `sop_briefing_from_n8n.md` | **The n8n workflow**, run end to end |
| `sop_briefing_march-2026_template.md` | The deterministic template. The control |
| `facts_march-2026.json` | The engine. All three render from this |

All three are held to the same tests: no figure without a source, inside the reading budget,
no cents in prose, leading with the decision the engine ranked first.

> **Data hygiene note.** The committed briefing was generated with Gemini, whose free tier
> reserves the right to train on submitted data. Acceptable for mock exercise data; with
> real Manukora figures the provider choice would have to be made on that basis rather than
> on which key was to hand.

---

## The idea

**The language model never does arithmetic.**

Every number is computed in Python, covered by a test, and serialised to `facts.json`. The
model receives those facts and writes prose around them — it cannot calculate or infer a
figure, because [the schema it must satisfy](src/schema.py) has no numeric field at all.

That split is what makes the output checkable: `tests/test_output_integrity.py` extracts
every figure from the finished briefing and asserts each traces back to a computed fact. An
invented number fails the build.

```
data/mock_sales.csv
      │
      ▼
  engine.py ──────────────► facts.json ──────┬──► narrative.py (model writes prose)
  every calculation,                          │
  every business rule,                        └──► render.py   (template writes prose)
  covered by tests                                     │
                                                       ▼
                                            compose_briefing()
                                        one assembler, tables from facts
```

Both paths load the same prompt and render through the same assembler, so they cannot drift
into producing different documents — and the template render doubles as a control on the
model's.

---

## What the briefing actually says

Not a summary of the spreadsheet. Three findings drove the recommendations:

**The weakest seller is where the capital is stuck.** MGO 100+ 250g grew +0.8% against a
range moving +7.5% — the only SKU not keeping pace — while holding 6.2 months of cover
against a 2-month target, with 2,000 more units inbound taking it to 7.14. The
recommendation is not to reorder. It is to hold that shipment and move the capital to the
six SKUs that are actually short.

**An order in flight does not settle the question.** MGO 1700+ 100g has stock on the water
and still lands at 2.13 months against its 3-month target. Treating "an order exists" as
"handled" would have dropped it from the queue entirely.

**The reorder trigger accounts for lead time.** Firing when cover falls below target means
the replenishment arrives two months after the buffer was already breached. Triggering at
`target + lead time` surfaces MGO 263+ 500g — above target today, unrecoverable if you wait
for it to dip.

---

## Business rules from the brief

All in [`src/config.py`](src/config.py), tagged `BRIEF` where the exercise states them and
`ASSUMPTION` where it does not. Each has a test that fails on the *wrong* reading, not just
one that passes on the right one.

| Rule | How it is handled |
|---|---|
| M1 is December 2025, M4 is March 2026 | The output names months. `M4` is a column header, not something an executive should translate |
| Bioactive Blends launched mid-January | Trend measured from January. December would inflate their growth on an artefact of the launch date |
| Propolis Tincture is phasing out in Q2 2026 | Flagged for stockout risk, not reordered above 30 days of cover |
| MGO 1700+ 100g targets 3 months | Declared in config and cross-checked against the dataset on load |
| March demand is the sell-through baseline | Cover is stock divided by March units |
| Shopify and Amazon pool one inventory | Demand is the sum of both channels everywhere |
| `Order_Arrival_Months = 0` means no order | Treated as "nothing inbound", never "arrives immediately" |

## Assumptions I made

The brief is silent on these. Each is declared in `config.py` and listed in
[`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md) with what would change if the answer differs.

- **Supplier lead time is 2 months, 3 for MGO 1700+.** Not in the data; inferred from
  `Order_Arrival_Months`. It drives every quantity and date, so it is the first thing to
  confirm.
- **Reorder when cover falls below target *plus* lead time**, not at the target itself.
- **Target cover is the buffer wanted on arrival**, so a reorder covers transit and target.
- **"Overstocked" is more than twice the target** — a threshold chosen to flag outliers.
- **"Sold poorly" means falling behind the range.** Nothing declined this month, so the
  briefing says that rather than implying a fall that did not happen.

---

## Approach and tradeoffs

**Deterministic engine, model only for prose.** Costs a schema and an assembler. Buys an
output that can be tested and a briefing that runs with no key. The alternative — one
prompt, one call — is a third of the code and cannot be verified without recomputing every
figure by hand, every month.

**Structured outputs over free text.** A briefing cannot come back missing the tension
section or with a recommendation that has no rationale. Costs some flexibility in how the
model organises its answer; buys a shape guaranteed before anyone reads it.

**No SQL in Part 1.** A twelve-row CSV does not need a database, and adding one would be the
overbuilding the brief warns against. It belongs in Part 2, where a *daily* brief genuinely
needs snapshot tables to answer "what changed overnight". Said here so it reads as a
decision rather than an omission.

**Depth where the money is.** The top two recommendations get a paragraph of reasoning, the
rest get one clause. Six equal paragraphs would bury the two that matter.

---

## The prompt stack

| | Where | What it does |
|---|---|---|
| **Build-time** | [`CLAUDE.md`](CLAUDE.md), [`prompts/build-stack.md`](prompts/build-stack.md) | How this repo was built with Claude Code |
| **Run-time** | [`prompts/v1_baseline.md`](prompts/v1_baseline.md) → [`v2_final.md`](prompts/v2_final.md) | How a briefing gets written each month |

**The first prompt** handed the model the raw CSV and asked for a briefing. **The one I use**
hands it a fact pack with every figure already computed and asks only for prose.

### I ran v1, and it recommended buying stock for a discontinued product

Same model as the production path, so the prompt is the only variable. Output at
[`prompts/v1_baseline_output.md`](prompts/v1_baseline_output.md); reproduce with
`python scripts/run_v1_baseline.py`.

v1 is not obviously bad — it got the MGO 1700+ three-month target right, read
`Order_Arrival_Months = 0` correctly, and got every cover figure right to two decimals.
Then it says this about Propolis Tincture, which is being retired this quarter:

> *"Stock cover is at a critical 1.37 months. Issue an immediate emergency batch order of
> 500 units."*

It never mentions the phase-out. It also got January and February portfolio totals wrong —
by 48 and 120 units, in the trend section the brief asks for by name — while getting
December and March exactly right.

**The problem is not that v1 made mistakes. It is that they are invisible.** Correct figures
and wrong ones are formatted identically, and the recommendation that would lose money is
the most confidently worded sentence on the page. No wording fixes that — only moving the
arithmetic somewhere it can be tested. v1's last line was "make sure your numbers are
accurate", which is the tell: an instruction you cannot check is a hope.

Change-by-change account, and what running both providers showed, in
[`prompts/CHANGELOG.md`](prompts/CHANGELOG.md).

---

## Where the AI helped, and where it was wrong

**Where it helped:** drafting the engine and tests quickly, and — more usefully — structured
review passes over the design before any code existed. One asked "would this actually run?"
and found that n8n cannot execute the Python, so the central arrow in my own diagram had
nothing behind it.

**Where it was wrong.** Each of these is a commit:

- **It fabricated two figures** in the design document — a "22% of total" that was 16.6%,
  and a "~1,150 units" that was 934. Both plausible, both wrong, both in the document that
  proposed a test against exactly this failure. That produced the no-hand-typed-figures rule
  and `tests/test_output_integrity.py`.
- **It got the reorder trigger wrong**, firing two months too late on a two-month lead time.
- **It wrote a sentence that was confidently false**, conflating an order's arrival date with
  the stockout date.
- **It took a decision that belonged to the engine**, choosing its own headline instead of
  the ranked one. Fixed in the prompt *and* enforced in `check_against_facts()`.
- **My own budget instruction was wrong.** It named the whole document's ceiling, but the
  model only authors part of it. Told 750 the model wrote 755 — obedient, on target, still
  over. The allowance is now computed from the renderer's overhead rather than typed.

Running it also found two false positives in the integrity check that only real prose
triggers: abbreviated SKU names, and a US-format date orphaning its year. Both would have
been flaky CI failures within a week, and a flaky check gets deleted rather than fixed. Both
are regression tests now.

**What has not been run:** nothing. Both provider paths, the CLI and the n8n workflow have
each produced a briefing that passes the same tests.

---

## How I verified it

```bash
python -m pytest -q     # 61 tests
```

**The maths.** `tests/test_business_rules.py` has one test per rule, and where possible each
demonstrates what the *wrong* reading produces. Reading `Order_Arrival_Months = 0` as
"arrives now" would credit SKUs with stock they do not have and empty the queue of exactly
the SKUs needing attention — asserted, not assumed. `tests/test_engine.py` pins reference
totals worked out by hand before the engine existed, and covers what is easy to get subtly
wrong: growth compounds rather than averaging, and cover-after-arrival subtracts the demand
consumed in transit.

**The output.** `tests/test_output_integrity.py` asserts every figure traces to `facts.json`
and — because a test that cannot fail proves nothing — separately proves it catches an
invented figure and does not fire on SKU names or dates.

**The documentation.** `tests/test_docs_claims.py` checks the one figure no fact pack can
source: the size of the suite, quoted above. It had already drifted once.

**Reproducibility.** CI runs the suite with no secrets, regenerates the briefing without an
API key, and fails if the committed output drifts from the code.

---

## Repository layout

| Path | |
|---|---|
| [`data/`](data/) | The mock dataset from the brief, verbatim |
| [`src/`](src/) | Config, loader, engine, schema, providers, narrative, renderer, CLI, and the `/facts` service n8n calls |
| [`scripts/`](scripts/) | `run_v1_baseline.py` — reproduces the v1 run |
| [`prompts/`](prompts/) | Both prompt stacks and the changelog |
| [`tests/`](tests/) | Business rules, arithmetic, output integrity, documentation claims |
| [`output/`](output/) | The generated briefings and their fact pack |
| [`n8n/`](n8n/) | Workflow export, canvas screenshot, and how it was verified |
| [`skills/`](skills/) | Reusable procedure for running and adapting this |
| [`CLAUDE.md`](CLAUDE.md) | Build-time instructions and the rules this repo runs under |
| [`RUNBOOK.md`](RUNBOOK.md) | What breaks and how to fix it |
| [`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md) | What I would have asked before anyone acts on this |

---

## What I would do differently

**I planned too much and tested too late.** The design went through several review passes
before any code existed, and three of the things those passes eventually found would have
surfaced in twenty minutes of writing a first version. The clearest case is the one that
changed the architecture: *n8n cannot execute this project's Python.* That took a careful
fourth reading of my own plan to notice. It also takes ten seconds to check —

```bash
docker run --rm n8nio/n8n which python3
```

A cheap experiment beats a careful reading, and I had the ratio backwards.

**The v1 baseline should have been the first thing I ran, not one of the last.** It is the
strongest evidence in this repository — a naive prompt recommending an emergency reorder of
a discontinued product — and it arrived near the end, as a way of proving something I had
already decided. Run first, its failures would have *been* the specification: I would not
have had to reason about which rules a model gets wrong, because it would have shown me.

**The reading budget was my own invention, and I let it cost more than it was worth.** The
brief asks for five minutes; the 900-word ceiling is a proxy I chose and never validated,
then enforced with a retry mechanism when a provider overshot it. Measuring once what five
minutes actually means would have been cheaper than building around a number I made up.

Declining to raise that ceiling once a result depended on it was still right. Setting it so
firmly, so early, without checking it, was not.

## What I would do next

Connect the real sources. The engine takes a validated table; swapping the CSV loader for
Shopify and SP-API clients does not touch the calculations or the tests.

Then add the previous year. Four months cannot separate growth from season, and every
projection here extrapolates a four-month trend — the ranking is fairly robust to that, but
the absolute figures deserve less confidence than they currently invite.
