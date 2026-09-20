"""A user C++ module through the whole pipeline (P8-S01, 05 §5).

The toy module in `modules/Examples/ToyJets.cc` is built by the ordinary CMake rule, loaded with
`dlopen` at run time, and its YODA objects land in the **same** `analysis.yoda` as Rivet's.

Two of these tests are the reason the design is shaped the way it is:

* **serial and sharded give identical results.** A module's objects are filled and fills add, so k
  workers' clones sum to what one worker would have had. P6-S01 found the converse — an object that
  is `set` rather than filled cannot be merged at all — which is why a `Results::Worker` can only
  fill;
* **the normalised integral is σ, exactly.** Scaling happens once, in `finalize`, with σ and Σw
  known. There is no `scale()` during the run to call twice or to call early.

Marked `slow` and registered as the ctest test `modules`.
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
MODULE = REPO / "build" / "modules" / "Examples" / "libhekit_ToyJets.so"
PLUGIN = REPO / "build" / "analyses" / "PhotoProduction"
BASE_CARD = REPO / "tests" / "golden" / "inputs" / "PhotoProduction" / "photo_ep.cmnd"
SCRATCH = REPO / "output" / "scratch"

EVENTS = 2000
THREADS = 4
SEED = 606001

yoda = pytest.importorskip("yoda")
pytest.importorskip("tomli_w")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)"),
    pytest.mark.skipif(not MODULE.is_file(), reason="build the toy module first"),
]


def cards(directory: Path) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "photo_ep.cmnd").write_bytes(BASE_CARD.read_bytes())
    (directory / "point.cmnd").write_text(
        "Beams:frameType = 2\nBeams:eA = 920\nBeams:eB = 27.5\nBeams:idB = -11\n"
        "PDF:pSet = LHAPDF6:MSTW2008lo68cl\n", encoding="utf-8")
    return [str(directory / "photo_ep.cmnd"), str(directory / "point.cmnd")]


def run_spec(directory: Path, *, mode: str, with_rivet: bool = False, dump_every: int = 0,
             events: int = EVENTS, threads: int = THREADS):
    import tomli_w

    directory.mkdir(parents=True, exist_ok=True)
    sinks = []
    if with_rivet:
        sinks.append({"kind": "rivet", "analyses": ["photo_eic"], "paths": [str(PLUGIN)],
                      "xsec": "generator", "weights": "nominal", "dump_every": dump_every,
                      "check_beams": True})
    sinks.append({"kind": "module", "name": "ToyJets", "paths": [str(MODULE.parent)],
                  "options": {"pt_min": 0.5, "eta_max": 5.0}})

    spec = {
        "meta": {"schema": 2, "point": "mod", "hash": "sha256:" + "ab" * 32,
                 "origin": "P8-S01", "aliases": []},
        "run": {"events": events, "threads": threads, "mode": mode, "seed": SEED,
                "seeds": {"point": SEED, "instances": [SEED + index for index in range(threads)]}},
        "source": {"kind": "pythia", "cards": cards(directory / "cards")},
        "output": {"dir": str(directory), "yoda": "analysis.yoda",
                   "summary": "run.summary.json"},
        "sink": sinks,
        "status": {"fd": 3, "heartbeat_ms": 500},
    }
    path = directory / "run.toml"
    path.write_text(tomli_w.dumps(spec), encoding="utf-8")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    done = subprocess.run([str(RUN), str(path)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=1800, cwd=SCRATCH)
    assert done.returncode == 0, done.stderr[-3000:]
    summary = json.loads((directory / "run.summary.json").read_text(encoding="utf-8"))["run"]
    return yoda.read(str(directory / "analysis.yoda")), summary


@pytest.fixture(scope="module")
def modes(tmp_path_factory):
    """The same events, once serially and once sharded."""
    root = tmp_path_factory.mktemp("modules")
    made = {}
    for mode in ("serial", "sharded"):
        made[mode] = run_spec(root / mode, mode=mode)
    return made


# ── the exact-totals row ─────────────────────────────────────────────────────

def test_sharded_really_ran_sharded(modes):
    assert modes["serial"][1]["mode"] == "serial"
    assert modes["sharded"][1]["mode"] == "sharded"
    assert modes["sharded"][1]["threads"] == THREADS


def test_serial_and_sharded_are_identical(modes):
    """Fills add, so k workers' clones sum to what one worker would have had (05 §5)."""
    import yodacmp

    serial, sharded = modes["serial"][0], modes["sharded"][0]
    assert sorted(serial) == sorted(sharded)
    for path in sorted(serial):
        if path.endswith("pt_vs_eta"):
            continue                                   # a profile: compared through its sumW below
        assert serial[path].sumW() == pytest.approx(sharded[path].sumW(), rel=1e-12), path
    assert serial["/ToyJets/pt_vs_eta"].sumW() == \
        pytest.approx(sharded["/ToyJets/pt_vs_eta"].sumW(), rel=1e-12)


