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

## What has not been run

**v1 was never executed against the live API, and neither was v2.** No Anthropic API key
was available while building this, so `narrative.py` is written and reviewed but not
exercised end to end, and the committed briefing in `output/` is the deterministic
`--no-llm` render.

The v1 critique above is therefore reasoning about the design, not a transcript of a
recorded A/B run — and it is labelled that way rather than dressed up as one. The failures
in "Where the AI was wrong" are real and observable in this repo's git history; the v1-run
comparison is not. Given a key, the first thing to do is generate the model-written
briefing and diff its figures against the template render — a check
`test_output_integrity.py` already implements.
