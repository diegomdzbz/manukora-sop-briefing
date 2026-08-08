# Runbook

What breaks, how to tell, and what to do about it. Written for whoever inherits this
without having built it.

**First thing to know:** the engine, the tests and the briefing all run with no API key and
no network. If something is broken, `python -m src.main --no-llm` still works and is the
fastest way to isolate whether the problem is in the data, the engine, or the model.

---

## The monthly run

```bash
python -m src.main --no-llm     # briefing from the template, no key needed
python -m src.main              # briefing written by the model
python -m src.main --facts-only # fact pack only; used by the n8n workflow
```

Output lands in `output/`. Commit it — CI fails if the committed briefing drifts from what
the code produces.

---

## Failures, in the order you will meet them

### `Dataset rejected: ...`

The loader refused the input. The message names the line and the column. Causes, in order
of likelihood:

| Message contains | What happened | Fix |
|---|---|---|
| `is missing columns` | Column renamed or dropped upstream | Restore the header, or update `REQUIRED_COLUMNS` in `loader.py` |
| `is not a whole number` | A blank, a thousands separator, or `N/A` in a count | Clean the export; the loader will not guess |
| `no units sold in <month>` | A SKU with zero sales in the reporting month | Cover and revenue cannot be derived from a zero baseline. Remove the SKU or confirm it should be there |
| `target cover is X but the brief requires Y` | The dataset disagrees with a rule in `config.py` | **Do not "fix" this by editing config to match.** Find out which is right first — this check exists because a quiet change here produces a plausible wrong answer |

### `Narrative layer failed: ANTHROPIC_API_KEY is not set`

Expected without a key. Use `--no-llm`, or copy `.env.example` to `.env` and fill it in.

### `Narrative layer failed: Claude API returned 429`

Rate limited. The SDK already retries with backoff; a 429 reaching you means the retries
were exhausted. Wait and re-run, or use `--no-llm` — the briefing is not time-critical to
the minute.

### `Narrative layer failed: Response hit the 16000 token ceiling`

The response was cut off mid-briefing. Either raise `MAX_TOKENS` in `narrative.py` or lower
`EFFORT` — thinking and response text share that budget. Do not ship a truncated briefing.

### `BriefingContractError: reorder rationales do not match the queue`

The model returned a well-formed briefing that is about the wrong SKUs — it dropped a
recommendation or invented one. The run fails rather than shipping a briefing with a
missing recommendation. Re-run; if it repeats, the fact pack and the prompt have drifted
apart and `v2_final.md` needs updating.

### `test_no_unsourced_figures_in_the_template_briefing` fails

**The important one.** A figure in the briefing has no source in the fact pack. The failure
names the figure and the line it appeared in.

Almost always one of two things: someone typed a number into prose by hand (see the rule in
`CLAUDE.md` — this is exactly what it forbids), or a renderer started computing instead of
formatting. Move the computation into `engine.py` and read it back.

Do not fix this by loosening the check.

---

## Changing a business rule

All of them live in `src/config.py`, tagged `BRIEF` (stated in the exercise, not
negotiable) or `ASSUMPTION` (my choice — see `OPEN-QUESTIONS.md`).

To change one: edit `config.py`, run `pytest`, and read what fails. The business-rule tests
are written to fail loudly on exactly these changes, so a red suite here is the system
working. Update the test alongside the rule, in the same commit, with the reason.

Common cases:

- **Supplier lead time changed** → `DEFAULT_LEAD_TIME_MONTHS` / `LEAD_TIME_OVERRIDES`.
  Expect every reorder quantity and date to move.
- **A SKU gets a different cover target** → `TARGET_COVER_OVERRIDES`, *and* the dataset
  column. The loader cross-checks them and will refuse to run if they disagree.
- **A new SKU is phased out** → add it to `PHASE_OUT_SKUS` with its floor.
- **A new product line launches mid-period** → add it to `TREND_BASELINE_OVERRIDES` so its
  partial first month does not inflate its growth.

---

## The n8n workflow

`docker compose up` starts two services: `engine` (the Python `/facts` endpoint) and `n8n`.
n8n calls the engine over the internal network — it cannot run the Python itself, which is
why they are separate containers.

| Symptom | Cause | Fix |
|---|---|---|
| n8n node fails with `ECONNREFUSED` | Engine container not up yet | `docker compose ps`; the engine has a healthcheck, wait for it |
| Workflow runs, no Slack message | `SLACK_WEBHOOK_URL` unset | Expected. The workflow writes the briefing to disk instead; the Slack node is present but disabled |
| Changes to `src/` not reflected | Container running an old image | `docker compose up --build` |

---

## Rotating the API key

The key lives only in `.env`, which is gitignored. Replace the value and re-run — nothing
caches it. If a key is ever committed by accident, treat it as public: revoke it at
`console.anthropic.com` first, then clean the history. Revoke before you rewrite; a
rewritten history does not un-leak anything already pushed.
