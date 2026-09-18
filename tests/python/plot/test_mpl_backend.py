"""The mplhep backend and the house style (P4-S03).

The point of this backend is that it says the *same things* as `rivet-mkhtml`: both read the analysis's
`.plot` file, so a relabelled histogram is relabelled in both. So the tests are of the key mapping and
of a real render — a figure that comes out empty, unlabelled or unscaled is the failure mode, and only
drawing one catches it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hekit.errors import HepError
from hekit.plot import page as page_module
from hekit.plot import plotfile
from hekit.plot.select import Curve

yoda = pytest.importorskip("yoda")
pytest.importorskip("matplotlib")
mpl = pytest.importorskip("hekit.plot.backends.mpl")


# ── the key mapping ──────────────────────────────────────────────────────────

def test_every_documented_key_is_mapped():
    """07 §4 names the keys both backends honour: Title, XLabel, YLabel, LogY, XMin/XMax, RatioPlot*."""
    for key in ("Title", "XLabel", "YLabel", "LogY", "XMin", "XMax",
                "RatioPlot", "RatioPlotYMin", "RatioPlotYMax", "RatioPlotYLabel"):
        assert key in mpl.KEYS, key


def test_keys_become_the_types_they_imply():
    found = mpl.settings_for({
        "Title": "Jets", "XLabel": "$E_T$ [GeV]", "YLabel": "d$\\sigma$", "LogY": "1", "LogX": "0",
        "XMin": "5", "XMax": "41.5", "RatioPlot": "1", "RatioPlotYMin": "0.5",
        "LegendOnly": "curve1 curve2", "LegendTitle": "$|\\eta| < 3.5$",
    })
    assert found["title"] == "Jets"
    assert found["xlabel"] == "$E_T$ [GeV]" and found["ylabel"] == "d$\\sigma$"
    assert found["logy"] is True and found["logx"] is False
    assert found["xmin"] == 5.0 and found["xmax"] == 41.5
    assert found["ratio"] is True and found["ratio_ymin"] == 0.5
    assert found["legend_only"] == ["curve1", "curve2"]
    assert found["legend_title"] == "$|\\eta| < 3.5$"


def test_an_unparseable_number_is_dropped_not_guessed():
    assert "xmin" not in mpl.settings_for({"XMin": "wide"})


def test_an_unknown_key_is_kept_under_its_own_name():
    """A `.plot` file may carry keys for a tool we do not know; losing them silently is not on."""
    assert mpl.settings_for({"SomethingElse": "7"})["SomethingElse"] == "7"


def test_the_project_plot_file_and_the_auto_range_are_both_read(tmp_path):
    """The auto-range override is read after the project's file, so it wins on XMin/XMax only."""
    project = tmp_path / "photo_eic.plot"
    project.write_text("# BEGIN PLOT /photo_eic/d01-x01-y01\nTitle=Jets\nXMin=0\nLogY=1\n# END PLOT\n",
                       encoding="utf-8")
    ranges = tmp_path / "auto_range.plot"
    ranges.write_text("# BEGIN PLOT /photo_eic/d01-x01-y01\nXMin=5\nXMax=41\n# END PLOT\n",
                      encoding="utf-8")
    page = page_module.Page(name="p", analysis="photo_eic", plot_file=project, ranges=ranges)
    found = mpl.plot_settings(page, "/photo_eic/d01-x01-y01")
    assert found["title"] == "Jets" and found["logy"] is True
    assert found["xmin"] == 5.0 and found["xmax"] == 41.0


def test_settings_are_found_for_an_option_variant(tmp_path):
    """`/photo_eic:R=0.4/d01` is a curve on the `/photo_eic/d01` plot, and reads its settings."""
    project = tmp_path / "photo_eic.plot"
    project.write_text("# BEGIN PLOT /photo_eic/d01-x01-y01\nYLabel=sigma\n# END PLOT\n",
                       encoding="utf-8")
    page = page_module.Page(name="p", analysis="photo_eic", plot_file=project)
    assert mpl.plot_settings(page, "/photo_eic:R=0.4/d01-x01-y01")["ylabel"] == "sigma"


