"""An external generator through the whole pipeline (P7-S01, 04 §1, §8).

There is no Sherpa on this machine, and waiting for one would leave the framework untested until
P7-S03. So the framework is exercised with a stand-in that behaves like an external generator in the
two ways that matter — a cacheable prepare step, and generating by writing HepMC3 into a FIFO — and
whose events come from an existing event store.

That last part is what makes this more than a smoke test. The events are the *same events* a Pythia
run already analysed, so the YODA that comes out of the FIFO can be compared with the YODA that run
produced. If the plumbing loses, reorders or duplicates an event, the histograms say so.

The store is written with **one** worker on purpose. 04 §8 says a stream takes σ from the last
event's `GenCrossSection`, "since there is one producer" — and that qualifier is load-bearing: with
two workers the last event carries one worker's running estimate, and every histogram comes out
scaled by the ratio between that and the merged σ.

Marked `slow` and registered as the ctest test `external_adapter`.
"""

from __future__ import annotations

import json
import os
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

EVENTS = 300

yoda = pytest.importorskip("yoda")
pytest.importorskip("tomli_w")
pytest.importorskip("pyHepMC3")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)"),
    pytest.mark.skipif(not (PLUGIN / "Rivet_photo_eic.so").is_file(),
                       reason="build the Rivet plugin first"),
]


