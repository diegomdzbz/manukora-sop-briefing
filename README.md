# Manukora — Monthly S&OP Briefing Automation

Turns four months of SKU-level sales and inventory data into a monthly S&OP briefing an
executive can read in five minutes and act on.

Built as a practical exercise. Part 1 (this build) is below; Part 2 (the Morning Intelligence
Brief architecture) is in [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Status

Work in progress. Sections land as their branches merge — see the commit history.

- [x] Scaffold, mock data, build instructions
- [ ] Calculation engine
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

Full setup, the prompt stack, assumptions and verification notes follow as the build lands.

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
