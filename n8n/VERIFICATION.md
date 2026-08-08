# n8n stack — verification

![The workflow on the n8n canvas](canvas.png)

Nine nodes. The schedule fans out to two HTTP calls — one for the fact pack, one for the
prompt — which merge before the agent writes. **Post to Slack** is greyed out because it is
deliberately deactivated (see the bottom of this file), and the warning on the **Claude**
node is a missing credential: the repository ships no keys, so a freshly imported workflow
is expected to look exactly like this until you add your own.

---


The two-service design in `docker-compose.yml` rests on a claim: **n8n cannot execute this
project's Python.** That claim is load-bearing — if it were wrong, the whole compose stack
would be unnecessary complexity.

So it was checked rather than assumed. Transcript below, run against the live stack.

```
$ docker compose up -d --build
 Container manukora-engine  Healthy
 Container manukora-n8n     Started

$ docker compose ps
NAME              STATUS                   PORTS
manukora-engine   Up 2 minutes (healthy)   0.0.0.0:8000->8000/tcp
manukora-n8n      Up 12 seconds            0.0.0.0:5678->5678/tcp
```

**1. Does the n8n container have a Python interpreter?**

```
$ docker exec manukora-n8n sh -c 'command -v python3 || command -v python || echo NONE'
NONE
```

No. This is the reason the engine is a separate service.

**2. Can it see the repository on the host?**

```
$ docker exec manukora-n8n sh -c 'ls /app/src || echo ABSENT'
ABSENT
```

No. Mounting the source in would not help either — there is nothing to run it with.

**3. Can it reach the engine over the internal network?**

```
$ docker exec manukora-n8n sh -c 'wget -qO- http://engine:8000/health'
{"status":"ok","skus":12}
```

Yes. This is the connection the workflow actually uses.

**4. Does the fact pack arrive intact?**

```
$ docker exec manukora-n8n sh -c 'wget -qO- http://engine:8000/facts'
March 2026: 7,180 units, reorder queue of 6 SKUs
first recommendation: Manuka Honey MGO 263+ 500g — 1,232 units
```

Yes, and the figures match what the CLI produces from the same dataset.

**5. Does `/prompt` serve the versioned file, or a copy?**

The workflow fetches the prompt rather than carrying it in a node parameter, so that the
CLI and the workflow cannot drift onto different instructions. Verified byte-for-byte
against `prompts/v2_final.md`:

```
GET /prompt -> 200  source=prompts/v2_final.md  prompt=3277 chars  schema=8 fields
/prompt serves the versioned file unmodified: YES
```

---

## 6. Does the workflow actually produce a briefing?

The checks above prove the plumbing. This proves the product.

```
$ docker compose run --rm --no-deps --entrypoint sh n8n \
    -c 'n8n execute --id wJK3eczmf4YlhOzw'

  "mode": "cli",
  "startedAt": "2026-08-08T03:03:45.008Z",
  "stoppedAt":  "2026-08-08T03:04:05.096Z",
  "status": "success",
  "finished": true
```

Twenty seconds, all eleven nodes, no manual steps. It wrote
[`output/sop_briefing_from_n8n.md`](../output/sop_briefing_from_n8n.md) — committed, and
held to exactly the same standard as the CLI output:

| | |
|---|---|
| Figures with no source in the fact pack | none |
| Prose length | 754 words, inside the reading budget |
| Cents quoted in prose | none |
| Leads with the engine's top-ranked tension | yes |
| Reorder rationales | 6 of 6 |

`tests/test_output_integrity.py` checks this file alongside the others, so the workflow's
output cannot quietly drift from the guarantees the CLI's output is held to.

### Three things this run found that reading the config would not

**`GEMINI_API_KEY` never reached the container.** `docker-compose.yml` forwarded
`ANTHROPIC_API_KEY` and `SLACK_WEBHOOK_URL` and not the key the project actually uses. The
model node would have failed on the first scheduled run, months from now, with nobody
watching.

**n8n blocks `$env` in expressions by default.** Even once the key was present, the
expression could not read it without `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`.

**n8n blocks filesystem writes by default.** The run got all the way through the model call
and the assembly, then failed on the last node. Fixed with
`N8N_RESTRICT_FILE_ACCESS_TO=/data/output` — scoped to the one mounted directory rather
than opened up wholesale.

Each is a one-line config fix and each would have been a silent failure in production.

### And n8n confirmed the architecture in its own logs

While starting the execution:

```
Failed to start Python task runner ... because Python 3 is missing from this system
```

That is the container saying, unprompted, why the engine has to be a separate service.

---

## Running it yourself

```bash
docker compose up -d --build          # engine waits for healthy before n8n starts
open http://localhost:5678            # n8n
open http://localhost:8000/docs       # the engine's OpenAPI page
```

Then in n8n: **Workflows → Import from File → `n8n/workflow.json`**. Add an Anthropic or
Google credential to the model node and run it.

## What is not demonstrated

The **Slack node is wired and disabled**. No Slack workspace was available for this
exercise, so the delivery shown is the file write to `/data/output`, mounted to `./output`
on the host. Setting `SLACK_WEBHOOK_URL` and enabling the node switches delivery on;
nothing else changes.

Wiring it and leaving it off is honest. Screenshotting a posted message that never posted
would not be.
