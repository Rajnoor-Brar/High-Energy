"""One generation, several analysis variants, several curves (P6-S02, 03 §4).

The rule is simple and the saving is large: an **analysis** option does not change the events, so
scanning one must not generate the events again. `photo_eic:R=0.4` and `photo_eic:R=1.0` are two
analyses of the same shower, so the radius study is *one* generation with both analyses booked in one
Rivet analyzer, and the two curves are two object paths inside one YODA.

Every layer of that has unit tests already — the sweep groups the points, the analyzer books both
variants, the plotter turns a variant into a curve. What had no test is the chain: that `hep run`
followed by `hep plot` on a real study really does generate once and draw twice. That is what this
file is, and it is the only place where the saving is actually observed rather than asserted about a
data structure.

Marked `slow` and registered as the ctest test `event_groups`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "tests" / "e2e" / "mini.toml"
RUN = REPO / "build" / "bin" / "hep-run"
PLUGIN = REPO / "build" / "analyses" / "PhotoProduction" / "Rivet_photo_eic.so"

yoda = pytest.importorskip("yoda")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)"),
    pytest.mark.skipif(not PLUGIN.is_file(), reason="build the Rivet plugin first"),
]

#: `[study.radius]` of the e2e config: two radii, pinned to one PDF so only the option varies.
VARIANTS = ["photo_eic:R=0.4", "photo_eic:R=1.0"]
POINTS = ["mini_27x920_MSTW08lo_r04", "mini_27x920_MSTW08lo_r10"]
GENERATION = "mini_27x920_MSTW08lo"


def hep(*arguments: str, results: Path, timeout: int = 1800, expect: int | None = 0):
    done = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(REPO / 'utils' / 'python')!r});"
         f" from hekit.cli import main; raise SystemExit(main({list(arguments)!r}))"],
        cwd=REPO, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
        env=dict(os.environ, HEKIT_RESULTS=str(results)))
    done.text_stdout = done.stdout.decode("utf-8", errors="replace")
    done.text_stderr = done.stderr.decode("utf-8", errors="replace")
    if expect is not None:
        assert done.returncode == expect, done.text_stdout + done.text_stderr
    return done


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    """The radius study, run once."""
    results = tmp_path_factory.mktemp("groups") / "results"
    done = hep("run", str(CONFIG), "--study", "radius", "--plain", results=results)
    return done, results


def points_root(results: Path) -> Path:
    # The results tree is keyed by *project* (the config's directory), not by `[run].name`.
    return results / "e2e" / "points"


# ── the plan row ─────────────────────────────────────────────────────────────

def test_the_plan_is_one_group_with_every_variant(tmp_path):
    """The step's row: 1 group, both variants, and the point names kept as its aliases."""
    results = tmp_path / "results"
    done = hep("plan", str(CONFIG), "--study", "radius", "--json", results=results)
    plan = json.loads(done.text_stdout)

    assert len(plan["groups"]) == 1, "an analysis option is not a separate generation (03 §4)"
    group = plan["groups"][0]
    assert group["name"] == GENERATION
    assert group["analyses"] == VARIANTS
    assert sorted(group["aliases"]) == POINTS, "both points resolve to the one generation"
    assert [point["name"] for point in plan["points"]] == POINTS
    assert {point["group"] for point in plan["points"]} == {GENERATION}


def test_a_generator_study_is_not_grouped(tmp_path):
    """The control. Otherwise "one group" could just mean the planner groups everything."""
    results = tmp_path / "results"
    done = hep("plan", str(CONFIG), "--study", "pdf", "--json", results=results)
    plan = json.loads(done.text_stdout)
    assert len(plan["groups"]) == len(plan["points"]) == 2, "a PDF change is a different shower"


# ── the output row ───────────────────────────────────────────────────────────

def test_one_directory_holds_both_variants(ran):
    """The saving, observed: two points, one point directory, one set of events."""
    _, results = ran
    directories = sorted(entry.name for entry in points_root(results).iterdir() if entry.is_dir())
    assert directories == [GENERATION], directories


def test_the_yoda_carries_a_path_per_variant(ran):
    """The step's row: `/photo_eic:R=0.4/...` is present, and so is the other one."""
    _, results = ran
    objects = yoda.read(str(points_root(results) / GENERATION / "analysis.yoda"))
    found = sorted({path.split("/")[1] for path in objects if path.startswith("/photo_eic")})
    assert found == VARIANTS, found
    # Both variants filled real histograms, rather than one being booked and left empty.
    for variant in VARIANTS:
        filled = [path for path in objects
                  if path.startswith(f"/{variant}/") and not path.startswith("/RAW")]
        assert filled, f"{variant} booked nothing"


def test_the_events_were_generated_once(ran):
    """One σ and one event count for the generation, not one per variant."""
    _, results = ran
    summary = json.loads(
        (points_root(results) / GENERATION / "run.summary.json").read_text(encoding="utf-8"))
    assert summary["run"]["events"] > 0
    objects = yoda.read(str(points_root(results) / GENERATION / "analysis.yoda"))
    assert objects["/_EVTCOUNT"].val() == pytest.approx(summary["run"]["events"])


# ── the plot row ─────────────────────────────────────────────────────────────

def test_the_page_draws_one_curve_per_variant(ran, tmp_path):
    """The step's row: two curves, out of the one file the one generation wrote."""
    _, results = ran
    done = hep("plot", str(CONFIG), "--study", "radius", results=results)
    text = done.text_stdout + done.text_stderr
    assert "2 curves" in text, text[-2000:]

    pages = list((results / "e2e").rglob("*_by_radius*"))
    assert pages, "the radius page was not written"
