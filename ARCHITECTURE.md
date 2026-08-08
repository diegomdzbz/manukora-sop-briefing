# Part 2 — Morning Intelligence Brief

A daily message answering four questions: what changed overnight, what needs a decision
today, what is trending the wrong way, and what looks important but is not.

## What I would build

Three items. Never four. A short narrative in a Slack DM, no dashboard, no attachments.

The architecture is the one Part 1 already proves. A deterministic layer decides *what is
worth saying*; a model decides *how to say it*. The model receives a fact pack and writes
prose, and the same integrity check applies — a figure in the brief that no query produced
fails the build. Detection is too consequential to delegate to a language model, and prose
is too tedious to hand-write.

**Nightly, around 02:00 NZ:** ingest Shopify (Admin GraphQL), Amazon Seller Central
(SP-API Orders + FBA Inventory), and Klaviyo (campaign and flow metrics) into BigQuery as
dated snapshot tables — one row per SKU per source per day, append-only. Snapshots rather
than live queries are what make "what changed overnight" a `LAG()` instead of a
recomputation, and they give a real history to compare against.

**Detection** is a set of named SQL detectors, each emitting candidates with a magnitude, a
direction, and a z-score against the trailing 28 days: revenue and conversion deltas,
stock cover crossing the reorder point, refund and return spikes, review-rating drops,
campaign performance breaks, and Amazon Buy Box loss. A candidate is surfaced only if it
clears two bars: statistically unusual (|z| > 2) **and** actionable today. "Revenue is down
4%" is neither. "MGO 514+ 500g crosses its reorder point on Thursday and the supplier
needs six weeks" is both.

**Ranking** orders survivors by revenue at stake, exactly as the monthly briefing does.
The top three go to Claude with the ranked fact pack; the rest are logged, not sent.

**Delivery** is a Slack DM. The same payload posts to a private channel for the ops team,
so the exec's brief and the team's context stay in sync.

## The timing problem

The exec may be in Auckland, Los Angeles, or in transit. A fixed 6am NZ send is wrong most
of the time, and inferring their location would be both creepy and unreliable.

**So infer nothing.** Slack already knows: `users.info` returns a `tz` field the user sets
themselves and updates when they travel. Send at 07:00 in their declared local time.
Zero tracking, zero extra infrastructure, and it is already correct the day they land.

Around that: a `/brief` slash command for on-demand delivery; a fallback to 06:00 NZ if
`tz` is empty; a guard against sending twice in one local calendar day when the timezone
shifts mid-flight; and weekend suppression unless something genuinely cannot wait.

## Stack and cost

Assumes one daily run, three recipients, ~40 SKUs across three sources.

| Component | Choice | Monthly |
|---|---|---|
| Orchestration | n8n (self-hosted, the Part 1 container) | ~$20 infra |
| Warehouse | BigQuery — small tables, mostly free tier | <$5 |
| Narrative | Claude, ~15K input + ~800 output per run | ~$3 |
| Sources | Shopify, SP-API, Klaviyo — no per-call cost | $0 |
| Delivery | Slack | $0 |

**Under $30 a month.** The model is the cheapest line, which is the point: the expensive
work is deterministic, so it is not being paid for by the token.

## Failure modes

**Stale data is the dangerous one.** SP-API reporting lags 24–48 hours, and a brief that
silently reports on partial data is worse than no brief. Every source carries a freshness
timestamp; if one is stale, the brief opens by saying which, and the affected detectors are
suppressed rather than run on old numbers.

**Silence must be explicit.** A missing message is ambiguous — nothing happened, or the
job died? On a quiet day it sends "nothing needs you today", with the checks that ran. A
heartbeat that never goes quiet is a heartbeat you can trust.

**Model unavailable** falls back to the deterministic template render, exactly as `--no-llm`
does today. The brief still goes out; only the prose is plainer.

## Keeping it useful

The failure mode of every daily digest is becoming wallpaper. Three defences:

**A hard cap of three.** Scarcity forces ranking, and ranking is the product.

**Every item names a decision.** If a detector cannot say what to do about its finding, the
detector is wrong and gets cut, not the threshold.

**Suppression with escalation.** An item does not repeat within seven days unless it has
materially worsened — otherwise the same stockout warning trains the reader to skim.

And a monthly review of which items were acted on. A detector that has never once produced
an action in eight weeks is noise with good intentions, and should be deleted.