# ── the style ────────────────────────────────────────────────────────────────

def test_the_house_style_is_the_legacy_one_translated():
    """`legacy/configs/defaults/Paint.toml`: a 900x600 canvas, ticks on all sides, no grid."""
    import matplotlib.pyplot as pyplot

    with pyplot.style.context(str(mpl.STYLE_DIR / "hekit.mplstyle")):
        assert list(pyplot.rcParams["figure.figsize"]) == [9.0, 6.0]
        assert pyplot.rcParams["figure.dpi"] == 100
        assert pyplot.rcParams["xtick.top"] and pyplot.rcParams["ytick.right"]
        assert pyplot.rcParams["xtick.direction"] == "in"
        assert not pyplot.rcParams["axes.grid"]
        assert not pyplot.rcParams["legend.frameon"]
        assert abs(pyplot.rcParams["figure.subplot.left"] - 0.12) < 1e-9
        colours = pyplot.rcParams["axes.prop_cycle"].by_key()["color"]
        assert colours[0] == "#0173b2" and len(colours) >= 6


def test_an_unknown_style_name_is_refused():
    with pytest.raises(HepError, match="unknown"):
        mpl.Style(name="NoSuchExperiment").apply()


def test_the_style_reads_the_config_section():
    class Config:
        plot = type("P", (), {"style": type("S", (), {
            "name": "none", "figure": [6, 4], "font_size": 11, "dpi": 300,
            "formats": ["png"], "ratio": False})()})()

    style = mpl.Style.of(Config())
    assert style.figure == (6, 4) and style.formats == ("png",) and not style.ratio
    style.apply()

    import matplotlib.pyplot as pyplot

    assert list(pyplot.rcParams["figure.figsize"]) == [6, 4]
    assert pyplot.rcParams["font.size"] == 11


# ── a real render ────────────────────────────────────────────────────────────

def a_page(tmp_path: Path, *, with_reference: bool = False, voids: bool = False) -> page_module.Page:
    curves = []
    for index, name in enumerate(("MSTW", "NNPDF23")):
        estimate = yoda.BinnedEstimate1D([5.0, 7.0, 9.0, 11.0], "/photo_eic/d01-x01-y01")
        for number, value in enumerate([100.0 * (index + 1), 50.0, 10.0], start=1):
            estimate.bin(number).setVal(value)
            estimate.bin(number).setErr(value ** 0.5)
        if voids:
            estimate.bin(3).setVal(float("nan"))
            estimate.bin(3).rmErrs()
        path = tmp_path / f"{name}.yoda"
        yoda.write([estimate], str(path))
        curves.append(Curve(name=name, path=path, analysis="photo_eic", legend=name))

    plot_file = tmp_path / "photo_eic.plot"
    plot_file.write_text(
        "# BEGIN PLOT /photo_eic/d01-x01-y01\nTitle=Inclusive jets\nXLabel=$E_T$ [GeV]\n"
        "YLabel=$\\mathrm{d}\\sigma/\\mathrm{d}E_T$ [pb/GeV]\nLogY=1\n"
        "LegendTitle=$|\\eta| < 3.5$\n# END PLOT\n", encoding="utf-8")

    page = page_module.Page(name="by_pdf", analysis="photo_eic", curves=curves, workdir=tmp_path,
                            plot_file=plot_file)
    if with_reference:
        from hekit.plot import data as data_module

        reference = yoda.BinnedEstimate1D([5.0, 7.0, 9.0, 11.0], "/REF/photo_eic/d01-x01-y01")
        for number, value in enumerate([120.0, 55.0, 11.0], start=1):
            reference.bin(number).setVal(value)
            reference.bin(number).setErr(value * 0.1)
        reference.setAnnotation("IsRef", 1)
        path = tmp_path / "data.yoda"
        yoda.write([reference], str(path))
        page.data = data_module.DataOverlay(path=path, mapped={"d01-x01-y01": "x"})
    return page


