"""Serial and sharded give the same numbers, and sharding is refused where it would not (P6-S01).

The claim of 05 §3 is precise, and this checks it rather than trusting it: at a fixed seed and thread
count `PythiaParallel` generates the **same event set** whatever the mode — `balanceLoad` splits the
events evenly and each instance has its own seed — so serial and sharded differ only in which handler
saw which event and in what order the sums were done. The histograms must therefore agree, and the
totals must be equal, not merely compatible.

The other half is the part that is easy to get wrong quietly. Sharding is only sound when every piece
of the analysis is, and jet clustering here is not: `SISConePlugin` keeps its cache and its RNG in
process-wide statics, and this FastJet is built without `FASTJET_HAVE_LIMITED_THREAD_SAFETY`. A race
there does not crash — it changes the jets. So the tests below pin down *both* fallbacks: `auto`
declines and says why, and an explicit `sharded` stops rather than producing a plausible histogram
with the wrong numbers in it.

`MC_FSPARTICLES` and `MC_XS` stand in for the project's own analysis, which cannot be sharded at all
(that is what `test_an_explicit_sharded_run_refuses_an_analysis_that_clusters_jets` asserts).

Marked `slow` and registered as the ctest test `sharded_rivet`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "utils" / "python"))
sys.path.insert(0, str(REPO / "tests" / "tools"))

RUN = REPO / "build" / "bin" / "hep-run"
PLUGIN = REPO / "build" / "analyses" / "PhotoProduction"
BASE_CARD = REPO / "tests" / "golden" / "inputs" / "PhotoProduction" / "photo_ep.cmnd"
SCRATCH = REPO / "output" / "scratch"

#: Big enough for the step's "50k serial vs sharded" row, small enough to stay a test.
EVENTS = 50000
THREADS = 4

yoda = pytest.importorskip("yoda")
pytest.importorskip("tomli_w")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first"),
]


def cards(directory: Path) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "photo_ep.cmnd").write_bytes(BASE_CARD.read_bytes())
    (directory / "point.cmnd").write_text(
        "Beams:frameType = 2\nBeams:eA = 920\nBeams:eB = 27.5\nBeams:idB = -11\n"
        "PDF:pSet = LHAPDF6:MSTW2008lo68cl\n", encoding="utf-8")
    return [str(directory / "photo_ep.cmnd"), str(directory / "point.cmnd")]


def spec_for(directory: Path, *, mode: str, analyses, paths=(), events: int = 600,
             threads: int = THREADS, check_beams: bool = False, store: bool = False) -> dict:
    sinks = [{"kind": "rivet", "analyses": list(analyses), "paths": [str(entry) for entry in paths],
              "xsec": "generator", "weights": "nominal", "dump_every": 0,
              "check_beams": check_beams}]
    if store:
        sinks.append({"kind": "store", "dir": str(directory / "events"), "compression": "zst"})
    return {
        "meta": {"schema": 2, "point": "sharded", "hash": "sha256:" + "ab" * 32,
                 "origin": "P6-S01", "aliases": []},
        # The same seeds in both modes: that is what makes the event set the same, and so what makes
        # "the histograms must agree" a statement about the merge rather than about statistics.
        "run": {"events": events, "threads": threads, "mode": mode, "seed": 770001,
                "seeds": {"point": 770001,
                          "instances": [770001 + index for index in range(threads)]}},
        "source": {"kind": "pythia", "cards": cards(directory / "cards")},
        "output": {"dir": str(directory), "yoda": "analysis.yoda", "summary": "run.summary.json"},
        "sink": sinks,
        "status": {"fd": 3, "heartbeat_ms": 500},
    }


def run_spec(directory: Path, spec: dict, *, timeout: int = 1800):
    """Run `hep-run` with fd 3 captured, and return (process, status messages, summary-or-None)."""
    import tomli_w

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "run.toml"
    path.write_text(tomli_w.dumps(spec), encoding="utf-8")
    status = directory / "status.jsonl"
    SCRATCH.mkdir(parents=True, exist_ok=True)
    # `text=True` alone would decode with the locale's encoding, and under the C locale that is
    # ASCII: a message with one accented character then fails the test for the wrong reason.
    done = subprocess.run(
        ["sh", "-c", f'exec 3>{status}; exec "$@"', "hep-run", str(RUN), str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=SCRATCH)
    messages = [json.loads(line) for line in status.read_text(encoding="utf-8").splitlines()] \
        if status.is_file() else []
    summary_path = directory / "run.summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else None
    return done, messages, summary


def notices(messages) -> list[str]:
    return [message["msg"] for message in messages
            if message.get("k") == "log" and message.get("source") == "run"]


def init_mode(messages) -> str | None:
    for message in messages:
        if message.get("k") == "init":
            return message.get("mode")
    return None


@pytest.fixture(scope="module")
def both(tmp_path_factory):
    """The same 50k events, once serially and once sharded."""
    root = tmp_path_factory.mktemp("sharded")
    made = {}
    for mode in ("serial", "sharded"):
        directory = root / mode
        done, messages, summary = run_spec(
            directory, spec_for(directory, mode=mode, analyses=["MC_FSPARTICLES", "MC_XS"],
                                events=EVENTS))
        assert done.returncode == 0, done.stderr[-3000:]
        made[mode] = (directory, messages, summary)
    return made


# ── the equivalence row ──────────────────────────────────────────────────────

def test_sharded_really_ran_sharded(both):
    """Otherwise every comparison below would be a run compared with itself."""
    assert init_mode(both["serial"][1]) == "serial"
    assert init_mode(both["sharded"][1]) == "sharded"
    assert both["serial"][2]["run"]["mode"] == "serial"
    assert both["sharded"][2]["run"]["mode"] == "sharded"
    assert both["sharded"][2]["run"]["threads"] == THREADS


def test_the_two_modes_analysed_the_same_events(both):
    """A fixed seed and thread count fix the event set (05 §3), so this is exact."""
    serial = both["serial"][2]["run"]
    sharded = both["sharded"][2]["run"]
    assert serial["events"] == sharded["events"]
    assert serial["attempted"] == sharded["attempted"]
    assert serial["seeds"]["instances"] == sharded["seeds"]["instances"]


def test_every_histogram_agrees_bin_for_bin(both):
    """The step's row. Everything filled is identical; the one exception has its own test."""
    import yodacmp

    # rtol = 0: not "close enough" but *equal to the precision YODA writes*, which is what the two
    # modes actually produce here.
    report = yodacmp.compare(both["serial"][0] / "analysis.yoda",
                             both["sharded"][0] / "analysis.yoda", raw=True, rtol=0.0)
    assert report.compared >= 50
    assert not report.only_left and not report.only_right, report.table()
    differing = {difference.path for difference in report.differences}
    assert differing <= {"/MC_XS/XS", "/RAW/MC_XS/XS"}, report.table()


