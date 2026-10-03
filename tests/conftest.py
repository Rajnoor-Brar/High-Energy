"""Test setup shared by every suite.

* The runner package is importable as `runner` (utils/Env on sys.path), and tests/ is on sys.path for
  `support` (the shared helpers).
* Tests read and write only their own places, whatever the shell has set: HEKIT_RESULTS and HEKIT_OUTPUT
  point into output/tests/, and HEKIT_CONFIGS to tests/fixtures/configs (frozen copies), so a test
  never reads the user's configs/ and fails only when the code changed.
* The basetemp is output/tests/pytest from the repository, wherever pytest is started.
* The session guard: tests/fixtures and tests/reference must come out byte for byte as they went in
  (a failure). results/, configs/ and modules/ are the user's, who may edit them while tests run, so a
  change there is reported at the end (a test escaping HEKIT_* would show up there), not failed.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "utils" / "Env"))

SCRATCH = REPO / "output" / "tests"
FIXTURES = REPO / "tests" / "fixtures" / "configs"
os.environ["HEKIT_RESULTS"] = str(SCRATCH / "results")
os.environ["HEKIT_OUTPUT"] = str(SCRATCH / "output")
os.environ["HEKIT_CONFIGS"] = str(FIXTURES)

OURS = (REPO / "tests" / "fixtures", REPO / "tests" / "reference")         # must not change: content hashes
THEIRS = (REPO / "results", REPO / "configs", REPO / "modules")           # the user's: reported, by stat

_report: list[str] = []


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    if not config.option.basetemp:                       # before the tmp_path factory reads it
        config.option.basetemp = str(SCRATCH / "pytest")


def _hashes(tops) -> dict[str, str]:
    seen = {}
    for top in tops:
        for path in sorted(top.rglob("*")) if top.is_dir() else ():
            if path.is_file() and "__pycache__" not in path.parts:
                seen[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return seen


def _stats(tops) -> dict[str, tuple]:
    seen = {}
    for top in tops:
        for path in top.rglob("*") if top.is_dir() else ():
            try:
                info = path.stat()
            except FileNotFoundError:
                continue
            seen[str(path)] = (info.st_size, info.st_mtime_ns)
    return seen


def _changed(before: dict, after: dict) -> list[str]:
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


@pytest.fixture(scope="session", autouse=True)
def the_repository_is_left_alone():
    ours, theirs = _hashes(OURS), _stats(THEIRS)
    yield
    _report.extend(_changed(theirs, _stats(THEIRS)))
    changed = _changed(ours, _hashes(OURS))
    assert not changed, "tests changed their fixtures or reference data:\n  " + "\n  ".join(changed[:20])


def pytest_terminal_summary(terminalreporter):
    if _report:
        terminalreporter.write_sep("-", "changed under results/, configs/ or modules/ during the session")
        terminalreporter.write_line("(your own edits, or a test that escaped HEKIT_*: check any you did not make)")
        for path in _report[:20]:
            terminalreporter.write_line(f"  {path}")
        if len(_report) > 20:
            terminalreporter.write_line(f"  … and {len(_report) - 20} more")


@pytest.fixture
def scratch(tmp_path_factory) -> Path:
    """A fresh directory under the basetemp (output/tests/pytest/) for one test."""
    return Path(tmp_path_factory.mktemp("t", numbered=True))
