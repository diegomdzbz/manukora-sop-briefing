"""The five-minute reading budget, and the one way to override it.

The budget was advisory for most of this project — over-length was printed and shipped.
It is a stated requirement, so it now fails the run. But some models will not come in under
the ceiling on this document, and a flagship path that only ever errors is a dead end.

`--allow-over-budget` is the way out: it has to be typed, its name says what typing it
means, and it does not move the ceiling for anyone else. These tests hold that shape.

No network and no API key: the provider is injected.
"""

from __future__ import annotations

import pytest

from src import config
from src.narrative import OverReadingBudget, write_prose
from src.render import compose_briefing, prose_word_count, template_prose


class StubProvider:
    """A model that writes a fixed number of extra words, and counts its calls."""

    class info:  # noqa: N801 - mirrors the shape of a real provider
        label = "Stub model"

    def __init__(self, facts: dict, padding_words: int, padding_on_retry: int | None = None):
        self._facts = facts
        self._padding = padding_words
        self._retry_padding = padding_on_retry if padding_on_retry is not None else padding_words
        self.calls = 0

    def generate(self, system: str, user: str, schema: dict) -> dict:
        self.calls += 1
        pad = self._padding if self.calls == 1 else self._retry_padding
        prose = template_prose(self._facts)
        prose["capital_note"] = prose["capital_note"] + " padding" * pad
        return prose


def _padding_to_exceed(facts: dict, by: int) -> int:
    """How many filler words push the rendered briefing `by` words past the ceiling."""
    baseline = prose_word_count(compose_briefing(facts, template_prose(facts)))
    return config.MAX_BRIEFING_WORDS - baseline + by


# --------------------------------------------------------------------------------------


def test_an_over_length_briefing_fails_the_run_by_default(facts):
    """The ceiling is a requirement, so missing it is a failure, not a warning."""
    provider = StubProvider(facts, _padding_to_exceed(facts, by=40))

    with pytest.raises(OverReadingBudget) as exc:
        write_prose(facts, provider=provider)

    assert exc.value.written > config.MAX_BRIEFING_WORDS
    assert exc.value.ceiling == config.MAX_BRIEFING_WORDS
    # The message has to point somewhere useful, or the failure is just a wall.
    assert "--allow-over-budget" in str(exc.value)
    assert "--no-llm" in str(exc.value)


def test_the_override_ships_it(facts):
    """Explicitly asking for the long briefing gets the long briefing."""
    provider = StubProvider(facts, _padding_to_exceed(facts, by=40))

    prose, label = write_prose(facts, provider=provider, allow_over_budget=True)

    assert label == "Stub model"
    assert prose_word_count(compose_briefing(facts, prose)) > config.MAX_BRIEFING_WORDS


def test_the_override_does_not_skip_the_retry(facts):
    """Willing to ship a long briefing is not the same as not wanting a shorter one.

    The rewrite still runs with the override set, because the shorter briefing is the
    better briefing even when the caller would have accepted either.
    """
    provider = StubProvider(facts, _padding_to_exceed(facts, by=40))
    write_prose(facts, provider=provider, allow_over_budget=True)
    assert provider.calls == 2


def test_a_retry_that_comes_in_under_is_accepted_without_the_override(facts):
    """The retry is not ceremony: a model that takes the correction is shipped."""
    provider = StubProvider(
        facts,
        padding_words=_padding_to_exceed(facts, by=40),
        padding_on_retry=0,
    )

    prose, _ = write_prose(facts, provider=provider)

    assert provider.calls == 2
    assert prose_word_count(compose_briefing(facts, prose)) <= config.MAX_BRIEFING_WORDS


def test_a_briefing_inside_the_budget_is_not_retried(facts):
    """No second call when the first one fits — the retry costs money."""
    provider = StubProvider(facts, padding_words=0)

    write_prose(facts, provider=provider)

    assert provider.calls == 1


def test_the_override_cannot_wave_through_anything_else(facts):
    """`--allow-over-budget` is about length, not about correctness.

    A briefing that drops a reorder recommendation is rejected either way — otherwise the
    flag would quietly become "ship whatever came back".
    """
    from src.schema import BriefingContractError

    class DropsARecommendation(StubProvider):
        def generate(self, system, user, schema):
            prose = super().generate(system, user, schema)
            prose["reorder_rationales"] = prose["reorder_rationales"][:-1]
            return prose

    with pytest.raises(BriefingContractError):
        write_prose(facts, provider=DropsARecommendation(facts, 0), allow_over_budget=True)


def test_the_cli_exposes_the_flag():
    """A capability nobody can find is not a capability."""
    from src.main import _parse_args

    assert _parse_args(["--no-llm"]).allow_over_budget is False
    assert _parse_args(["--allow-over-budget"]).allow_over_budget is True