def test_the_totals_are_equal(both):
    """sumW and σ: the two numbers every normalisation downstream depends on."""
    serial = yoda.read(str(both["serial"][0] / "analysis.yoda"))
    sharded = yoda.read(str(both["sharded"][0] / "analysis.yoda"))
    assert serial["/RAW/_EVTCOUNT"].sumW() == sharded["/RAW/_EVTCOUNT"].sumW()
    assert serial["/_XSEC"].val() == sharded["/_XSEC"].val()

    summary = both["serial"][2]["run"]
    assert both["sharded"][2]["run"]["xsec_pb"] == summary["xsec_pb"]
    assert both["sharded"][2]["run"]["xsec_err_pb"] == summary["xsec_err_pb"]
    # The YODA is normalised to the σ the run measured, not to a per-event estimate (D-Q1).
    assert serial["/_XSEC"].val() == pytest.approx(summary["xsec_pb"], rel=1e-6)


def test_a_running_estimate_is_the_one_thing_a_merge_cannot_reproduce(both):
    """`MC_XS/XS` is `set()` from the per-event σ, so it is a snapshot, not a sum.

    Rivet marks `MC_XS` re-entrant and it is — every *filled* object merges exactly — but one of its
    objects records "σ as of the last event I saw". Four of those merged is not the last of one
    stream, and no merge can make it so; Rivet's own `merge` falls back to copying, so the value is
    whichever handler was folded in last. It matters because it is the shape of mistake a module
    (P8-S01) can make in results of its own: `fill` merges, `set` does not.

    Note what this does *not* assert: that the two modes disagree. Neither number is reproducible —
    `PythiaParallel` holds one mutex around the callback in serial mode but imposes no order, so
    "the last event" is whichever worker got there first — and they may coincide. What is asserted
    is that both remain estimates of the same σ, and that the run's own σ is untouched.
    """
    serial = yoda.read(str(both["serial"][0] / "analysis.yoda"))
    sharded = yoda.read(str(both["sharded"][0] / "analysis.yoda"))
    assert serial["/MC_XS/XS"].val() == pytest.approx(sharded["/MC_XS/XS"].val(), rel=0.05)
    for written in (serial, sharded):
        assert written["/MC_XS/XS"].val() == pytest.approx(written["/_XSEC"].val(), rel=0.05)
    # The number that is actually used downstream is unaffected, and exactly equal.
    assert serial["/_XSEC"].val() == sharded["/_XSEC"].val()


