# n8n stack — verification

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
