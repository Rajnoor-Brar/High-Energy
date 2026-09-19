"""A real Whizard point through `hep run` (P7-S04, 04 §5).

Whizard 3.1.8 is installed here, so this runs it. Two rows: a toy `e+e- → jj`, and the ep card D-Q7
settled on — direct photoproduction, which is Whizard's own physics rather than a cross-check of
`photo_ep.cmnd`.

Two findings are pinned here because they are properties of Whizard that bite immediately and would
otherwise be rediscovered:

* it writes **no cross-section** into its HepMC3 output — no `C` record at all — so a point must set
  `[rivet].xsec`, and `hep-run` refuses to normalise by nothing rather than dividing by zero;
* compiling the matrix-element library and integrating is expensive and seed-independent, which is
  exactly what the prepare cache is for.

Marked `slow` and registered as the ctest test `whizard`.
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
CARD = REPO / "configs" / "PhotoProduction" / "photo_ep.sin"

yoda = pytest.importorskip("yoda")

WHIZARD = shutil.which("whizard") or str(Path.home() / "HEP" / "install" / "whizard" / "bin" / "whizard")

#: Whizard's own integration of the ep card: `n_events / corr. to luminosity`, in pb.
EP_XSEC = 2481.6

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)"),
    pytest.mark.skipif(not Path(WHIZARD).is_file(), reason="Whizard is not installed"),
]

TOY_CARD = """# a toy base card for the adapter test
model = SM
process toy = e1, E1 => u, U
integrate (toy)
simulate (toy)
"""


def hep(*arguments: str, results: Path, expect: int = 0, timeout: int = 1800):
    done = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(REPO / 'utils' / 'python')!r});"
         f" from hekit.cli import main; raise SystemExit(main({list(arguments)!r}))"],
        cwd=REPO, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
        env=dict(os.environ, HEKIT_RESULTS=str(results),
                 PATH=f"{Path(WHIZARD).parent}:{os.environ.get('PATH', '')}"))
    done.text = done.stdout.decode("utf-8", errors="replace") + \
        done.stderr.decode("utf-8", errors="replace")
    assert done.returncode == expect, done.text[-4000:]
    return done


def write_config(directory: Path, *, card: str, card_name: str, events: int, beams: str,
                 energies: str, tag: str, xsec: str = "", seeds: bool = False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / card_name).write_text(card, encoding="utf-8")
    text = f'''schema = 2

[run]
name = "wz"
events = {events}
seed = 8001
threads = 1

[generator]
tool = "whizard"
card = "{card_name}"

[beams]
ids = [{beams}]

[rivet]
analyses = ["MC_FSPARTICLES"]
paths = []
{f"xsec = {xsec}" if xsec else ""}

[output]
tag_style = "tag"

[settle.use]
energies = "{tag}"

[quantity.energies]
type = "energies"
values = [{energies}]
labels = ["{tag}"]
tags = ["{tag}"]
use = 1

[study.one]
description = "one Whizard point"
'''
    if seeds:
        text += '''
[quantity.replica]
type = "seed"
values = [5, 6]
labels = ["seed 5", "seed 6"]
tags = ["s5", "s6"]

[study.seeds]
across = ["replica"]
'''
    path = directory / "wz.toml"
    path.write_text(text, encoding="utf-8")
    return path


def points_root(results: Path) -> Path:
    return results / "proj" / "points"


def only_point(results: Path) -> Path:
    found = [entry for entry in points_root(results).iterdir() if entry.is_dir()]
    assert len(found) == 1, found
    return found[0]


# ── the toy row ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def toy(tmp_path_factory):
    """`e+e- → u ubar` at the Z: small, fast, and nothing to do with photoproduction."""
    root = tmp_path_factory.mktemp("whizard_toy")
    config = write_config(root / "proj", card=TOY_CARD, card_name="toy.sin", events=20,
                          beams="11, -11", energies="[45.6, 45.6]", tag="91", xsec="1.0")
    results = root / "results"
    hep("run", str(config), "--plain", results=results)
    return results


def test_the_toy_runs_end_to_end(toy):
    """The step's row. Whizard is parton-level, so the 'final state' is the hard process."""
    directory = only_point(toy)
    summary = json.loads((directory / "run.summary.json").read_text(encoding="utf-8"))["run"]
    assert summary["source"] == "stream"
    assert summary["events"] == 20
    objects = yoda.read(str(directory / "analysis.yoda"))
    assert [path for path in objects if path.startswith("/MC_FSPARTICLES/")]


def test_the_plan_is_integrate_generate_analyse(tmp_path):
    config = write_config(tmp_path / "proj", card=TOY_CARD, card_name="toy.sin", events=20,
                          beams="11, -11", energies="[45.6, 45.6]", tag="91", xsec="1.0")
    done = hep("plan", str(config), "--json", results=tmp_path / "results")
    plan = json.loads(done.stdout.decode("utf-8", errors="replace"))
    group = plan["groups"][0]
    assert group["stages"] == ["whizard-integrate", "whizard-generate", "hep-run"]
    assert group["spec"]["source"]["kind"] == "stream"


