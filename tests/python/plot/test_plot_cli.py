"""`hep plot`'s own decisions: which pages, where they go, and the argv it builds (P4-S02).

Drawing is `rivet-mkhtml`'s job and is checked end to end in `tests/integration/test_plot_vs_legacy.py`;
what is worth testing quickly is everything around it — page selection, the output directory, the
legend subtlety a hidden reference introduces, and that `--suggest-data-map` suggests rather than acts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hekit.plot import page as page_module
from hekit.plot.backends import mkhtml
from hekit.plot.cli import _pages, _study_plots
from hekit.plot.select import Curve
from hekit.results import Layout

yoda = pytest.importorskip("yoda")


def a_page(tmp_path: Path, *, legends=("MSTW", "NNPDF23")) -> page_module.Page:
    curves = []
    for name in legends:
        path = tmp_path / f"{name}.yoda"
        estimate = yoda.BinnedEstimate1D([0.0, 1.0, 2.0], f"/photo_eic/d01-x01-y01")
        estimate.bin(1).setVal(1.0)
        yoda.write([estimate], str(path))
        curves.append(Curve(name=name, path=path, analysis="photo_eic", legend=name))
    return page_module.Page(name="by_pdf", analysis="photo_eic", curves=curves, workdir=tmp_path)


# ── the argv ─────────────────────────────────────────────────────────────────

def test_curves_carry_their_titles(tmp_path):
    arguments = mkhtml.arguments(a_page(tmp_path))
    assert arguments[:2] == ["--rmopts", "--no-rivet-refs"]
    assert arguments[2].endswith("MSTW.yoda:Title=MSTW")
    assert arguments[3].endswith("NNPDF23.yoda:Title=NNPDF23")


def test_rivet_reference_data_is_off_unless_asked_for(tmp_path):
    """Rivet's own reference data is for published analyses; a project analysis has none."""
    assert "--no-rivet-refs" in mkhtml.arguments(a_page(tmp_path))
    assert "--no-rivet-refs" not in mkhtml.arguments(a_page(tmp_path), rivet_refs=True)


def test_a_colon_in_a_legend_does_not_break_the_argument(tmp_path):
    page = a_page(tmp_path)
    page.curves[0].legend = "photo_eic:R=0.4"
    argument = mkhtml.arguments(page)[2]
    assert argument.count(":Title=") == 1
    assert argument.endswith("Title=photo_eic R=0.4"), "the colon becomes a space, as ydmrg did"


def test_a_hidden_reference_keeps_the_legend_labels_aligned(tmp_path):
    """A reference kept as the ratio denominator but not drawn still owns a legend entry, which
    would shift every label by one; the curves are named and `LegendOnly` lists them."""
    from hekit.plot import data as data_module

    page = a_page(tmp_path)
    reference = yoda.BinnedEstimate1D([0.0, 1.0, 2.0], "/REF/photo_eic/d01-x01-y01")
    reference.setAnnotation("IsRef", 1)
    reference.setAnnotation("MainPanel", 0)
    path = tmp_path / "data.yoda"
    yoda.write([reference], str(path))
    page.data = data_module.DataOverlay(path=path, mapped={"d01-x01-y01": "x"})

    arguments = mkhtml.arguments(page)
    assert arguments[-1] == "PLOT:LegendOnly=curve1 curve2"
    # `--reflabel Data` comes before the inputs, so the curves are found rather than indexed.
    named = [entry for entry in arguments if ":Name=curve" in entry]
    assert len(named) == 2 and ":Name=curve1" in named[0] and ":Name=curve2" in named[1]


def test_a_drawn_reference_needs_no_legend_trick(tmp_path):
    from hekit.plot import data as data_module

    page = a_page(tmp_path)
    reference = yoda.BinnedEstimate1D([0.0, 1.0, 2.0], "/REF/photo_eic/d01-x01-y01")
    reference.setAnnotation("IsRef", 1)
    path = tmp_path / "data.yoda"
    yoda.write([reference], str(path))
    page.data = data_module.DataOverlay(path=path, mapped={"d01-x01-y01": "x"})

    arguments = mkhtml.arguments(page, data_legend="ZEUS")
    assert "--reflabel" in arguments and arguments[arguments.index("--reflabel") + 1] == "ZEUS"
    assert not any(entry.startswith("PLOT:LegendOnly") for entry in arguments)


def test_the_command_reads_the_plot_files_in_order(tmp_path):
    """The project's `.plot` first, the auto-range after it, so only XMin/XMax are overridden."""
    page = a_page(tmp_path)
    page.plot_file = tmp_path / "photo_eic.plot"
    page.ranges = tmp_path / "auto_range.plot"
    line = mkhtml.command(page, tmp_path / "out")
    assert line[:3] == [mkhtml.TOOL, "-o", str(tmp_path / "out")]
    assert line.index(str(page.plot_file)) < line.index(str(page.ranges))


def test_the_environment_is_private(tmp_path):
    environment = mkhtml.environment(analysis_paths=[tmp_path], run="page")
    assert environment["RIVET_ANALYSIS_PATH"].startswith(str(tmp_path))
    assert "output/scratch/mpl" in environment["MPLCONFIGDIR"], "no racing on $HOME (00/B19)"


# ── page selection ───────────────────────────────────────────────────────────

class FakePoint:
    def __init__(self, name):
        self.name = name
        self.suffix = name
        self.legend = name.upper()


class FakePlan:
    def __init__(self):
        self.points = [FakePoint("a"), FakePoint("b")]
        self.pages = [type("Page", (), {"name": "by_pdf", "suffix": "by_pdf",
                                        "members": self.points,
                                        "legends": ["A", "B"]})()]


def test_pages_come_from_the_plan_by_default():
    plan = FakePlan()
    assert [page.name for page in _pages(plan, per_point=False)] == ["by_pdf"]


def test_points_flag_makes_one_page_per_point():
    """`ydplt`'s job: a single point is a page with one curve, and nothing else changes."""
    pages = _pages(FakePlan(), per_point=True)
    assert [page.name for page in pages] == ["a", "b"]
    assert all(len(page.members) == 1 for page in pages)
    assert pages[0].legends == ["A"]


def test_pages_go_next_to_the_manifest_of_the_run(redirect_results, tmp_path):
    """07 §1: `studies/<run>/plots/<page>/`, beside the manifest that lists the points."""
    class Config:
        project = "Demo"
        output = type("O", (), {"root": ""})()
        run = type("R", (), {"serial": True})()

    layout = Layout(root=redirect_results / "Demo", project="Demo")
    plan = type("P", (), {"study": "pdf", "config": Config()})()
    first = _study_plots(layout, plan)
    assert first.parent.name == "01_pdf" and first.name == "plots"
    assert _study_plots(layout, plan) == first, "a second plot run reuses the same study directory"
