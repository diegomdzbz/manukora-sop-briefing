# Prompt changelog

What changed between `v1_baseline.md` and `v2_final.md`, and why.

---

## The change that mattered: the prompt got smaller because the system got bigger

v1 asked the model to analyse and write. v2 asks it only to write. That is not a wording
improvement — it is a different architecture, and every other change follows from it.

| | v1 | v2 |
|---|---|---|
| Input | The raw CSV | A fact pack with every figure computed |
| Model's job | Analyse, calculate, decide, write | Write |
| Numbers | Produced by the model | Produced by `engine.py`, rendered by `render.py` |
| Output shape | Whatever prose came back | Constrained by a JSON schema |
| Verifiable? | Only by recomputing every figure by hand | `pytest` |

**The reason v1 could not be fixed by better wording:** its failure mode is that correct
output and confident-but-wrong output look identical to the reader. No instruction solves
that. "Make sure your numbers are accurate" — v1's last line — is the tell: an instruction
you cannot check is a hope.

---

## Change by change

**Moved every calculation into `engine.py`.** The trap rules from the brief (Bioactive
trended from January, MGO 1700+ on a three-month target, Propolis deprioritised, zero
arrival months meaning no order) went into `config.py` where a test can assert them, rather
than into prose where the model might honour them.

**Added "do not calculate anything", stated at its limit.** The instruction names the case
that actually goes wrong — a difference between two numbers *both already present* in the
fact pack. That is the one a model talks itself into, because it feels like reading rather
than deriving.

**Constrained the output shape.** v1's structure was a suggestion. v2 returns an object
validated against `schema.py`, so a briefing cannot come back missing the tension section
or with a recommendation that has no rationale. `check_against_facts()` then confirms there
is exactly one rationale per queued SKU.

**Replaced "be thorough" with "lead with the decision".** Thoroughness produces length.
The brief is explicit that restating the spreadsheet is the failure mode, so v2 asks for
the action first and the evidence second.

**Told it the tables exist.** v2 explains that rendered tables sit under its prose, so the
model stops narrating figures the reader can already see. This did more for concision than
any "be concise" instruction.

**Added "say what the data actually supports".** Nothing declined this month. Under v1 the
likely output implies something fell, because "what sold poorly" invites a decline. v2 has
the model say plainly that the weakest SKU grew slower than the range.

---

## Where the AI was wrong, and what I fixed by hand

The honest version of this section, because it is the one worth reading.

**It fabricated two figures in the design document.** While planning, I wrote that one SKU
was "22% of total revenue opportunity" and that another needed "~1,150 units". Checked
against the engine: 16.6% and 934. Both were plausible, both were wrong, and both appeared
in the document that proposed a test against exactly this failure.

That is the origin of the no-hand-typed-figures rule in `CLAUDE.md` and of
`test_output_integrity.py`. The test is not a hypothetical guard against model
hallucination — it is a response to a failure that already happened, in this repo, during
this build.

**It got the reorder trigger wrong.** The first engine fired when cover fell below target.
With a two-month lead time that means the replenishment lands two months *after* the buffer
was breached. Fixed to `cover < target + lead_time`, which is the standard reorder point —
and which surfaced MGO 263+ 500g, a SKU sitting above target today that still cannot be
replenished in time. The same pass caught that an inbound order does not settle the
question: MGO 1700+ has stock on the water and still lands short.

**It wrote a sentence that was confidently false.** The briefing said an order placed today
"lands around 16 June, which is roughly when the shelf empties" — but that date was the
stockout, not the arrival. Two different quantities, collapsed into one clause that read
fine. Fixed by computing both dates separately in the engine
(`earliest_arrival_if_ordered_today` vs `projected_stockout_date`) so the sentence has to
name which is which.

**It picked the wrong headline.** The briefing led with the SKU that had the most capital
tied up, rather than the one with the hardest decision — a fast-selling product that is
merely over-covered is a scheduling question, not a capital one. Fixed by ranking tensions
on decision type first and size second.

**It designed a workflow that could not run.** The n8n container has no Python and no
access to the repo on the host, so "n8n runs the engine" was an arrow with nothing behind
it. Fixed with a two-service `docker-compose` and an HTTP endpoint.

**It had two paths generating the same document.** The CLI and the n8n node would each
have produced a briefing, with nothing saying which one was authoritative. Fixed by making
`compose_briefing()` the single assembler and `v2_final.md` the single prompt, loaded by
both.

---

## What running it actually taught me

