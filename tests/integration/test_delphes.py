"""A real detector stage through `hep run` (P7-S08, 05 §5).

Delphes 3.5.1 is installed here, so this runs it: Pythia generates, `Analyzer::Delphes` tees the events
to a file, and `DelphesHepMC3` turns them into `delphes.root` — which `hep proc` (12) will read with
uproot, so the test reads it that way too.

**The tee is a file, not a FIFO, and that is the finding this step made.** 05 §5 described a pipe with
Delphes reading it alongside `hep-run`. `DelphesHepMC3` sizes its input first and skips anything of
length zero (`readers/DelphesHepMC3.cpp:160-169`), and a FIFO always measures zero — so it opened the
pipe, decided it was empty, exited, and `hep-run` died writing into a closed pipe. The test that the
intermediate is a regular file is therefore not pedantry.

Marked `slow` and registered as the ctest test `delphes`.
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
PLUGIN = REPO / "build" / "analyses" / "PhotoProduction"
BASE_CARD = REPO / "tests" / "golden" / "inputs" / "PhotoProduction" / "photo_ep.cmnd"

uproot = pytest.importorskip("uproot")

DELPHES = shutil.which("DelphesHepMC3") or \
    str(Path.home() / "HEP" / "install" / "delphes" / "bin" / "DelphesHepMC3")
CARDS = Path(DELPHES).parent.parent / "cards"
CARD = CARDS / "delphes_card_CMS.tcl"

EVENTS = 200

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)"),
    pytest.mark.skipif(not (PLUGIN / "Rivet_photo_eic.so").is_file(),
                       reason="build the Rivet plugin first"),
    pytest.mark.skipif(not Path(DELPHES).is_file(), reason="Delphes is not installed"),
    pytest.mark.skipif(not CARD.is_file(), reason="no Delphes CMS card"),
]


def hep(*arguments: str, results: Path, expect: int = 0, timeout: int = 1800):
    done = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(REPO / 'utils' / 'python')!r});"
         f" from hekit.cli import main; raise SystemExit(main({list(arguments)!r}))"],
        cwd=REPO, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
        env=dict(os.environ, HEKIT_RESULTS=str(results),
                 PATH=f"{Path(DELPHES).parent}:{os.environ.get('PATH', '')}"))
    done.text = done.stdout.decode("utf-8", errors="replace") + \
        done.stderr.decode("utf-8", errors="replace")
    assert done.returncode == expect, done.text[-4000:]
    return done


def write_config(directory: Path, *, card: Path = CARD, keep: bool = False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "dl.toml"
    path.write_text(f'''schema = 2

[run]
name = "dl"
events = {EVENTS}
seed = 9001
threads = 2

[generator]
tool = "pythia"
card = "{BASE_CARD}"

[beams]
ids = [2212, -11]

[rivet]
analyses = ["photo_eic"]
paths = ["{PLUGIN}"]

[delphes]
card = "{card}"
keep_events = {str(keep).lower()}

[output]
tag_style = "tag"

[static.use]
energies = "27x920"

[quantity.energies]
type = "energies"
values = [[920, 27.5]]
labels = ["27x920"]
tags = ["27x920"]
use = 1

[study.one]
description = "one point with a detector stage"
''', encoding="utf-8")
    return path


def point_dir(results: Path) -> Path:
    return results / "proj" / "points" / "dl_27x920"


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    root = tmp_path_factory.mktemp("delphes")
    config = write_config(root / "proj")
    results = root / "results"
    hep("run", str(config), "--plain", results=results)
    return config, results


# ── the output row ───────────────────────────────────────────────────────────

def test_the_detector_stage_runs_after_the_generator(tmp_path):
    """Not alongside it: Delphes cannot read a pipe, so it reads a finished file (P7-S08)."""
    config = write_config(tmp_path / "proj")
    done = hep("plan", str(config), "--json", results=tmp_path / "results")
    plan = json.loads(done.stdout.decode("utf-8", errors="replace"))
    group = plan["groups"][0]
    assert group["stages"] == ["hep-run", "delphes"]
    assert "delphes" in [analyzer["kind"] for analyzer in group["spec"]["analyzer"]]


def test_delphes_root_is_readable_by_uproot(ran):
    """The step's row, and the form `hep proc` will read it in (12 §1)."""
    _, results = ran
    path = point_dir(results) / "delphes.root"
    assert path.is_file()
    with uproot.open(path) as handle:
        tree = handle["Delphes"]
        assert tree.num_entries == EVENTS
        assert any(branch.startswith("Jet") for branch in tree.keys())


def test_the_rivet_analysis_still_ran(ran):
    """The tee is a *tee*: the detector does not take the events away from the other analyzers."""
    import yoda

    _, results = ran
    objects = yoda.read(str(point_dir(results) / "analysis.yoda"))
    assert [path for path in objects if path.startswith("/photo_eic/")]


def test_the_sidecar_says_what_produced_it(ran):
    """So a ROOT file can be traced without opening it."""
    _, results = ran
    found = json.loads((point_dir(results) / "delphes.json").read_text(encoding="utf-8"))
    assert found["point"] == "dl_27x920"
    assert found["card"] == str(CARD)
    assert len(found["card_sha256"]) == 64
    assert found["hash"], "the point's identity, so the ROOT file can be matched to a run"


def test_the_intermediate_is_cleared_by_default(ran):
    """It is uncompressed and routinely larger than everything else the point produced."""
    _, results = ran
    assert not (point_dir(results) / "events.delphes.hepmc").exists()


def test_keep_events_keeps_it_as_a_regular_file(tmp_path_factory):
    """A regular file, not a FIFO — which is the whole reason this step's design changed."""
    root = tmp_path_factory.mktemp("delphes_keep")
    config = write_config(root / "proj", keep=True)
    results = root / "results"
    hep("run", str(config), "--plain", results=results)

    events = point_dir(results) / "events.delphes.hepmc"
    assert events.is_file()
    assert not events.is_fifo(), "Delphes skips any input whose length is zero"
    assert events.stat().st_size > 0
    assert events.read_text(encoding="utf-8", errors="replace").startswith("HepMC::Version")


# ── the failure row ──────────────────────────────────────────────────────────

def test_a_bad_card_fails_the_point_and_is_attributed(tmp_path_factory):
    """The step's row. Delphes exits 1 for a bad card, and 1 is "spec or card error"."""
    root = tmp_path_factory.mktemp("delphes_bad")
    bad = root / "proj" / "bad.tcl"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("this is not a Delphes card\nset Nonsense {\n", encoding="utf-8")
    config = write_config(root / "proj", card=bad)
    results = root / "results"

    done = hep("run", str(config), "--plain", results=results, expect=1)
    assert "delphes failed" in done.text, done.text[-2000:]
    assert not (point_dir(results) / "delphes.root").exists()
    # The events it could not read are left behind, because that is what you would want to look at.
    assert (point_dir(results) / "events.delphes.hepmc").is_file()
