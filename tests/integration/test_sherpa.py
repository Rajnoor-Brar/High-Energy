"""A real Sherpa point through `hep run` (P7-S03, 04 §4).

Sherpa 3.0.5 is installed on this machine, so this runs it: integrate, generate into the FIFO, and
analyse with the project's own Rivet plugin. Skipped cleanly where it is not.

What makes the checks worth something rather than "a process exited 0":

* the two **modes** must agree. `inprocess` reads the FIFO with `Source::Stream` and `native` lets
  Sherpa run Rivet itself — different code on both sides of the seam — and at a fixed seed they see
  the same events, so σ must come out the same number;
* the **cache** must turn two seeds into one integration, which is most of what a Sherpa run costs;
* and the events must reach the analysis, which is what `photo_eic` histograms being filled shows.

Marked `slow` and registered as the ctest test `sherpa`. Integration takes ~75 s, so the fixture runs
it once and shares it.
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
CARD = REPO / "configs" / "PhotoProduction" / "photo_ep.sherpa.yaml"

EVENTS = 200
SEED = 7001

yoda = pytest.importorskip("yoda")
pytest.importorskip("yaml")

SHERPA = shutil.which("Sherpa") or str(Path.home() / "HEP" / "install" / "sherpa" / "bin" / "Sherpa")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)"),
    pytest.mark.skipif(not (PLUGIN / "Rivet_photo_eic.so").is_file(),
                       reason="build the Rivet plugin first"),
    pytest.mark.skipif(not Path(SHERPA).is_file(), reason="Sherpa is not installed"),
    pytest.mark.skipif(not CARD.is_file(), reason="the Sherpa base card is missing"),
]


def hep(*arguments: str, results: Path, expect: int = 0, timeout: int = 1800):
    done = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(REPO / 'utils' / 'python')!r});"
         f" from hekit.cli import main; raise SystemExit(main({list(arguments)!r}))"],
        cwd=REPO, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
        env=dict(os.environ, HEKIT_RESULTS=str(results),
                 PATH=f"{Path(SHERPA).parent}:{os.environ.get('PATH', '')}"))
    done.text = done.stdout.decode("utf-8", errors="replace") + \
        done.stderr.decode("utf-8", errors="replace")
    assert done.returncode == expect, done.text[-4000:]
    return done


def write_config(directory: Path, *, mode: str = "inprocess", seeds: bool = False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CARD, directory / CARD.name)
    text = f'''schema = 2

[run]
name = "sh"
events = {EVENTS}
seed = {SEED}
threads = 1

[generator]
tool = "sherpa"
card = "{CARD.name}"

[beams]
ids = [2212, 11]

[rivet]
analyses = ["photo_eic"]
paths = ["{PLUGIN}"]
mode = "{mode}"

[output]
tag_style = "tag"

[settle.use]
energies = "18x275"

[quantity.energies]
type = "energies"
values = [[275.0, 18.0]]
labels = ["18x275 GeV"]
tags = ["18x275"]
use = 1

[study.one]
description = "one Sherpa point"
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
    path = directory / "sh.toml"
    path.write_text(text, encoding="utf-8")
    return path


def points_root(results: Path) -> Path:
    return results / "proj" / "points"


def read_yoda(directory: Path):
    for name in ("analysis.yoda", "analysis.yoda.gz"):
        if (directory / name).is_file():
            return yoda.read(str(directory / name))
    raise AssertionError(f"no YODA in {directory}: {sorted(p.name for p in directory.iterdir())}")


@pytest.fixture(scope="module")
def inprocess(tmp_path_factory):
    """One point, events through the FIFO into `hep-run`."""
    root = tmp_path_factory.mktemp("sherpa")
    config = write_config(root / "proj")
    results = root / "results"
    hep("run", str(config), "--plain", results=results)
    return results


# ── the point row ────────────────────────────────────────────────────────────

def test_the_plan_is_integrate_generate_analyse():
    """04 §4's chain. `hep-run` is last because it is the one counting events."""
    import tempfile

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        config = write_config(root / "proj")
        done = hep("plan", str(config), "--json", results=root / "results")
        plan = json.loads(done.stdout.decode("utf-8", errors="replace"))
        group = plan["groups"][0]
        assert group["stages"] == ["sherpa-integrate", "sherpa-generate", "hep-run"]
        assert group["spec"]["source"]["kind"] == "stream"


