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
