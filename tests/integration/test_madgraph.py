"""A real MadGraph point through `hep run` (P7-S05, 04 §7).

`e+ e- → mu+ mu-` at the Z: the smallest thing MadGraph can be asked to do, which is the point — the
step's rows are about the *chain*, not about the physics. Four processes run in order (build, launch,
unpack, shower) and none of them may overlap, because each reads a file the one before it wrote.

The chain is worth stating once more because it is unlike every other adapter's: MadGraph produces a
matrix element, not events, and Pythia showers it **inside `hep-run`**. So there is no FIFO, the
source is `Source::Pythia`, and the cross-section comes from the LHE header rather than from a
`GenCrossSection`.

Marked `slow` and registered as the ctest test `madgraph`. Building the process directory is about a
minute, so the fixture runs it once.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "utils" / "python"))

RUN = REPO / "build" / "bin" / "hep-run"

yoda = pytest.importorskip("yoda")

MG = shutil.which("mg5_aMC") or str(Path.home() / "HEP" / "install" / "madgraph" / "bin" / "mg5_aMC")

EVENTS = 100

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)"),
    pytest.mark.skipif(not Path(MG).is_file(), reason="MadGraph is not installed"),
]

PROC_CARD = """# the smallest thing MadGraph can be asked to do
generate e+ e- > mu+ mu-
"""

SHOWER_CARD = """! Pythia settings for showering MadGraph's LHE events.
PartonLevel:MPI = off
Print:quiet = on
"""


def hep(*arguments: str, results: Path, expect: int = 0, timeout: int = 2400):
    done = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(REPO / 'utils' / 'python')!r});"
         f" from hekit.cli import main; raise SystemExit(main({list(arguments)!r}))"],
        cwd=REPO, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
        env=dict(os.environ, HEKIT_RESULTS=str(results),
                 PATH=f"{Path(MG).parent}:{os.environ.get('PATH', '')}"))
    done.text = done.stdout.decode("utf-8", errors="replace") + \
        done.stderr.decode("utf-8", errors="replace")
    assert done.returncode == expect, done.text[-4000:]
    return done


def write_config(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "proc.dat").write_text(PROC_CARD, encoding="utf-8")
    (directory / "shower.cmnd").write_text(SHOWER_CARD, encoding="utf-8")
    path = directory / "mg.toml"
    path.write_text(f'''schema = 2

[run]
name = "mg"
events = {EVENTS}
seed = 5151
threads = 1

[generator]
tool = "madgraph"
card = "proc.dat"
shower = "shower.cmnd"

[beams]
ids = [11, -11]

[rivet]
analyses = ["MC_FSPARTICLES"]
paths = []

[output]
tag_style = "tag"

[static.use]
energies = "91"

[quantity.energies]
type = "energies"
values = [[45.6, 45.6]]
labels = ["91"]
tags = ["91"]
use = 1

[study.one]
description = "one MadGraph point"
''', encoding="utf-8")
    return path


def points_root(results: Path) -> Path:
    return results / "proj" / "points"


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    root = tmp_path_factory.mktemp("madgraph")
    config = write_config(root / "proj")
    results = root / "results"
    hep("run", str(config), "--plain", results=results)
    return config, results


# ── the toy row ──────────────────────────────────────────────────────────────

def test_the_chain_is_four_phases_in_order(tmp_path):
    """Each stage reads a file the one before wrote, so none of them may overlap (04 §7).

    Planned in a *fresh* results tree, because a built process directory is exactly what the plan
    then leaves out — which the next test checks.
    """
    config = write_config(tmp_path / "proj")
    done = hep("plan", str(config), "--json", results=tmp_path / "results")
    plan = json.loads(done.stdout.decode("utf-8", errors="replace"))
    group = plan["groups"][0]
    assert group["stages"] == ["madgraph-build", "madgraph-launch", "madgraph-unpack", "hep-run"]
    # The source is Pythia: MadGraph handed over a matrix element, not events.
    assert group["spec"]["source"]["kind"] == "pythia"


def test_a_built_process_directory_drops_out_of_the_plan(ran):
    """The cache, seen from the planner: there is nothing left to build."""
    config, results = ran
    done = hep("plan", str(config), "--json", results=results)
    plan = json.loads(done.stdout.decode("utf-8", errors="replace"))
    assert plan["groups"][0]["stages"] == ["madgraph-launch", "madgraph-unpack", "hep-run"]


def test_the_lhe_is_showered_and_analysed(ran):
    """The step's row: 1k LHE events showered and analysed. (100 here — the chain is the subject.)"""
    _, results = ran
    directory = points_root(results) / "mg_91"
    summary = json.loads((directory / "run.summary.json").read_text(encoding="utf-8"))["run"]
    assert summary["source"] == "pythia"
    assert summary["events"] == EVENTS
    assert summary["xsec_pb"] > 0, "σ comes from the LHE header"

    objects = yoda.read(str(directory / "analysis.yoda"))
    assert [path for path in objects if path.startswith("/MC_FSPARTICLES/")]
    assert objects["/_XSEC"].val() == pytest.approx(summary["xsec_pb"], rel=1e-6)


def test_the_lhe_was_unpacked_beside_the_results(ran):
    """The shower card has to name it, and a cache path would make the cache key depend on itself."""
    _, results = ran
    directory = points_root(results) / "mg_91"
    assert (directory / "events.lhe").is_file()
    assert not (directory / "events.hepmc").exists(), "nothing streams, so no FIFO is made"


def test_the_shower_card_takes_its_beams_from_the_lhe(ran):
    """`frameType = 4` means Pythia reads them from the header; repeating them would be ignored."""
    _, results = ran
    card = (points_root(results) / "mg_91" / "point.cmnd").read_text(encoding="utf-8")
    assert "Beams:frameType = 4" in card
    assert "Beams:LHEF" in card
    assert "Beams:idA" not in card and "Beams:eA" not in card


def test_the_launch_script_is_on_disk(ran):
    """It carries the seed, the event count and the beams, so it is part of what ran."""
    _, results = ran
    script = (points_root(results) / "mg_91" / "launch.dat").read_text(encoding="utf-8")
    assert f"set nevents {EVENTS}" in script
    assert "set lpp1 0" in script and "set ebeam1 45.6" in script
    assert "shower=OFF" in script


# ── the cache row ────────────────────────────────────────────────────────────

def test_the_second_run_reuses_the_process_directory(ran):
    """The step's row. Building it is a minute of Fortran and does not depend on the seed."""
    config, results = ran
    entries = list((results / "proj" / ".cache" / "madgraph").iterdir())
    assert len(entries) == 1
    marker = json.loads((entries[0] / "prepared.json").read_text(encoding="utf-8"))
    assert marker["tool"] == "madgraph" and marker["version"]
    assert marker["produces"] == ["process/bin/generate_events"]

    before = (entries[0] / "process" / "bin" / "generate_events").stat().st_mtime
    hep("run", str(config), "--rerun", "--plain", results=results)
    assert len(list(results.rglob("logs/madgraph-build.log"))) == 1, "it built a second time"
    assert (entries[0] / "process" / "bin" / "generate_events").stat().st_mtime == before