def test_a_sherpa_point_produces_a_yoda(inprocess):
    """The step's row. Every event asked for arrives, and the analysis sees them."""
    directory = points_root(inprocess) / "sh_18x275"
    summary = json.loads((directory / "run.summary.json").read_text(encoding="utf-8"))["run"]
    assert summary["source"] == "stream"
    assert summary["events"] == EVENTS

    objects = read_yoda(directory)
    filled = [path for path in objects if path.startswith("/photo_eic/")]
    assert filled, "the analysis booked nothing"
    assert objects["/_XSEC"].val() > 0


def test_the_card_that_ran_is_on_disk(inprocess):
    """Sherpa would take `'KEY: value'` arguments; a card that is not the card that ran is no use."""
    import yaml

    card = points_root(inprocess) / "sh_18x275" / "point.yaml"
    document = yaml.safe_load(card.read_text(encoding="utf-8"))
    assert document["BEAMS"] == [2212, 11]
    assert document["RANDOM_SEED"] > 0
    assert document["EVENTS"] == EVENTS
    assert document["MPI_PDF_SET"] == document["PDF_SET"], "or Sherpa dies on a default PDF"


def test_the_progress_parser_read_sherpas_log(inprocess):
    """06 §4's table, calibrated on a real log rather than on the manual."""
    from hekit.run.parsers import parser_for

    log = (points_root(inprocess) / "sh_18x275" / "logs" / "sherpa-generate.log")
    text = log.read_text(encoding="utf-8", errors="replace")
    parser = parser_for("sherpa")
    seen = [found.events for found in (parser.feed(line) for line in text.splitlines())
            if found.events is not None]
    assert seen, "no progress was parsed out of Sherpa's own output"
    assert max(seen) <= EVENTS


# ── the cache row ────────────────────────────────────────────────────────────

def test_two_seeds_integrate_once(tmp_path_factory):
    """The step's row, and most of what a Sherpa run costs (04 §1)."""
    root = tmp_path_factory.mktemp("sherpa_seeds")
    config = write_config(root / "proj", seeds=True)
    results = root / "results"
    hep("run", str(config), "--study", "seeds", "--plain", results=results)

    names = sorted(entry.name for entry in points_root(results).iterdir() if entry.is_dir())
    assert names == ["sh_18x275_s5", "sh_18x275_s6"]

    integrations = list(results.rglob("logs/sherpa-integrate.log"))
    assert len(integrations) == 1, f"integrated {len(integrations)} times"

    entries = list((results / "proj" / ".cache" / "sherpa").iterdir())
    assert len(entries) == 1
    marker = json.loads((entries[0] / "prepared.json").read_text(encoding="utf-8"))
    assert marker["tool"] == "sherpa" and marker["version"]
    assert (entries[0] / "Results.zip").is_file(), "the grid itself"

    # Different seeds really did generate different events.
    first, second = (json.loads((points_root(results) / name / "run.summary.json")
                                .read_text(encoding="utf-8"))["run"] for name in names)
    assert first["events"] == second["events"] == EVENTS
    assert first["xsec_pb"] != second["xsec_pb"]


# ── the modes row ────────────────────────────────────────────────────────────

def test_native_mode_agrees_with_in_process(inprocess, tmp_path_factory):
    """Different code on both sides of the seam, the same events, so the same σ.

    `native` lets Sherpa run Rivet itself and write a gzipped YODA; `inprocess` sends the events
    through a FIFO into `hep-run`'s own Rivet sink. At a fixed seed they must agree on the number the
    whole analysis is normalised by.
    """
    root = tmp_path_factory.mktemp("sherpa_native")
    config = write_config(root / "proj", mode="native")
    results = root / "results"
    hep("run", str(config), "--plain", results=results)

    directory = points_root(results) / "sh_18x275"
    assert not (directory / "events.hepmc").exists() or (directory / "events.hepmc").is_fifo()
    native = read_yoda(directory)
    streamed = read_yoda(points_root(inprocess) / "sh_18x275")

    assert native["/_XSEC"].val() == pytest.approx(streamed["/_XSEC"].val(), rel=1e-6)
    assert [path for path in native if path.startswith("/photo_eic/")], "native booked nothing"


def test_native_mode_has_no_hep_run_stage(tmp_path):
    """Nothing is reading a FIFO, so there is nothing for `hep-run` to do (04 §4)."""
    config = write_config(tmp_path / "proj", mode="native")
    done = hep("plan", str(config), "--json", results=tmp_path / "results")
    plan = json.loads(done.stdout.decode("utf-8", errors="replace"))
    assert plan["groups"][0]["stages"] == ["sherpa-integrate", "sherpa-generate"]
