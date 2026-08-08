# The build-time instruction stack

The brief asks for the instruction stack, and there are two. This is the one that built the
repository; [`v2_final.md`](v2_final.md) is the one that runs every month.

| | Build-time | Run-time |
|---|---|---|
| Instructs | Claude Code, while writing this repo | The model, when generating a briefing |
| Lives in | [`../CLAUDE.md`](../CLAUDE.md) + this file | `v1_baseline.md`, `v2_final.md` |
| Output | Code, tests, documentation | The prose in `output/` |

`CLAUDE.md` is the durable half — it sits at the repo root and constrains anyone, human or
agent, who works here. This file records how the work was actually driven.

---

## How the repo was built

**Plan first, in writing, and audit the plan before writing code.** The design document
went through five review passes before the first line of Python. Each pass used a different
lens, and each found something the previous one could not:

| Pass | Lens | What it caught |
|---|---|---|
| 1 | Against the exercise brief | No section for "what sold well and poorly"; no tradeoffs section; no screenshots |
| 2 | Against the job description | The design had no tool use, no evidence of async communication, no build-time prompt stack |
| 3 | Internal coherence | Verification covered the maths but not the output; docs were batched into one final phase |
| 4 | *Would this actually run?* | **n8n cannot execute the Python** — the container has no interpreter and no access to the host repo. Two paths generated the briefing with nothing saying which was authoritative |
| 5 | Verify the plan's own claims | **Two fabricated figures** — a "22% of total" that was 16.6%, and a "~1,150 units" that was 934 |

Pass 4 is the one worth copying. "Does this satisfy the requirements?" and "would this run?"
are different questions, and only the second finds an arrow in a diagram with nothing
behind it.

Pass 5 is the one that changed the code. Both figures were plausible, and both appeared in
the document proposing a test against exactly that failure. That produced the
no-hand-typed-figures rule in `CLAUDE.md` and `tests/test_output_integrity.py`.

**Build in dependency order, and commit at each boundary.** Rules and validation, then the
engine, then tests, then the narrative layer, then the integrity check. Each phase on its
own branch, merged with a real description. The history is meant to be read.

**Document in the branch that changes the behaviour.** Not in a final pass — a history of
silent code followed by one large documentation dump is the thing this repo is trying not
to be.

**Verify before claiming done.** `pytest` green, `--no-llm` produces a complete briefing
with no key, every figure traces to `facts.json`, no secrets in the diff.

---

## What Claude Code was told, in substance

Beyond `CLAUDE.md`, the instructions that shaped the work:

**On the architecture.** The LLM never does arithmetic. Every number is computed in Python,
covered by a test, and serialised to `facts.json`; the model receives those facts and writes
prose around them. If you find yourself letting the model calculate something — even a
difference between two numbers already in the fact pack — move it into the engine.

**On the brief's rules.** The seven data-context rules are not comments. Each one goes into
`config.py` where a test can assert it, and each gets a test that demonstrates what the
*wrong* reading produces, not just that the right one passes. A test that only confirms
today's output documents nothing.

**On honesty — and on keeping it current.** Say what was not done, then keep saying the
true version as the facts change.

For most of this build there was no API key, so `narrative.py` was written and reviewed but
never executed, and the committed briefing was the deterministic render. That was recorded
plainly rather than smoothed over, because a repo that overstates what it ran is worse than
one that ran less.

Then a key turned up, the narrative layer ran, v1 ran, and both statements stopped being
true — **and the disclaimers did not update themselves.** A later audit found this file
still claiming nothing had been executed, and the README asserting "v1 was never executed"
seventy-seven lines below a section titled *"I ran v1"*. The honesty sections had become the
stale sections, precisely because they were written once and treated as settled.

The lesson is the one this whole repository is built around: a claim nothing checks will
drift. Test what you can — every figure in the briefing traces to a computed fact because a
test says so — and for the prose that cannot be tested, re-read it against reality before
shipping rather than trusting that it aged well.

**On scope.** Deliver what was asked at the scope intended. SQL belongs in Part 2, where a
daily brief genuinely needs a warehouse — not forced into Part 1, where a twelve-row CSV
does not need a database and adding one would be the overbuilding the brief warns against.

---

## What this cost

The exercise was built across a single working session in Claude Code. The expensive part
was not generating code — it was the five review passes and the reasoning about which
design would still be correct in six months. That ratio is the point: the model is fast at
writing the thing and slow to notice that the thing is wrong, so the human-shaped work is
deciding what to check and insisting it gets checked.
