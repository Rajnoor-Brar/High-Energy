"""Test setup shared by every suite.

* The runner package is importable as `runner` (utils/Env on sys.path).
* Tests never write into results/ or configs/. HEKIT_RESULTS and HEKIT_OUTPUT point into
  output/tests/, and a session guard fails the run if anything under results/ or configs/ changed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "utils" / "Env"))

SCRATCH = REPO / "output" / "tests"
os.environ.setdefault("HEKIT_RESULTS", str(SCRATCH / "results"))
os.environ.setdefault("HEKIT_OUTPUT", str(SCRATCH / "output"))


def _snapshot() -> dict[str, float]:
    seen: dict[str, float] = {}
    for top in (REPO / "results", REPO / "configs"):
        if top.is_dir():
            for path in top.rglob("*"):
                seen[str(path)] = path.stat().st_mtime if path.exists() else 0.0
    return seen


@pytest.fixture(scope="session", autouse=True)
def results_and_configs_untouched():
    before = _snapshot()
    yield
    after = _snapshot()
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    assert not changed, "tests wrote into results/ or configs/:\n  " + "\n  ".join(changed[:20])


@pytest.fixture
def scratch(tmp_path_factory) -> Path:
    """A fresh directory under output/tests/ for one test."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return Path(tmp_path_factory.mktemp("t", numbered=True))