v2 **was** run. `output/sop_briefing_march-2026.md` is written by a model, and it passes
`test_output_integrity.py` — every figure in it traces back to `facts.json`. That is the
central claim of this architecture, demonstrated rather than asserted.

Three things surfaced on the first live run that no amount of reading the code would have
found. All three are now regression tests.

**The integrity check had two false-positive modes, and real model prose triggered both.**

*Abbreviated SKU names.* The check stripped exact SKU names before extracting figures. The
model wrote "the MGO 263+ and MGO 514+ formats" and "MGO 100+ 250g" — dropping the "Manuka
Honey" prefix, as any writer would — and five product codes were reported as invented
figures. Fixed by treating a digit followed by `+`, `g` or `ml` as an identifier wherever
it appears, which is the right rule rather than a longer list of names.

*Date order.* The renderer writes "1 May 2026". The model wrote "May 1, 2026" in prose,
which left the year orphaned and reported `2026` as an unsourced figure. Neither format is
wrong; the check now reads both.

Both would have been flaky-test-in-CI within a week, and a flaky integrity check gets
deleted rather than fixed. Finding them on a real response, before the repo shipped, is
the argument for running the thing.

**The model took a decision that belonged to the engine.** Asked for a headline, it led
with the most urgent reorder (MGO 514+ 500g, overdue, $34k at stake) instead of the hardest
decision (MGO 100+ 250g, stalled and over-covered). Both are defensible reads — but ranking
is the engine's job, and letting the model choose meant the lead would vary run to run.
Fixed in two places: `v2_final.md` now says the headline is the first entry in `tensions`,
and `check_against_facts()` rejects a briefing that leads with anything else. Prompt for
intent, enforce in code.

## What v1 produced when it was actually run

The critique above was written before running it. Then it was run — same model as the
production path, so the prompt is the only variable — and the output is committed at
[`v1_baseline_output.md`](v1_baseline_output.md). Reproduce with
`python scripts/run_v1_baseline.py`.

**Give it credit first.** v1 is not obviously bad. It correctly applied the MGO 1700+
three-month target, correctly read `Order_Arrival_Months = 0` as "no order placed", got
every cover figure right to two decimals, ranked by revenue opportunity using projected
rather than current demand, and produced a well-organised document. Anyone skimming it
would file it as competent work.

**Then look at what it recommends for Propolis Tincture 30ml:**

> *"Stock cover is at a critical 1.37 months. Issue an immediate emergency batch order of
> 500 units."*

That product is being discontinued this quarter. The brief says so, and says not to reorder
it above 30 days of cover — it has 42. v1 never mentions the phase-out anywhere in the
document. It recommends buying inventory for a line that is being retired, and it uses the
word *emergency* to do it.

**And the trend section, which the brief asked for by name, has arithmetic errors:**

| | Actual | v1 | |
|---|---|---|---|
| December 2025 | 5,740 | 5,740 | ✓ |
| January 2026 | 6,152 | **6,104** | off by 48 |
| February 2026 | 6,676 | **6,556** | off by 120 |
| March 2026 | 7,180 | 7,180 | ✓ |

The two months it was not given as anchors are the two it got wrong. Nothing on the page
distinguishes them from the two it got right.

**Three more, briefly:**

- **Reorder quantities are round numbers, not calculations.** 2,000 units where the formula
  gives 1,232; 1,200 where it gives 936. No lead time, no target buffer — just plausible
  figures.
- **Bioactive Blends are trended from December**, their partial launch month, inflating the
  growth that drives projected demand and therefore the ranking.
- **The tension the brief explicitly asks for is missed.** v1 labels MGO 100+ 250g
  "HEALTHY — Overstocked" with 6.20 months of cover, notes the 2,000 units inbound in a
  table cell, and recommends nothing. The single most valuable observation in this dataset
  is present as a data point and absent as a decision.

**The point is not that v1 made mistakes.** It is that its mistakes are invisible. Correct
figures and wrong ones are formatted identically, and the one recommendation that would
actually lose money is the most confidently worded sentence in the document. There is no
prompt wording that fixes that — only moving the arithmetic somewhere it can be tested.

That is the argument for everything else in this repository, and it is now an observation
rather than a prediction.

## What has still not been run

**The Anthropic path was not exercised.** `providers.py` implements both; the live run used
Gemini, because that was the key available. Both enforce the schema server-side — Anthropic
through structured outputs, Google through `responseSchema` — but only the Google path has
actually returned a briefing. The Anthropic request shape is written against the documented
API and reviewed, not proven.
