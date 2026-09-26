"""The rule `hep bench` applies to its measurements (P6-S03, 05 §3).

The measuring is slow and lives in `tests/integration/test_bench.py`; the *decision* is a pure
function of three timings, so it is checked here, instantly, including the cases a real machine would
be awkward to produce on demand — a sharded leg that was refused, one that is marginally faster, and
analyzers so cheap there is nothing to parallelise.

The order of the questions is the part worth pinning: "is it allowed?" before "is it faster?". A
sharded run of an analysis that clusters jets is not a faster run, it is a wrong one (00/B31).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "utils" / "python"))

from hekit.run import bench


def measurement(name: str, wall: float = 0.0, *, refused: str = "", mode: str = "",
                events: int = 1000) -> bench.Measurement:
    return bench.Measurement(name=name, wall_s=wall, refused=refused, mode=mode or name,
                             events=events)


# ── the table ────────────────────────────────────────────────────────────────

def test_a_refused_sharded_leg_recommends_serial_and_says_why():
    """The real case on this machine: the reason is the answer, and it is passed through intact."""
    reason = "photo_eic clusters jets, which cannot be done from several threads"
    mode, why = bench.recommend(measurement("generation", 1.0), measurement("serial", 4.0),
                                measurement("sharded", refused=reason))
    assert mode == "serial"
    assert why == reason, "the refusal is quoted, not summarised into 'it did not work'"


def test_a_clearly_faster_sharded_leg_recommends_sharded():
    mode, why = bench.recommend(measurement("generation", 1.0), measurement("serial", 4.0),
                                measurement("sharded", 2.0))
    assert mode == "sharded"
    assert "2.00x" in why


def test_a_marginally_faster_sharded_leg_is_not_worth_it():
    """Two modes within a few per cent are the same run with more ways to go wrong."""
    mode, why = bench.recommend(measurement("generation", 1.0), measurement("serial", 4.0),
                                measurement("sharded", 3.9))
    assert mode == "serial"
    assert "not worth" in why and f"{bench.WORTH_IT:.2f}" in why


def test_the_threshold_is_the_boundary():
    """Exactly at the threshold counts as worth it; just under does not."""
    serial = measurement("serial", 4.0)
    at = measurement("sharded", 4.0 / bench.WORTH_IT)
    under = measurement("sharded", 4.0 / (bench.WORTH_IT - 0.01))
    assert bench.recommend(measurement("generation", 1.0), serial, at)[0] == "sharded"
    assert bench.recommend(measurement("generation", 1.0), serial, under)[0] == "serial"


def test_cheap_analyzers_are_reported_as_nothing_to_parallelise():
    """A different reason from "it did not help": here the generator is the bottleneck."""
    mode, why = bench.recommend(measurement("generation", 4.0), measurement("serial", 4.2),
                                measurement("sharded", 4.1))
    assert mode == "serial"
    assert "nothing to parallelise" in why


def test_nothing_measured_recommends_the_safe_mode():
    mode, why = bench.recommend(measurement("generation"), measurement("serial"),
                                measurement("sharded"))
    assert mode == "serial"
    assert "nothing to compare" in why


def test_an_unmeasured_sharded_leg_without_a_reason_still_recommends_serial():
    mode, why = bench.recommend(measurement("generation", 1.0), measurement("serial", 4.0),
                                measurement("sharded"))
    assert mode == "serial" and "could not be measured" in why


# ── assumption A4, as a number ───────────────────────────────────────────────

def test_the_analyzer_share_is_what_the_analyzers_add():
    """01 A4 asked whether Rivet's cost is comparable to Pythia's; this is how it gets answered."""
    assert bench.analyzer_share(measurement("generation", 1.0),
                            measurement("serial", 4.0)) == pytest.approx(0.75)
    assert bench.analyzer_share(measurement("generation", 1.0),
                            measurement("serial", 1.0)) == pytest.approx(0.0)


def test_the_analyzer_share_never_goes_negative():
    """Two runs of the same thing differ by noise, and a negative share would read as nonsense."""
    assert bench.analyzer_share(measurement("generation", 1.1), measurement("serial", 1.0)) == 0.0


def test_the_analyzer_share_is_zero_when_a_leg_is_missing():
    assert bench.analyzer_share(measurement("generation"), measurement("serial", 4.0)) == 0.0


# ── derived numbers ──────────────────────────────────────────────────────────

def test_a_rate_needs_a_wall_clock():
    assert measurement("x", 2.0, events=1000).rate == pytest.approx(500.0)
    assert measurement("x", 0.0, events=1000).rate == 0.0, "no division by zero"


def test_a_refused_leg_is_not_measured_even_with_a_time():
    assert not bench.Measurement(name="sharded", wall_s=1.0, refused="no").measured
    assert bench.Measurement(name="sharded", wall_s=1.0).measured


# ── the cache ────────────────────────────────────────────────────────────────

def test_the_cache_round_trips(tmp_path, monkeypatch):
    """A cached report has to come back as the same numbers, or `--refresh` is the only safe option."""
    monkeypatch.setenv("HEKIT_ROOT", str(tmp_path))
    from hekit.env import paths

    monkeypatch.setattr(paths, "scratch_root", lambda: tmp_path / "scratch")

    report = bench.Report(project="p", point="q", machine=bench.machine_id(), threads=4,
                          events=1000, mode="sharded", reason="because",
                          measurements=[measurement("generation", 1.0), measurement("serial", 4.0)])
    bench.save_cached(report)
    back = bench.load_cached("p", "q")

    assert back is not None
    assert back.mode == "sharded" and back.reason == "because"
    assert [entry.name for entry in back.measurements] == ["generation", "serial"]
    assert back.measurements[1].wall_s == 4.0


def test_a_corrupt_cache_is_ignored_rather_than_fatal(tmp_path, monkeypatch):
    from hekit.env import paths

    monkeypatch.setattr(paths, "scratch_root", lambda: tmp_path / "scratch")
    path = bench.cache_path("p", "q")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert bench.load_cached("p", "q") is None


def test_the_cache_is_keyed_by_machine():
    """A number measured elsewhere is not a number about this machine."""
    assert bench.machine_id() in bench.cache_path("p", "q").name
