"""Test-safety: nothing under tests/ may write into results/ or configs/ (00/B18).

Applies to every test directory, not just tests/python, because the legacy golden fixtures drive the old
tools and those resolve paths against the current directory. Each test is checked, so a failure names the
test that wrote. A test that needs a results tree sets `HEKIT_RESULTS` (tests/python/conftest.py does).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import guard

@pytest.fixture(autouse=True)
def _no_writes_to_protected_trees() -> object:
    """Fail the test that changed anything under results/ or configs/."""
    roots = tuple(guard.REPO / name for name in guard.PROTECTED)
    before = guard.snapshot(roots)
    yield
    found = guard.changes(before, guard.snapshot(roots))
    if found:
        raise AssertionError(
            "this test wrote into a protected tree (use output/scratch/ or HEKIT_RESULTS):\n  "
            + "\n  ".join(found))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return guard.REPO


@pytest.fixture
def scratch_dir(tmp_path: Path) -> Path:
    """A writable directory that is never inside the repository."""
    assert guard.REPO not in tmp_path.parents
    return tmp_path