def test_the_same_events_were_seen(modes):
    assert modes["serial"][1]["events"] == modes["sharded"][1]["events"]
    assert modes["serial"][1]["xsec_pb"] == modes["sharded"][1]["xsec_pb"]
    assert modes["serial"][0]["/ToyJets/events"].sumW() == float(modes["serial"][1]["events"])


# ── the scaling row ──────────────────────────────────────────────────────────

def test_a_normalised_histogram_integrates_to_the_cross_section(modes):
    """σ/Σw × Σw = σ. The scaling contract, as a number."""
    objects, summary = modes["sharded"]
    assert objects["/ToyJets/multiplicity"].sumW() == pytest.approx(summary["xsec_pb"], rel=1e-6)


def test_an_unnormalised_counter_is_still_a_count(modes):
    """`finalize` scaled what it chose to; the counter is untouched, and says how many events."""
    objects, summary = modes["sharded"]
    assert objects["/ToyJets/events"].sumW() == pytest.approx(summary["events"])


def test_a_profile_is_left_alone(modes):
    """A profile is a mean, so scaling it would be wrong — the module does not, and this checks it."""
    objects, _ = modes["sharded"]
    profile = objects["/ToyJets/pt_vs_eta"]
    assert profile.sumW() > 0
    # `mean(2)` is the y axis: the mean pT in that eta bin. A few GeV in a photoproduction sample,
    # and enormous if anything had scaled it by σ.
    means = [entry.mean(2) for entry in profile.bins() if entry.numEntries() > 0]
    assert means, "the profile has no entries"
    assert max(means) < 100.0


# ── one file, and dumps ──────────────────────────────────────────────────────

def test_module_objects_share_rivets_file(tmp_path):
    """07 §1: one `analysis.yoda`, so `hep plot` and `rivet-mkhtml` treat them alike."""
    if not (PLUGIN / "Rivet_photo_eic.so").is_file():
        pytest.skip("build the Rivet plugin first")
    objects, _ = run_spec(tmp_path / "both", mode="serial", with_rivet=True, events=400,
                          threads=2)
    assert [path for path in objects if path.startswith("/ToyJets/")]
    assert [path for path in objects if path.startswith("/photo_eic/")]


def test_a_periodic_dump_is_written_and_holds_no_module_objects(tmp_path):
    """The dump is Rivet's, and a module's objects are unscaled until `finalize` (05 §5).

    Including them would put an unscaled distribution in a file that looks like a result — which is
    exactly the `legacy/Record` defect the scaling contract exists to prevent (00 §4.1).
    """
    if not (PLUGIN / "Rivet_photo_eic.so").is_file():
        pytest.skip("build the Rivet plugin first")
    directory = tmp_path / "dump"
    run_spec(directory, mode="serial", with_rivet=True, dump_every=200, events=600, threads=2)

    dump = directory / "analysis.dump.yoda"
    assert dump.is_file()
    objects = yoda.read(str(dump))
    assert objects, "the dump is empty"
    assert not [path for path in objects if path.startswith("/ToyJets/")]


# ── booking is validated before the run ──────────────────────────────────────

def test_a_module_that_is_not_there_fails_the_preflight(tmp_path):
    """A typo costs a second rather than a whole generation (06 §3.3)."""
    import tomli_w

    directory = tmp_path / "missing"
    directory.mkdir(parents=True)
    spec = {
        "meta": {"schema": 2, "point": "mod", "hash": "sha256:" + "ab" * 32,
                 "origin": "P8-S01", "aliases": []},
        "run": {"events": 10, "threads": 1, "mode": "serial", "seed": SEED,
                "seeds": {"point": SEED, "instances": [SEED]}},
        "source": {"kind": "pythia", "cards": cards(directory / "cards")},
        "output": {"dir": str(directory), "yoda": "analysis.yoda",
                   "summary": "run.summary.json"},
        "sink": [{"kind": "module", "name": "NoSuchModule", "paths": [str(MODULE.parent)]}],
        "status": {"fd": 3, "heartbeat_ms": 500},
    }
    path = directory / "run.toml"
    path.write_text(tomli_w.dumps(spec), encoding="utf-8")
    done = subprocess.run([str(RUN), str(path), "--check"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600, cwd=SCRATCH)
    assert done.returncode != 0
    assert "no module called 'NoSuchModule'" in done.stderr
    assert "libhekit_NoSuchModule.so" in done.stderr, "and it says where it looked"
