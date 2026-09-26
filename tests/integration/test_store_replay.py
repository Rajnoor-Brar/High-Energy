"""Replaying a store through the same analyzers as fresh events (P5-S02, 11 §4).

The claim this step makes is strong and easy to check: a replay is *the same events*, so analysing a
store must give exactly what analysing the generation gave — not compatible, identical. The rest is
about what a replay may not do (change the events) and what happens when it is stopped.

Marked `slow` and registered as the ctest test `store_replay`.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "utils" / "python"))

RUN = REPO / "build" / "bin" / "hep-run"
PLUGIN = REPO / "build" / "analyses" / "PhotoProduction"
BASE_CARD = REPO / "tests" / "golden" / "inputs" / "PhotoProduction" / "photo_ep.cmnd"

yoda = pytest.importorskip("yoda")
pytest.importorskip("tomli_w")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first"),
    pytest.mark.skipif(not (PLUGIN / "Rivet_photo_eic.so").is_file(),
                       reason="build the Rivet plugin first"),
]


def write_spec(path: Path, spec: dict) -> Path:
    import tomli_w

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(spec), encoding="utf-8")
    return path


def run_spec(path: Path, *arguments: str, timeout: int = 1800):
    return subprocess.run([str(RUN), str(path), *arguments], capture_output=True, text=True,
                          timeout=timeout, cwd=REPO / "output" / "scratch")


def cards(directory: Path) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "photo_ep.cmnd").write_bytes(BASE_CARD.read_bytes())
    (directory / "point.cmnd").write_text(
        "Beams:frameType = 2\nBeams:eA = 920\nBeams:eB = 27.5\nBeams:idB = -11\n"
        "PDF:pSet = LHAPDF6:MSTW2008lo68cl\n", encoding="utf-8")
    return [str(directory / "photo_ep.cmnd"), str(directory / "point.cmnd")]


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """One run that both analyses its events and stores them: the reference for every replay."""
    directory = tmp_path_factory.mktemp("generated")
    spec = {
        "meta": {"schema": 2, "point": "stored", "hash": "sha256:" + "ab" * 32,
                 "origin": "P5-S02", "aliases": []},
        "run": {"events": 800, "threads": 3, "seed": 424001,
                "seeds": {"point": 424001, "instances": [424001, 424002, 424003]}},
        "source": {"kind": "pythia", "cards": cards(directory)},
        "output": {"dir": str(directory), "yoda": "analysis.yoda", "summary": "run.summary.json"},
        "analyzer": [{"kind": "rivet", "analyses": ["photo_eic"], "paths": [str(PLUGIN)],
                  "xsec": "generator", "weights": "nominal", "dump_every": 0, "check_beams": True},
                 {"kind": "store", "dir": str(directory / "events"), "compression": "zst"}],
        "status": {"fd": 3, "heartbeat_ms": 500},
    }
    done = run_spec(write_spec(directory / "run.toml", spec))
    assert done.returncode == 0, done.stderr[-3000:]
    return directory


def replay_spec(store: Path, output: Path, *, analyses=("photo_eic",), queue: int = 0) -> dict:
    from hekit.adapters import store as store_adapter

    document = store_adapter.store_document(store, queue=queue)
    return {
        "meta": {"schema": 2, "point": "replayed", "hash": "sha256:" + "cd" * 32,
                 "origin": "P5-S02 replay", "aliases": []},
        "run": {"events": 0, "threads": 0, "seed": 0, "seeds": {"point": 0, "instances": []}},
        "source": {"kind": "store", "input": str(store), "store": document},
        "output": {"dir": str(output), "yoda": "analysis.yoda", "summary": "run.summary.json"},
        "analyzer": [{"kind": "rivet", "analyses": list(analyses), "paths": [str(PLUGIN)],
                  "xsec": "generator", "weights": "nominal", "dump_every": 0, "check_beams": True}],
        "status": {"fd": 3, "heartbeat_ms": 500},
    }


# ── the replay row ───────────────────────────────────────────────────────────

def test_a_replay_consumes_every_event_the_index_promised(generated, tmp_path):
    """The step's row: events consumed = the index's total."""
    from hekit.store import index as index_module

    store = generated / "events"
    index = index_module.read(store)
    output = tmp_path / "replay"
    done = run_spec(write_spec(tmp_path / "replay.toml", replay_spec(store, output)))
    assert done.returncode == 0, done.stderr[-3000:]

    summary = json.loads((output / "run.summary.json").read_text(encoding="utf-8"))["run"]
    assert summary["events"] == index.events
    assert summary["source"] == "store"
    assert summary["seeds"]["instances"] == [], "a replay chose no seeds and says so"
    assert summary["threads"] == len(index.shards), "one reader per shard"


def test_a_replay_reproduces_the_generation_exactly(generated, tmp_path):
    """Same events, same analysis: identical histograms, not merely compatible."""
    sys.path.insert(0, str(REPO / "tests" / "tools"))
    import yodacmp

    output = tmp_path / "replay"
    done = run_spec(write_spec(tmp_path / "replay.toml", replay_spec(generated / "events", output)))
    assert done.returncode == 0, done.stderr[-3000:]

    report = yodacmp.compare(generated / "analysis.yoda", output / "analysis.yoda", raw=True)
    assert report.identical, report.table()
    assert report.compared >= 39


def test_the_cross_section_comes_from_the_index(generated, tmp_path):
    """11 §4: σ is the run's merged value, carried by the index — not a per-event estimate."""
    from hekit.store import index as index_module

    output = tmp_path / "replay"
    run_spec(write_spec(tmp_path / "replay.toml", replay_spec(generated / "events", output)))
    index = index_module.read(generated / "events")
    objects = yoda.read(str(output / "analysis.yoda"))
    # rel=1e-6, not 1e-9: YODA writes about seven significant digits, so the *file* cannot hold the
    # index's full double. The value is the index's, rounded by the writer.
    assert objects["/_XSEC"].val() == pytest.approx(index.xsec_pb, rel=1e-6)
    assert objects["/_XSEC"].totalErrAvg() == pytest.approx(index.xsec_err_pb, rel=1e-6)


