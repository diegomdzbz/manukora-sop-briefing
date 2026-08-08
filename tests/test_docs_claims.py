"""Figures the documentation states about this repo must be true of this repo.

`test_output_integrity.py` holds the briefing to its fact pack. This holds the docs to the
one figure they state about the project rather than about Manukora: how many tests there
are. No fact pack can source it, so it is the only number in the documentation that could
drift without anything noticing — and it did. It was right when it was written, and stopped
being right three commits later when two unrelated changes each added tests. Nothing failed,
because nothing was looking.

The rule in `CLAUDE.md` is that no figure is hand-typed. A test count cannot be read off
`facts.json`, so the alternative is to check it: any count the docs give is compared against
the suite that actually ran. A number in the docs is read as a claim about the whole suite —
if a doc ever needs to count the tests in one file, it has to say so in words.

The check has no sense of tense, and that is deliberate. Writing the README paragraph that
introduces this file tripped it, because the sentence narrated the old count in the present
form `54 tests`. Teaching it to recognise history would mean guessing at prose; the simpler
rule is that documentation describes drift without reprinting the stale figure, which reads
better anyway. A reader scanning for how big the suite is should never meet a number that
was true once.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# `.claude` holds worktrees, which contain full copies of this repo — scanning them would
# check other branches' documentation against this branch's suite.
SKIP_DIRS = {".git", ".claude", ".pytest_cache", "node_modules"}

SUITE_SIZE_CLAIM = re.compile(r"\b(\d[\d,]*)\s+tests\b")


def _documentation() -> list[Path]:
    return sorted(
        path
        for path in REPO_ROOT.rglob("*.md")
        if not SKIP_DIRS.intersection(path.relative_to(REPO_ROOT).parts)
    )


def _stale_claims(count: int) -> list[str]:
    problems = []
    for doc in _documentation():
        lines = doc.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            for claimed in SUITE_SIZE_CLAIM.findall(line):
                if int(claimed.replace(",", "")) != count:
                    relative = doc.relative_to(REPO_ROOT).as_posix()
                    problems.append(f"{relative}:{lineno} claims {claimed}: {line.strip()}")
    return problems


def test_documented_suite_size_is_current(collected_test_count):
    problems = _stale_claims(collected_test_count)
    assert not problems, (
        f"the suite has {collected_test_count} tests, but the docs say otherwise:\n"
        + "\n".join(f"  {problem}" for problem in problems)
    )


def test_the_check_catches_a_stale_count(collected_test_count):
    """A test that cannot fail proves nothing — the same reasoning as the integrity check.

    Confirm the claim is really being read, rather than the pattern quietly matching
    nothing and the assertion passing on an empty list.
    """
    assert SUITE_SIZE_CLAIM.findall(f"python -m pytest -q     # {collected_test_count} tests")
    assert not _stale_claims(collected_test_count)
    assert _stale_claims(collected_test_count + 1), "a wrong count passed the check"


def test_the_check_ignores_prose_that_counts_no_tests(collected_test_count):
    """`one test per rule` and similar phrasing must not be read as a figure."""
    assert not SUITE_SIZE_CLAIM.findall("one test per rule the brief states")
    assert not SUITE_SIZE_CLAIM.findall("each rule has tests that fail on the wrong reading")