def test_the_point_card_runs_before_the_base(toy):
    """04 §5's order, on disk: SINDARIN executes top to bottom."""
    card = (only_point(toy) / "point.sin").read_text(encoding="utf-8")
    include = card.index("include(")
    assert card.index("seed =") < include
    assert card.index("n_events =") < include
    # An `energies` quantity is always a pair (the schema refuses a scalar), so this is the
    # `beams_momentum` path; the `sqrts` one is covered by the unit tests.
    assert "beams_momentum = 45.6, 45.6" in card
    assert "beams = e1, E1" in card, "PDG codes became the model's names"


def test_the_integration_card_is_written_beside_the_grids(toy):
    """It has to exist for the prepare stage, and it must not generate (or it opens the FIFO)."""
    entries = list((toy / "proj" / ".cache" / "whizard").iterdir())
    assert len(entries) == 1
    integration = (entries[0] / "integrate.sin").read_text(encoding="utf-8")
    assert "n_events = 0" in integration
    assert "$sample" not in integration


# ── the ep row ───────────────────────────────────────────────────────────────

@pytest.mark.skipif(not CARD.is_file(), reason="the Whizard ep card is missing")
def test_the_ep_card_runs(tmp_path_factory):
    """The card D-Q7 settled on: direct photoproduction, Whizard's own physics."""
    root = tmp_path_factory.mktemp("whizard_ep")
    config = write_config(root / "proj", card=CARD.read_text(encoding="utf-8"),
                          card_name=CARD.name, events=50, beams="2212, 11",
                          energies="[275.0, 18.0]", tag="18x275", xsec=str(EP_XSEC))
    results = root / "results"
    hep("run", str(config), "--plain", results=results)

    directory = only_point(results)
    summary = json.loads((directory / "run.summary.json").read_text(encoding="utf-8"))["run"]
    assert summary["events"] == 50
    card = (directory / "point.sin").read_text(encoding="utf-8")
    assert "beams = p, e1 => pdf_builtin, epa" in card, "the plan's half and the card's half"
    assert "beams_momentum = 275.0, 18.0" in card

    objects = yoda.read(str(directory / "analysis.yoda"))
    assert objects["/_XSEC"].val() == pytest.approx(EP_XSEC, rel=1e-6), \
        "the YODA is normalised by the σ the config supplied"


@pytest.mark.skipif(not CARD.is_file(), reason="the Whizard ep card is missing")
def test_without_a_cross_section_the_run_is_refused(tmp_path_factory):
    """Whizard writes no `GenCrossSection`, and a YODA normalised by zero is worse than none (04 §8)."""
    root = tmp_path_factory.mktemp("whizard_noxsec")
    config = write_config(root / "proj", card=CARD.read_text(encoding="utf-8"),
                          card_name=CARD.name, events=50, beams="2212, 11",
                          energies="[275.0, 18.0]", tag="18x275")      # no xsec
    # Exit 5 is the sink's own code (06 §3.3): the generator did its job, the sink refused to
    # normalise by nothing, and `hep run` reports the code the stage gave it.
    done = hep("run", str(config), "--plain", results=root / "results", expect=5)
    assert "sink error" in done.text

    # The message itself is in the stage's log, which is where a tool's own output belongs (06 §4).
    log = (only_point(root / "results") / "logs" / "hep-run.log").read_text(encoding="utf-8",
                                                                           errors="replace")
    assert "no cross-section" in log
    assert "[rivet].xsec" in log, "and it says what to do about it"


# ── the cache ────────────────────────────────────────────────────────────────

def test_two_seeds_compile_and_integrate_once(tmp_path_factory):
    """Building the matrix-element library is most of what a Whizard run costs (04 §1)."""
    root = tmp_path_factory.mktemp("whizard_seeds")
    config = write_config(root / "proj", card=TOY_CARD, card_name="toy.sin", events=20,
                          beams="11, -11", energies="[45.6, 45.6]", tag="91", xsec="1.0", seeds=True)
    results = root / "results"
    hep("run", str(config), "--study", "seeds", "--plain", results=results)

    names = sorted(entry.name for entry in points_root(results).iterdir() if entry.is_dir())
    assert len(names) == 2
    assert len(list(results.rglob("logs/whizard-integrate.log"))) == 1

    entries = list((results / "proj" / ".cache" / "whizard").iterdir())
    assert len(entries) == 1
    marker = json.loads((entries[0] / "prepared.json").read_text(encoding="utf-8"))
    assert marker["tool"] == "whizard" and marker["version"] == "3.1.8"