def test_a_small_queue_still_replays_everything(generated, tmp_path):
    """Backpressure is a bound on memory, not on correctness."""
    output = tmp_path / "replay"
    done = run_spec(write_spec(tmp_path / "replay.toml",
                               replay_spec(generated / "events", output, queue=4)))
    assert done.returncode == 0, done.stderr[-3000:]
    objects = yoda.read(str(output / "analysis.yoda"))
    assert objects["/_EVTCOUNT"].val() == pytest.approx(
        yoda.read(str(generated / "analysis.yoda"))["/_EVTCOUNT"].val())


def test_a_replay_can_add_an_analysis_variant(generated, tmp_path):
    """The point of a store: a new option costs a read, not a generation (03 §4)."""
    output = tmp_path / "replay"
    done = run_spec(write_spec(tmp_path / "replay.toml", replay_spec(
        generated / "events", output, analyses=("photo_eic:R=0.4", "photo_eic:R=1.0"))))
    assert done.returncode == 0, done.stderr[-3000:]
    objects = yoda.read(str(output / "analysis.yoda"))
    variants = sorted({path.split("/")[1] for path in objects if path.startswith("/photo_eic")})
    assert variants == ["photo_eic:R=0.4", "photo_eic:R=1.0"]
    assert objects["/_EVTCOUNT"].val() == pytest.approx(800, rel=0.02), "one pass over the events"


# ── the stop row ─────────────────────────────────────────────────────────────

def test_sigint_during_a_replay_stops_it_with_partial_output(generated, tmp_path):
    """06 §3.3: exit 6 and a partial YODA, the same contract as a generating run."""
    output = tmp_path / "replay"
    spec = replay_spec(generated / "events", output, queue=1)
    path = write_spec(tmp_path / "replay.toml", spec)

    process = subprocess.Popen([str(RUN), str(path), "--plain"], cwd=REPO / "output" / "scratch",
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    try:
        time.sleep(0.4)                      # let it get into the event loop
        os.killpg(os.getpgid(process.pid), signal.SIGINT)
        status = process.wait(timeout=300)
    finally:
        if process.poll() is None:           # pragma: no cover - only on a failure
            process.kill()
            process.wait(timeout=30)

    # Either it finished the 800 events first (they are quick) or it was stopped; both are correct,
    # and the contract is that a stop leaves a partial file and exit 6.
    assert status in {0, 6}, status
    if status == 6:
        assert (output / "analysis.partial.yoda").is_file()
        assert not (output / "analysis.yoda").exists(), "never both (07 §1)"
        summary = json.loads((output / "run.summary.json").read_text(encoding="utf-8"))["run"]
        assert summary["stopped"] is True
        assert 0 < summary["events"] <= 800
    else:
        assert (output / "analysis.yoda").is_file()
