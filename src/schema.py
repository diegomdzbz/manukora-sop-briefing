"""The contract the narrative layer must satisfy.

The model is constrained to this schema via structured outputs, so it cannot return a
briefing that is missing the tension section, or a reorder recommendation without a
rationale. Validation happens at the API layer — a response that does not fit the shape is
retried by the model rather than parsed hopefully on our side.

Note what is *not* here: numbers. Every figure in the finished briefing comes from
`facts.json` and is rendered by `render.py`. The model supplies prose and nothing else.
That is the whole reason the output can be checked — see `tests/test_output_integrity.py`.
"""

from __future__ import annotations

BRIEFING_SCHEMA = {
    "type": "object",
    "properties": {
        "opening_line": {
            "type": "string",
            "description": (
                "One sentence an executive reads first. States how the month went overall. "
                "No preamble, no 'this briefing covers'."
            ),
        },
        "headline": {
            "type": "object",
            "description": "The single decision that most deserves attention this month.",
            "properties": {
                "sku": {"type": "string", "description": "Exact SKU name from the fact pack."},
                "decision": {
                    "type": "string",
                    "description": "The action to take, stated as an instruction, not an option.",
                },
                "reasoning": {
                    "type": "string",
                    "description": (
                        "Two or three sentences of business reasoning. Why this is the call, "
                        "and what it costs to get it wrong."
                    ),
                },
            },
            "required": ["sku", "decision", "reasoning"],
            "additionalProperties": False,
        },
        "capital_note": {
            "type": "string",
            "description": (
                "One short paragraph on where working capital is committed versus where demand "
                "actually is."
            ),
        },
        "reorder_rationales": {
            "type": "array",
            "description": (
                "One entry per SKU in the reorder queue, in the same order. Every SKU in the "
                "queue must appear exactly once."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "rationale": {
                        "type": "string",
                        "description": (
                            "Why this SKU sits where it does in the ranking, and what happens "
                            "if the order is not placed. One to three sentences."
                        ),
                    },
                },
                "required": ["sku", "rationale"],
                "additionalProperties": False,
            },
        },
        "performance_note": {
            "type": "string",
            "description": (
                "What sold well and what sold poorly. If nothing declined outright, say so "
                "plainly rather than implying a fall that did not happen."
            ),
        },
        "tension_notes": {
            "type": "array",
            "description": (
                "One entry per tension in the fact pack, in the same order. These are the cases "
                "where the obvious reading of the data and the right decision disagree."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "note": {
                        "type": "string",
                        "description": "The conflict and how to resolve it, in one or two sentences.",
                    },
                },
                "required": ["sku", "note"],
                "additionalProperties": False,
            },
        },
        "noise_note": {
            "type": "string",
            "description": (
                "What looks like a story in this data and is not, and why it can be set aside. "
                "Empty string if the fact pack lists nothing under noise."
            ),
        },
        "closing_action": {
            "type": "string",
            "description": "What should happen before the next review. One or two sentences.",
        },
    },
    "required": [
        "opening_line",
        "headline",
        "capital_note",
        "reorder_rationales",
        "performance_note",
        "tension_notes",
        "noise_note",
        "closing_action",
    ],
    "additionalProperties": False,
}


class BriefingContractError(ValueError):
    """The model's response fit the schema but not the fact pack it was given."""


def check_against_facts(prose: dict, facts: dict) -> None:
    """Verify the model covered every SKU it was asked to cover.

    The schema guarantees the *shape* — that `reorder_rationales` is a list of objects with
    a `sku` and a `rationale`. It cannot guarantee the model wrote a rationale for every SKU
    in the queue, or that it did not invent one. That is what this checks.
    """
    expected_queue = [r["sku"] for r in facts["reorder_queue"]]
    got_queue = [r["sku"] for r in prose["reorder_rationales"]]
    if got_queue != expected_queue:
        raise BriefingContractError(
            "reorder rationales do not match the queue.\n"
            f"  expected: {expected_queue}\n"
            f"  received: {got_queue}"
        )

    expected_tensions = [t["sku"] for t in facts["tensions"]]
    got_tensions = [t["sku"] for t in prose["tension_notes"]]
    if got_tensions != expected_tensions:
        raise BriefingContractError(
            "tension notes do not match the fact pack.\n"
            f"  expected: {expected_tensions}\n"
            f"  received: {got_tensions}"
        )

    if facts["noise"] and not prose["noise_note"].strip():
        raise BriefingContractError(
            "the fact pack flags something as noise but the briefing says nothing about it"
        )

    # A SKU with stock already on the water that still lands short is the most important
    # thing about that SKU, and the easiest fact to leave out — the cover figure alone
    # reads like an ordinary shortfall. On the first live run the model wrote a generic
    # rationale for MGO 1700+ and dropped the inbound order entirely, which made the
    # briefing quieter than the analysis behind it.
    rationales = {r["sku"]: r["rationale"] for r in prose["reorder_rationales"]}
    for row in facts["reorder_queue"]:
        sku = next(s for s in facts["skus"] if s["sku"] == row["sku"])
        if not sku["inventory"]["has_order_placed"]:
            continue
        text = rationales[row["sku"]].lower()
        units = f"{sku['inventory']['units_on_order']:,}"
        mentions_inbound = str(units) in text or any(
            phrase in text for phrase in ("inbound", "in flight", "on order", "already ordered")
        )
        if not mentions_inbound:
            raise BriefingContractError(
                f"{row['sku']} has {units} units already inbound that still leave it short "
                f"of target, and the rationale does not mention them. That is the finding "
                f"for this SKU, not the cover figure."
            )

    # The engine decides what leads, not the model. On the first live run the model chose
    # the most urgent reorder as its headline instead of the hardest decision — a
    # defensible read, but it belongs to the ranking layer. The prompt says so and this
    # enforces it.
    if facts["tensions"]:
        expected = facts["tensions"][0]["sku"]
        if prose["headline"]["sku"] != expected:
            raise BriefingContractError(
                f"headline should lead with {expected!r} (the first tension, ranked by how "
                f"hard the decision is) but leads with {prose['headline']['sku']!r}"
            )
