"""`hep bench` against the real binary (P6-S03).

The decision rule is unit-tested in `tests/python/run/test_bench.py`; what has to be checked with a
generator running is that the legs are really measured, that a refused leg is reported as a reason
rather than a crash, and that the whole thing finishes in the time the step asks for.

Marked `slow` and registered as the ctest test `bench`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "utils" / "python"))

CONFIG = REPO / "tests" / "e2e" / "mini.toml"
RUN = REPO / "build" / "bin" / "hep-run"
PLUGIN = REPO / "build" / "analyses" / "PhotoProduction" / "Rivet_photo_eic.so"

#: The step's runtime row. Generous next to the ~15 s it actually takes, so a loaded machine does not
#: fail the suite; it is a ceiling, not a measurement.
BUDGET_S = 120

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)"),
    pytest.mark.skipif(not PLUGIN.is_file(), reason="build the Rivet plugin first"),
]


def hep(*arguments: str, scratch: Path, timeout: int = 600, expect: int = 0):
    done = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(REPO / 'utils' / 'python')!r});"
         f" from hekit.cli import main; raise SystemExit(main({list(arguments)!r}))"],
        cwd=REPO, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
        env=dict(os.environ, HEKIT_RESULTS=str(scratch / "results")))
    done.text = done.stdout.decode("utf-8", errors="replace") + \
        done.stderr.decode("utf-8", errors="replace")
    assert done.returncode == expect, done.text
    return done


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    """One benchmark, as JSON, with its wall clock."""
    scratch = tmp_path_factory.mktemp("bench")
    started = time.monotonic()
    done = hep("bench", str(CONFIG), "--events", "600", "--refresh", "--json", scratch=scratch)
    elapsed = time.monotonic() - started
    return json.loads(done.stdout.decode("utf-8", errors="replace")), elapsed, scratch


def leg(report: dict, name: str) -> dict:
    found = [entry for entry in report["measurements"] if entry["name"] == name]
    assert found, f"no {name} leg in {[entry['name'] for entry in report['measurements']]}"
    return found[0]


# ── the runtime row ──────────────────────────────────────────────────────────

def test_it_finishes_inside_the_budget(report):
    """The step's row: `hep bench` is a thing you run before a run, not instead of one."""
    _, elapsed, _ = report
    assert elapsed < BUDGET_S, f"took {elapsed:.0f}s"


# ── what it measured ─────────────────────────────────────────────────────────

def test_generation_only_is_the_ceiling(report):
    """Nothing can beat generating with no sinks at all, so this leg bounds the others."""
    data, _, _ = report
    generation, serial = leg(data, "generation"), leg(data, "serial")
    assert generation["wall_s"] > 0 and serial["wall_s"] > 0
    assert generation["wall_s"] <= serial["wall_s"], "adding sinks cannot make a run faster"
    assert generation["events"] == serial["events"] == 600


def test_the_sink_share_answers_assumption_a4(report):
    """01 A4 asked whether Rivet's per-event cost is comparable to Pythia's. It is larger."""
    data, _, _ = report
    assert 0.0 < data["sink_share"] < 1.0
    assert data["sink_share"] > 0.4, \
        f"photo_eic runs three jet algorithms; it should dominate (got {data['sink_share']:.2f})"


def test_the_sharded_leg_is_refused_with_its_reason(report):
    """`photo_eic` clusters jets, so there is no sharded number to report — only why (00/B31)."""
    data, _, _ = report
    sharded = leg(data, "sharded")
    assert sharded["refused"], "this build cannot shard a jet analysis"
    assert "jets" in sharded["refused"]
    assert data["mode"] == "serial"
    assert data["reason"] == sharded["refused"], "the recommendation quotes the refusal"


def test_the_replay_leg_reads_back_what_it_wrote(report):
    """"Generate once, analyse many" (11) only pays if reading is cheaper than generating."""
    data, _, _ = report
    replay = leg(data, "replay")
    if replay["refused"]:
        pytest.skip(f"no replay leg here: {replay['refused']}")
    assert replay["events"] == 600, "the replay saw every stored event"
    assert replay["wall_s"] < leg(data, "serial")["wall_s"], "reading beats generating"


# ── the cache ────────────────────────────────────────────────────────────────

def test_the_second_call_is_cached_and_immediate(report):
    """A benchmark is expensive; running it twice by accident should not cost twice."""
    _, _, scratch = report
    started = time.monotonic()
    done = hep("bench", str(CONFIG), "--events", "600", scratch=scratch)
    elapsed = time.monotonic() - started
    assert "cached" in done.text
    assert elapsed < 20, f"a cached report took {elapsed:.0f}s"


def test_nothing_was_written_into_results(report):
    """A benchmark is not a result (09 §3): it belongs in scratch and nowhere else."""
    _, _, scratch = report
    results = scratch / "results"
    leftovers = [path for path in results.rglob("*") if path.is_file()] if results.is_dir() else []
    assert not leftovers, leftovers[:5]