def hep(*arguments: str, results: Path, store: Path, short_by: int = 0, expect: int = 0,
        timeout: int = 900):
    """Run the real `hep` CLI with the fake adapter registered in the child process.

    Registering there rather than here is the point: `hep run` is a separate process, and an adapter
    that only exists in the test's own interpreter would prove nothing.
    """
    bootstrap = (
        f"import sys; sys.path.insert(0, {str(REPO / 'utils' / 'python')!r});"
        f" sys.path.insert(0, {str(REPO / 'tests' / 'tools')!r});"
        f" import fake_adapter;"
        f" from hekit.adapters import register; register('fake', fake_adapter, description='stand-in');"
        f" from hekit.cli import main; raise SystemExit(main({list(arguments)!r}))")
    done = subprocess.run(
        [sys.executable, "-c", bootstrap], cwd=REPO, capture_output=True, timeout=timeout,
        stdin=subprocess.DEVNULL,
        env=dict(os.environ, HEKIT_RESULTS=str(results), HEKIT_FAKE_STORE=str(store),
                 HEKIT_FAKE_SHORT_BY=str(short_by)))
    done.text = done.stdout.decode("utf-8", errors="replace") + \
        done.stderr.decode("utf-8", errors="replace")
    assert done.returncode == expect, done.text
    return done


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    """A Pythia run that both analyses its events and stores them: the reference for everything."""
    import tomli_w

    directory = tmp_path_factory.mktemp("source")
    cards = directory / "cards"
    cards.mkdir()
    (cards / "photo_ep.cmnd").write_bytes(BASE_CARD.read_bytes())
    (cards / "point.cmnd").write_text(
        "Beams:frameType = 2\nBeams:eA = 920\nBeams:eB = 27.5\nBeams:idB = -11\n"
        "PDF:pSet = LHAPDF6:MSTW2008lo68cl\n", encoding="utf-8")

    spec = {
        "meta": {"schema": 2, "point": "src", "hash": "sha256:" + "ab" * 32,
                 "origin": "P7-S01", "aliases": []},
        # One worker: see the module docstring. With two, the stream's σ is one worker's estimate.
        "run": {"events": EVENTS, "threads": 1, "mode": "serial", "seed": 99001,
                "seeds": {"point": 99001, "instances": [99001]}},
        "source": {"kind": "pythia",
                   "cards": [str(cards / "photo_ep.cmnd"), str(cards / "point.cmnd")]},
        "output": {"dir": str(directory), "yoda": "analysis.yoda",
                   "summary": "run.summary.json"},
        "sink": [{"kind": "rivet", "analyses": ["photo_eic"], "paths": [str(PLUGIN)],
                  "xsec": "generator", "weights": "nominal", "dump_every": 0, "check_beams": True},
                 {"kind": "store", "dir": str(directory / "events"), "compression": "zst"}],
        "status": {"fd": 3, "heartbeat_ms": 500},
    }
    path = directory / "src.toml"
    path.write_text(tomli_w.dumps(spec), encoding="utf-8")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    done = subprocess.run([str(RUN), str(path)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900, cwd=SCRATCH)
    assert done.returncode == 0, done.stderr[-3000:]
    return directory


def write_config(directory: Path, *, seeds: bool = False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "fake.card").write_text("# a fake generator base card\nprocess = photoproduction\n",
                                         encoding="utf-8")
    text = f'''schema = 2

[run]
name = "fk"
events = {EVENTS}
seed = 4242
threads = 1

[generator]
tool = "fake"
card = "fake.card"

[beams]
ids = [2212, -11]

[rivet]
analyses = ["photo_eic"]
paths = ["{PLUGIN}"]

[output]
tag_style = "tag"

[settle.use]
energies = "27x920"

[quantity.energies]
type = "energies"
values = [[920, 27.5]]
labels = ["27x920 GeV"]
tags = ["27x920"]
use = 1

[study.one]
description = "one point through the stand-in generator"
'''
    if seeds:
        text += '''
[quantity.replica]
type = "seed"
values = [11, 22]
labels = ["seed 11", "seed 22"]
tags = ["s11", "s22"]

[study.seeds]
description = "two seed replicas: the prepare step must run once"
across = ["replica"]
'''
    path = directory / "fake.toml"
    path.write_text(text, encoding="utf-8")
    return path


def points_root(results: Path) -> Path:
    return results / "fakeproj" / "points"


@pytest.fixture(scope="module")
def ran(tmp_path_factory, source):
    """One point generated through the FIFO."""
    root = tmp_path_factory.mktemp("external")
    config = write_config(root / "fakeproj")
    results = root / "results"
    done = hep("run", str(config), "--plain", results=results, store=source / "events")
    return done, results, source


# ── the fake-generator row ───────────────────────────────────────────────────

def test_the_plan_is_prepare_generate_analyse(tmp_path, source):
    """04 §1's chain, and `hep-run` last because it is the one counting events."""
    config = write_config(tmp_path / "fakeproj")
    done = hep("plan", str(config), "--json", results=tmp_path / "results",
               store=source / "events")
    plan = json.loads(done.stdout.decode("utf-8", errors="replace"))
    group = plan["groups"][0]
    assert group["stages"] == ["fake-prepare", "fake-generate", "hep-run"]
    assert group["spec"]["source"]["kind"] == "stream", "the events arrive through a FIFO"
    assert group["spec"]["source"]["inputs"][0].endswith("events.hepmc")


def test_the_run_completes_through_the_stream(ran):
    """The step's row: `hep run` with the fake tool completes via `Source::Stream`."""
    _, results, _ = ran
    summary = json.loads(
        (points_root(results) / "fk_27x920" / "run.summary.json").read_text(encoding="utf-8"))["run"]
    assert summary["source"] == "stream"
    assert summary["events"] == EVENTS
    assert summary["seeds"]["instances"] == [], "a stream chose no seeds of its own"


def test_the_events_survive_the_fifo_intact(ran):
    """The strong check: the same events, so the same histograms — not merely similar ones."""
    import yodacmp

    _, results, source = ran
    report = yodacmp.compare(source / "analysis.yoda",
                             points_root(results) / "fk_27x920" / "analysis.yoda", raw=True)
    assert report.identical, report.table()
    assert report.compared >= 39


def test_a_fifo_is_used_and_left_behind_as_a_pipe(ran):
    """It lives beside the point's results, not in a shared `/tmp` path (00/B19)."""
    _, results, _ = ran
    fifo = points_root(results) / "fk_27x920" / "events.hepmc"
    assert fifo.is_fifo(), "an external generator's events never touch a regular file"


# ── the cache row ────────────────────────────────────────────────────────────

def test_two_seeds_prepare_once(tmp_path_factory, source):
    """The step's row, and the reason the cache exists (04 §1)."""
    root = tmp_path_factory.mktemp("seeds")
    config = write_config(root / "fakeproj", seeds=True)
    results = root / "results"
    hep("run", str(config), "--study", "seeds", "--plain", results=results,
        store=source / "events")

    names = sorted(entry.name for entry in points_root(results).iterdir() if entry.is_dir())
    assert names == ["fk_27x920_s11", "fk_27x920_s22"], "two seeds are two generations"

    logs = sorted(path.parent.parent.name
                  for path in results.rglob("logs/fake-prepare.log"))
    assert len(logs) == 1, f"the prepare step ran {len(logs)} times: {logs}"

    cached = list((results / "fakeproj" / ".cache" / "fake").iterdir())
    assert len(cached) == 1, "both seeds share one grid"
    marker = json.loads((cached[0] / "prepared.json").read_text(encoding="utf-8"))
    assert marker["tool"] == "fake" and marker["version"] == "1.0"
    assert marker["produces"] == ["grid.dat"]


def test_a_second_run_reuses_the_cache(tmp_path_factory, source):
    """Running the same point again must not integrate again."""
    root = tmp_path_factory.mktemp("again")
    config = write_config(root / "fakeproj")
    results = root / "results"
    hep("run", str(config), "--plain", results=results, store=source / "events")
    first = list(results.rglob("logs/fake-prepare.log"))
    assert len(first) == 1

    hep("run", str(config), "--rerun", "--plain", results=results, store=source / "events")
    assert len(list(results.rglob("logs/fake-prepare.log"))) == 1, "it prepared a second time"


# ── the rule that makes a short stream a failure (04 §8) ─────────────────────

def test_a_generator_that_stops_early_fails_the_point(tmp_path_factory, source):
    """σ was measured for the full run, so a YODA filled with fewer events is wrong by the shortfall."""
    root = tmp_path_factory.mktemp("short")
    config = write_config(root / "fakeproj")
    results = root / "results"
    done = hep("run", str(config), "--plain", results=results, store=source / "events",
               short_by=50, expect=1)
    assert "produced 250 of the 300" in done.text
    assert "-50" in done.text