def test_sharding_is_faster(both):
    """The point of the phase. Measured at 1.67x on four threads; asserted only as "not slower"."""
    serial = both["serial"][2]["run"]["wall_s"]
    sharded = both["sharded"][2]["run"]["wall_s"]
    assert sharded < serial, f"sharded {sharded:.2f}s vs serial {serial:.2f}s"


# ── the fallback row ─────────────────────────────────────────────────────────

def test_a_non_reentrant_analysis_falls_back_to_serial_with_a_notice(tmp_path):
    """Rivet's own words: merging a non-re-entrant analysis gives an unpredictable result."""
    done, messages, summary = run_spec(
        tmp_path / "nonreentrant",
        spec_for(tmp_path / "nonreentrant", mode="auto", analyses=["MC_PRINTEVENT"], events=200))
    assert done.returncode == 0, done.stderr[-2000:]
    assert summary["run"]["mode"] == "serial"
    assert any("MC_PRINTEVENT" in notice and "Reentrant" in notice for notice in notices(messages)), \
        notices(messages)


def test_auto_declines_to_shard_rivet_when_fastjet_is_not_thread_safe(tmp_path):
    """Whether an analysis clusters is only known after `init()`, so `auto` cannot risk it.

    If FastJet is ever rebuilt with thread safety this flips, and the test says so instead of
    silently passing for the wrong reason.
    """
    done, messages, summary = run_spec(
        tmp_path / "auto", spec_for(tmp_path / "auto", mode="auto",
                                    analyses=["MC_FSPARTICLES"], events=200))
    assert done.returncode == 0, done.stderr[-2000:]
    if summary["run"]["mode"] == "serial":
        assert any("FASTJET_HAVE_LIMITED_THREAD_SAFETY" in notice for notice in notices(messages)), \
            notices(messages)
    else:
        assert summary["run"]["mode"] == "sharded", "a thread-safe FastJet: auto may shard"


def test_an_explicit_sharded_run_refuses_an_analysis_that_clusters_jets(tmp_path):
    """The project's own analysis, and the reason the whole gate exists.

    `photo_eic` runs kT, anti-kT and SISCone. SISCone keeps `stored_siscone`, `stored_particles` and
    `siscone::local_ranlux_state` in process-wide statics, so two threads clustering at once change
    each other's jets without any sign of it. Stopping is the only safe answer.
    """
    if not (PLUGIN / "Rivet_photo_eic.so").is_file():
        pytest.skip("build the Rivet plugin first")
    done, _, summary = run_spec(
        tmp_path / "jets", spec_for(tmp_path / "jets", mode="sharded", analyses=["photo_eic"],
                                    paths=[PLUGIN], events=200, check_beams=True))
    assert done.returncode != 0
    assert "clusters jets" in done.stderr
    assert "SISCone" in done.stderr
    assert summary is None, "a refused run writes no summary"


def test_the_project_analysis_still_runs_under_auto(tmp_path):
    """The fallback has to be a fallback: `auto` runs `photo_eic`, serially, without complaint."""
    if not (PLUGIN / "Rivet_photo_eic.so").is_file():
        pytest.skip("build the Rivet plugin first")
    done, messages, summary = run_spec(
        tmp_path / "photo", spec_for(tmp_path / "photo", mode="auto", analyses=["photo_eic"],
                                     paths=[PLUGIN], events=300, check_beams=True))
    assert done.returncode == 0, done.stderr[-2000:]
    assert summary["run"]["mode"] == "serial"
    assert (tmp_path / "photo" / "analysis.yoda").is_file()
    assert any("FASTJET" in notice for notice in notices(messages)), notices(messages)


# ── the sinks that can be sharded ────────────────────────────────────────────

def test_a_store_written_from_several_threads_is_whole(tmp_path):
    """The store shards on the *worker*, so a sharded run writes the same layout as a serial one.

    This is the sink that can actually be sharded here, and the one whose writer had to be made safe
    for it: the shard map grows when a worker first appears, and the total is counted across threads.
    """
    from hekit.store import index as index_module

    directory = tmp_path / "stored"
    done, _, summary = run_spec(
        directory, spec_for(directory, mode="sharded", analyses=["MC_FSPARTICLES"],
                            events=4000, store=True))
    assert done.returncode == 0, done.stderr[-3000:]
    assert summary["run"]["mode"] == "sharded"

    index = index_module.read(directory / "events")
    assert index.events == summary["run"]["events"], "every event reached a shard, exactly once"
    assert sum(shard.events for shard in index.shards) == index.events
    assert len(index.shards) == THREADS, "one shard per worker, whatever the mode"
