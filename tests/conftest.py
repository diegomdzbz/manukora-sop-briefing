"""Shared fixtures.

The dataset is loaded once and the fact pack built once; every test reads the same objects,
so a change in the engine shows up everywhere at once rather than in one lucky assertion.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.engine import build_facts
from src.loader import load

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET = REPO_ROOT / "data" / "mock_sales.csv"


@pytest.fixture(scope="session")
def records():
    return load(DATASET)


@pytest.fixture(scope="session")
def facts(records):
    return build_facts(records)


@pytest.fixture(scope="session")
def by_sku(facts):
    """Fact pack entries keyed by SKU, for readable assertions."""
    return {s["sku"]: s for s in facts["skus"]}


@pytest.fixture(scope="session")
def collected_test_count(request):
    """How many tests this run collected — or a skip, when the run was only a subset.

    The documentation quotes the size of the suite, and that figure is the one number here
    that no fact pack can source. It was accurate when it was written and stopped being
    accurate three commits later, when two changes each added tests and neither touched the
    README — which is how this kind of figure always fails.

    A partial run cannot judge the total, so it says so rather than failing — a check that
    fires on `pytest tests/test_engine.py` would be noise, and noisy checks get deleted.
    """
    collected = {item.path.name for item in request.session.items}
    missing = {path.name for path in Path(__file__).parent.glob("test_*.py")} - collected
    if missing:
        pytest.skip("partial run; suite size needs " + ", ".join(sorted(missing)))
    return len(request.session.items)
