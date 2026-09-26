"""hekit tests: every test gets its own results tree, so nothing can land in the real one."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def redirect_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`HEKIT_RESULTS` -> tmp_path for the duration of the test."""
    results = tmp_path / "results"
    results.mkdir()
    monkeypatch.setenv("HEKIT_RESULTS", str(results))
    return results
