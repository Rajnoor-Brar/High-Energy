"""`hep proc` end to end, and the fit overlay `hep plot` draws (P9-S01, 12 §2.1, 12 §3).

The unit tests in `tests/python/proc/` check that the fitters find the right answer. This one checks
the parts that only exist once there is a real result on disk:

  * a fit of a **finalized Rivet object**, which is a `BinnedEstimate1D` and not a `Histo1D` — its
    bins carry `val()` rather than `sumW()`, and must not be divided by the bin width. A fit that
    got that wrong would still converge, with an amplitude off by a constant factor;
  * `fits.json` carrying the provenance 12 §3 asks for: the backend that actually ran and the
    sha256 of every input;
  * **the overlay row** — `[plot].show_fits` puts `/PROC/<fit>/curve` on the figure its target is
    on, which means renaming it: a plotter overlays objects whose *paths* match, and
    `/PROC/peak/curve` matches nothing.

Marked `slow` because it generates a few hundred events first, and registered as the ctest test
`proc`.
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
CARD = REPO / "tests" / "golden" / "inputs" / "PhotoProduction" / "photo_ep.cmnd"
RUN = REPO / "build" / "bin" / "hep-run"
PLUGIN = REPO / "build" / "analyses" / "PhotoProduction" / "Rivet_photo_eic.so"

sys.path.insert(0, str(REPO / "utils" / "python"))

yoda = pytest.importorskip("yoda")
pytest.importorskip("scipy")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)"),
    pytest.mark.skipif(not PLUGIN.is_file(), reason="build the Rivet plugin first"),
]

TARGET = "/photo_eic/d01-x01-y01"


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


def config_with(directory: Path, block: str, *, show_fits: bool = False) -> Path:
    """The e2e config, with an absolute card and a `[[proc.fit]]` appended.

    The card path is made absolute because the copy lives somewhere else, and `project` is pinned so
    the copy writes into the same results tree the generation did.
    """
    text = CONFIG.read_text(encoding="utf-8")
    text = text.replace('card = "../golden/inputs/PhotoProduction/photo_ep.cmnd"',
                        f'card = "{CARD}"')
    text = text.replace("schema = 2", 'schema = 2\nproject = "e2e"', 1)
    if show_fits:
        text += "\n[plot]\nshow_fits = true\n"
    text += block
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "fitcfg.toml"
    path.write_text(text, encoding="utf-8")
    return path


FIT = f"""
[[proc.fit]]
name = "et_falloff"
target = "{TARGET}"
model = "expo"
range = [11.0, 40.0]
"""


@pytest.fixture(scope="module")
def produced(tmp_path_factory):
    """Generate once, then fit. Everything below reuses this."""
    root = tmp_path_factory.mktemp("proc")
    results = root / "results"
    hep("run", str(CONFIG), results=results)
    config = config_with(root / "cfg", FIT)
    done = hep("proc", str(config), results=results)
    study = next((results / "e2e" / "studies").iterdir())
    return results, config, study / "proc", done


def test_proc_writes_its_two_outputs(produced):
    _, _, proc_dir, done = produced
    assert (proc_dir / "fits.json").is_file(), done.text_stdout + done.text_stderr
    assert (proc_dir / "proc.yoda").is_file()


def test_the_fit_converged_on_a_finalized_estimate(produced):
    """A `BinnedEstimate1D`, fitted through `val()` — see the header note on the width trap."""
    _, _, proc_dir, _ = produced
    payload = json.loads((proc_dir / "fits.json").read_text(encoding="utf-8"))
    assert payload["fits"], "no fits were recorded"
    for entry in payload["fits"]:
        assert entry["valid"], entry["status"]
        assert entry["target"] == TARGET
        assert entry["model"] == "expo"
        assert entry["bins"]["used"] >= 5
        assert 0.0 < entry["chi2_per_ndf"] < 5.0
        # A falling E_T spectrum: the exponent must be negative and the amplitude positive.
        assert entry["params"]["slope"] < 0.0
        assert entry["params"]["amp"] > 0.0
        assert entry["errors"]["slope"] > 0.0


def test_the_amplitude_matches_the_histogram_it_was_fitted_to(produced):
    """The width trap, as a number.

    A finalized estimate is already in its own units; dividing by the bin width again would scale
    the fitted amplitude by 1/width — here a factor of two, since these bins are 2 GeV wide. So the
    fitted function is compared against the actual bin values it was fitted to.
    """
    results, _, proc_dir, _ = produced
    payload = json.loads((proc_dir / "fits.json").read_text(encoding="utf-8"))
    entry = payload["fits"][0]

    point = next((results / "e2e" / "points").iterdir())
    objects = yoda.read(str(point / "analysis.yoda"))
    estimate = objects[TARGET]

    amp, slope = entry["params"]["amp"], entry["params"]["slope"]
    inside = [b for b in estimate.bins() if 11.0 <= b.xMid() <= 40.0 and b.val() > 0]
    assert inside
    for entry_bin in inside[:4]:
        predicted = amp * pow(2.718281828459045, slope * entry_bin.xMid())
        # Within a factor of three of the bin it passes through: loose, because this is a two
        # parameter fit to a falling spectrum, and tight enough to catch a factor-of-width error.
        assert 1 / 3 < predicted / entry_bin.val() < 3, (
            f"bin at {entry_bin.xMid()}: fit says {predicted:.3g}, histogram says "
            f"{entry_bin.val():.3g}")


def test_fits_json_records_what_produced_it(produced):
    """12 §3: the backend that actually ran, and the hash of every input."""
    results, _, proc_dir, _ = produced
    payload = json.loads((proc_dir / "fits.json").read_text(encoding="utf-8"))
    provenance = payload["provenance"]
    assert provenance["backend"], "no backend recorded"
    assert provenance["inputs"], "no input hashes recorded"
    for name, digest in provenance["inputs"].items():
        assert len(digest) == 64, f"{name} has no sha256"
    assert isinstance(provenance["pyroot"], bool)


def test_the_curve_is_a_scatter_under_PROC(produced):
    """A fitted function has no bins; claiming bin contents it does not have would be a lie."""
    _, _, proc_dir, _ = produced
    objects = yoda.read(str(proc_dir / "proc.yoda"))
    assert objects
    for path, obj in objects.items():
        assert path.startswith("/PROC/")
        assert type(obj).__name__.startswith("Scatter")
        assert len(obj.points()) > 10


# ── Verification row: the overlay ────────────────────────────────────────────

def test_show_fits_puts_the_curve_on_its_targets_figure(produced, tmp_path):
    """The renaming row: `/PROC/<fit>/curve` becomes the target path, so a plotter overlays it."""
    from hekit.plot import fits as fits_module, io as io_module

    _, _, proc_dir, _ = produced
    destination = tmp_path / "fits.yoda"
    overlay = fits_module.overlay(
        proc_dir / "proc.yoda", on=[TARGET], destination=destination,
        targets=fits_module.targets_of(proc_dir / "fits.json"))

    assert overlay, "nothing was overlaid"
    assert overlay.path is not None and overlay.path.is_file()
    objects = io_module.read(overlay.path)
    assert objects
    # Every fit lands on the target's figure — `plot_key` strips the analysis option that keeps the
    # per-point curves distinct from one another.
    assert {io_module.plot_key(path) for path in objects} == {TARGET}
    assert len(objects) == len(overlay.names), "two points' fits collapsed into one"


def test_a_fit_for_another_page_is_skipped_not_misdrawn(produced, tmp_path):
    """`proc.yoda` holds a whole study's fits; a page only wants its own."""
    from hekit.plot import fits as fits_module

    _, _, proc_dir, _ = produced
    overlay = fits_module.overlay(
        proc_dir / "proc.yoda", on=["/photo_eic/d99-x01-y01"], destination=tmp_path / "f.yoda",
        targets=fits_module.targets_of(proc_dir / "fits.json"))
    assert not overlay
    assert overlay.skipped and "not on this page" in overlay.skipped[0]