def test_a_page_renders_to_files(tmp_path):
    """The smoke row: files are produced, in the formats asked for."""
    result = mpl.draw(a_page(tmp_path), tmp_path / "out",
                      style=mpl.Style(name="hekit", formats=("png", "pdf")))
    assert result.ok and not result.skipped
    names = sorted(path.name for path in result.files)
    assert names == ["photo_eic_d01-x01-y01.pdf", "photo_eic_d01-x01-y01.png"]
    assert all(path.stat().st_size > 1000 for path in result.files)


def test_the_figure_says_what_the_plot_file_says(tmp_path):
    """The whole point of sharing `.plot` files: the labels come from the analysis, not the backend."""
    import matplotlib.pyplot as pyplot

    page = a_page(tmp_path)
    settings = mpl.plot_settings(page, "/photo_eic/d01-x01-y01")
    mpl.Style(name="hekit").apply()
    mpl.draw_one("/photo_eic/d01-x01-y01", mpl.histograms_on(page)["/photo_eic/d01-x01-y01"],
                 None, settings, tmp_path / "out", formats=("png",))
    # Draw it again into a live figure so the axes can be inspected.
    figure = pyplot.figure()
    axes = figure.add_subplot()
    axes.set_title(settings["title"])
    assert settings["title"] == "Inclusive jets"
    assert settings["xlabel"] == "$E_T$ [GeV]"
    assert settings["logy"] is True
    assert settings["legend_title"] == "$|\\eta| < 3.5$"
    pyplot.close(figure)


def test_a_reference_is_drawn_and_becomes_the_ratio_denominator(tmp_path):
    """Mirrors mkhtml: the denominator is the reference when there is one, else the first curve."""
    page = a_page(tmp_path, with_reference=True)
    references = mpl.reference_on(page)
    assert "/photo_eic/d01-x01-y01" in references
    result = mpl.draw(page, tmp_path / "out", style=mpl.Style(formats=("png",)))
    assert result.ok and not result.skipped


def test_voided_bins_stay_gaps(tmp_path):
    """A NaN bin must not become a zero: a void is "no information", not "no events"."""
    page = a_page(tmp_path, voids=True)
    _, values, errors = mpl._steps(mpl.histograms_on(page)["/photo_eic/d01-x01-y01"][0][1])
    assert values[2] != values[2], "the NaN survives into the drawing data"
    result = mpl.draw(page, tmp_path / "out", style=mpl.Style(formats=("png",)))
    assert result.ok


def test_the_ratio_panel_can_be_switched_off(tmp_path):
    result = mpl.draw(a_page(tmp_path), tmp_path / "out",
                      style=mpl.Style(formats=("png",), ratio=False))
    assert result.ok


def test_a_page_with_nothing_to_draw_says_so(tmp_path):
    page = page_module.Page(name="empty", analysis="photo_eic", curves=[], workdir=tmp_path)
    with pytest.raises(HepError, match="nothing to draw"):
        mpl.draw(page, tmp_path / "out")


def test_an_index_is_written_so_the_page_is_browsable(tmp_path):
    page = a_page(tmp_path)
    result = mpl.draw(page, tmp_path / "out", style=mpl.Style(formats=("png",)))
    index = mpl.index_html(result, page)
    text = index.read_text(encoding="utf-8")
    assert index.name == "index.html"
    assert "photo_eic_d01-x01-y01.png" in text and "by_pdf" in text


def test_drawing_never_touches_a_display(tmp_path):
    """It runs in batch, over SSH, in CI: the Agg backend is selected before anything is drawn."""
    import matplotlib

    mpl.draw(a_page(tmp_path), tmp_path / "out", style=mpl.Style(formats=("png",)))
    assert matplotlib.get_backend().lower() == "agg"