def test_hep_plot_draws_with_show_fits(produced, tmp_path):
    """The command itself, with the option on, through the mpl backend."""
    results, _, _, _ = produced
    config = config_with(tmp_path / "cfg", FIT, show_fits=True)
    done = hep("plot", str(config), "--backend", "mpl", results=results)
    assert "curves" in done.text_stdout, done.text_stdout + done.text_stderr

    pages = next((results / "e2e" / "studies").iterdir()) / "plots"
    drawn = list(pages.rglob("photo_eic_d01-x01-y01.png"))
    assert drawn, "the target's figure was not drawn"
    assert drawn[0].stat().st_size > 0


# ── what a mistake costs ─────────────────────────────────────────────────────

def test_a_target_that_is_not_there_lists_what_is(produced, tmp_path):
    results, _, _, _ = produced
    config = config_with(tmp_path / "bad", """
[[proc.fit]]
name = "nowhere"
target = "/photo_eic/d99-x01-y01"
model = "expo"
""")
    done = hep("proc", str(config), results=results, expect=None)
    assert done.returncode != 0
    assert "has no object at" in done.text_stderr
    assert "d01-x01-y01" in done.text_stderr, "it should say what is there"


def test_only_selects_one_fit(produced, tmp_path):
    results, _, _, _ = produced
    config = config_with(tmp_path / "only", FIT + """
[[proc.fit]]
name = "second"
target = "/photo_eic/d02-x01-y01"
model = "expo"
""")
    done = hep("proc", str(config), "--only", "second", results=results)
    assert "second" in done.text_stdout
    assert "et_falloff" not in done.text_stdout

    missing = hep("proc", str(config), "--only", "nosuchfit", results=results, expect=None)
    assert missing.returncode != 0
    assert "et_falloff" in missing.text_stderr, "it should list the names there are"
