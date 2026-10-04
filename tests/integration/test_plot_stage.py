"""The plot stage end to end on fake complete points (P3 S2 rows 1 and 4).

Four points (lepton × pdf) whose products are the two legacy mini YODAs; plot_points = lepton, so
two pages per object with two curves each. Reference data are mapped for d01 only.
"""

from __future__ import annotations

import shutil
import sys
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from runner import labels, plot, quantities, record, sweep, tools

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "runner"))
from helpers import parse, raw  # noqa: E402
LEGACY = REPO / "tests" / "reference" / "legacy_run"
BUILT = all((REPO / "build" / name).exists() for name in ("Paint.exe", "App_yd2rt.exe"))

pytestmark = pytest.mark.skipif(not BUILT, reason="make utils/Apps/Paint.exe utils/App_yd2rt.exe")


@pytest.fixture
def stage(scratch, request):
    backend = getattr(request, "param", "root")
    data = raw(run__name=f"plotstage_{backend}", run__one__sweeps=["lepton", "pdf"], run__one__plot_points=["lepton"],
               quantities__lepton={"key": {"pythia": "Beams:idB"}, "values": [11, -11], "tags": ["em", "ep"]},
               quantities__pdf__labels=["MSTW 2008 LO", "NNPDF 2.3 LO"],
               plot={"backend": backend, "formats": ["png"], "ratio": True, "min_entries": 10, "range_pad": 1,
                     "data": {"file": "./tests/reference/legacy_run/ydmrg/photo_eic_data.yoda", "legend": "legacy",
                              "map": {"d01-x01-y01": "/REF/photo_eic/d01-x01-y01"}},
                     "style": {"page": {"dpi": 100}},
                     "figures": {"d04": {"objects": ["d04-*"], "logy": True, "y_gutter": 3.0, "title": "override",
                                         "style": {"legend": {"position": "top-left"}}}}})
    run = parse(data, scratch)
    configuration = run.configuration(None)
    return run, configuration, completed(run, configuration)


def completed(run, configuration) -> list:
    """The configuration's points planned, each with a legacy mini YODA as its product, complete."""
    master = quantities.load_master(run.project, run.master_toml)
    plans = []
    for point in sweep.points(run, configuration):
        plan = tools.plan_point(run, configuration, point, master)
        plan.identity = record.identity(plan)
        plans.append(plan)
    for plan in plans:
        shutil.rmtree(plan.res, ignore_errors=True)
        shutil.rmtree(plan.out, ignore_errors=True)
        source = LEGACY / ("mini_27x920_ep_MSTW.yoda" if "MSTW" in plan.point.name else "mini_27x920_ep_NNLO.yoda")
        product = plot.yoda_of(plan)
        product.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, product)
        record.complete_marker(plan).parent.mkdir(parents=True, exist_ok=True)
        record.complete_marker(plan).write_text(plan.identity + "\n")
    shutil.rmtree(plans[0].res.parent / "plots", ignore_errors=True)
    return plans


def test_pages_are_plot_points_by_objects(stage):
    run, configuration, plans = stage
    pages = plot.pages(run, configuration, plans)
    assert len(pages) == 2 * 17
    assert {p.name.split("/")[0] for p in pages} == {"em", "ep"}
    first = tomllib.loads(pages[0].config.read_text())
    assert [c["label"] for c in first["curve"]] == ["MSTW 2008 LO", "NNPDF 2.3 LO"]
    assert first["page"]["min_entries"] == 10 and first["page"]["range_pad"] == 1


def test_data_only_where_the_map_says(stage):
    run, configuration, plans = stage
    with_data = {p.name for p in plot.pages(run, configuration, plans) if "data" in tomllib.loads(p.config.read_text())}
    assert with_data == {"em/d01-x01-y01", "ep/d01-x01-y01"}


def test_object_overrides_and_rivet_labels(stage):
    run, configuration, plans = stage
    pages = {p.name: tomllib.loads(p.config.read_text())["page"] for p in plot.pages(run, configuration, plans)}
    assert pages["em/d04-x01-y01"]["logy"] is True and pages["em/d04-x01-y01"]["y_gutter"] == 3.0
    assert pages["em/d04-x01-y01"]["title"] == "override"
    assert pages["em/d02-x01-y01"]["y_gutter"] == 0.5 and pages["em/d02-x01-y01"]["x_gutter"] == "default"
    if (REPO / "build" / "Rivet" / "photo_eic.plot").exists():
        assert pages["em/d01-x01-y01"]["x_label"] == "#it{E}_{#it{T}}^{#it{jet}} [GeV]"
        # with no figure of its own, log y is what the analysis's .plot says (the built copy, which
        # follows modules/: the user may be editing it)
        assert pages["em/d02-x01-y01"]["logy"] is (labels.labels_of("/photo_eic/d02-x01-y01").get("LogY") == "1")


def test_a_page_carries_only_the_style_it_changes(stage):
    run, configuration, plans = stage
    by = {p.name: p for p in plot.pages(run, configuration, plans)}
    assert tomllib.loads(by["em/d04-x01-y01"].config.read_text())["style"] == {
        "page": {"dpi": 100}, "legend": {"position": "top-left"}}
    assert tomllib.loads(by["em/d02-x01-y01"].config.read_text())["style"] == {"page": {"dpi": 100}}
    assert by["em/d02-x01-y01"].style["legend"]["position"] == "top-right"     # base.toml's
    assert by["em/d02-x01-y01"].style["page"]["size"] == [4.67, 4.21]


def test_incomplete_points_are_not_drawn(stage):
    run, configuration, plans = stage
    record.complete_marker(plans[0]).unlink()
    first = tomllib.loads(plot.pages(run, configuration, plans)[0].config.read_text())
    assert len(first["curve"]) == 1


def test_draw_writes_every_page(stage):
    run, configuration, plans = stage
    said = []
    assert plot.draw(run, configuration, plans, said.append) == 0
    drawn = sorted((plans[0].res.parent / "plots" / "root").rglob("*.png"))
    assert len(drawn) == 34, said
    assert "34 of 34" in said[-1]


def test_the_sweep_is_merged_once_into_the_file_the_pages_read(stage):
    run, configuration, plans = stage
    pages = plot.pages(run, configuration, plans)
    merged = plans[0].res.parent / "plots" / "root" / f"{configuration.label}.root"
    assert {c["file"] for p in pages for c in tomllib.loads(p.config.read_text())["curve"]} == {str(merged)}
    before = merged.stat().st_mtime_ns
    plot.pages(run, configuration, plans)
    assert merged.stat().st_mtime_ns == before                         # nothing changed: not rebuilt
    uproot = pytest.importorskip("uproot")
    with uproot.open(merged) as f:
        assert {k.split("/")[0] for k in f.keys() if "/" in k} == {p.point.name for p in plans}
        assert "points.json" in {k.split(";")[0] for k in f.keys()} or not (plans[0].out.parent / "points.json").exists()


def test_figures_are_recipes_for_pages(stage):
    """V80: a defined figure takes over its objects' pages (also those [plot].objects leaves out) with its
    own page keys, and leaves the other pages as they were; one recipe per page."""
    run, configuration, plans = stage
    cuts = {"class": "overlay", "objects": ["d02-x01-y01", "d03-x01-y01"], "labels": ["$E_T > 5$", "$E_T > 10$"], "ratio": False}
    run.plot.update({"objects": ["/photo_eic/d01*"]})
    run.plot["figures"] = {"cuts": cuts}
    before = {p.name: p.config.read_text() for p in plot.pages(run, configuration, plans)}
    run.plot["figures"]["tails"] = {"objects": ["d05-*"], "min_entries": 0, "auto_range": False, "style": {"page": {"dpi": 50}}}
    after = {p.name: p for p in plot.pages(run, configuration, plans)}
    assert set(after) == set(before) | {"em/d05-x01-y01", "ep/d05-x01-y01"} and "em/d04-x01-y01" not in after
    assert all(after[name].config.read_text() == text for name, text in before.items())   # the same page TOMLs
    d05 = tomllib.loads(after["em/d05-x01-y01"].config.read_text())
    assert (d05["page"]["min_entries"], d05["page"]["auto_range"], d05["style"]["page"]["dpi"]) == (0, False, 50)
    run.plot["figures"]["more"] = {"objects": ["d0[5-6]-*"]}
    with pytest.raises(plot.HepError, match="'tails' and 'more' both make the pages of /photo_eic/d05-x01-y01"):
        plot.pages(run, configuration, plans)
    run.plot["figures"] = {"none": {"objects": ["d99-*"]}}
    with pytest.raises(plot.HepError, match="match no object"):
        plot.pages(run, configuration, plans)


def test_an_overlay_figure_folds_a_band(stage):
    """V80: a figure's band, here an overlay's: one curve per object, the band axis's other values its members."""
    run, configuration, plans = stage
    run.plot["figures"] = {"cuts": {"class": "overlay", "objects": ["d02-x01-y01", "d03-x01-y01"], "band": ["pdf"]}}
    page = next(p for p in plot.pages(run, configuration, plans) if p.name == "em/cuts")
    curves = tomllib.loads(page.config.read_text())["curve"]
    assert [c["label"] for c in curves] == ["d02-x01-y01 (pdf envelope)", "d03-x01-y01 (pdf envelope)"]
    assert [len(c["band"]) for c in curves] == [1, 1] and [len(b) for b in page.bands] == [1, 1]
    assert plot.draw(run, configuration, plans, lambda line: None) == 0


def test_a_derived_figure_is_an_object_of_every_point(stage):
    """V84: /FIGURES/<name> per point, the ratio of two objects, appended to a copy of each point's YODA
    (made again only when the product changes); drawn as an object, its labels its first object's, and
    another figure may overlay it."""
    run, configuration, plans = stage
    run.plot["figures"].update({"r15": {"class": "derived", "op": "ratio", "objects": ["d01-x01-y01", "d05-x01-y01"],
                                        "y_label": "d01 / d05", "ratio": False},
                                "both": {"class": "overlay", "objects": ["r15", "d01-x01-y01"]}})
    by = {p.name: p for p in plot.pages(run, configuration, plans)}
    page = tomllib.loads(by["em/r15"].config.read_text())
    assert page["page"]["y_label"] == "d01 / d05" and page["page"]["x_label"] == tomllib.loads(
        by["em/d01-x01-y01"].config.read_text())["page"]["x_label"]
    assert [c["object"] for c in page["curve"]][0].endswith("/FIGURES/r15")
    assert by["em/both"].variants == ["/FIGURES/r15", "/photo_eic/d01-x01-y01"] * 2
    copy = plans[0].out.parent / "plots" / "derived" / f"{plans[0].point.name}.yoda"
    assert "BEGIN YODA_ESTIMATE1D_V3 /FIGURES/r15" in copy.read_text()
    when = copy.stat().st_mtime_ns
    assert plot.draw(run, configuration, plans, lambda line: None) == 0
    assert copy.stat().st_mtime_ns == when
    run.plot["figures"]["bad"] = {"class": "derived", "op": "ratio", "objects": ["d01-x01-y01", "d02-x01-y01"]}
    with pytest.raises(plot.HepError, match="figure 'bad' at .*: ratio of /photo_eic/d01-x01-y01 and /photo_eic/d02-x01-y01"):
        plot.pages(run, configuration, plans)


def test_a_scan_figure_draws_one_number_per_point(scratch):
    """V85: x a numeric curve axis, y the cross section of each point, a Scatter2D per page cell (here
    per PDF), its points at the x values with ranges halfway to their neighbours; refused for a quantity
    of names, or a page axis."""
    data = raw(run__name="plotscan", run__one__sweeps=["lepton", "pdf"], run__one__plot_points=["pdf"],
               quantities__lepton={"key": {"pythia": "Beams:idB"}, "values": [11, -11, 22], "tags": ["em", "ep", "g"]},
               plot={"formats": ["png"], "figures": {"xs": {"class": "scan", "x": "lepton", "y": "sigma", "logy": False},
                                                     "b2": {"class": "scan", "x": "lepton", "y": "bin:2",
                                                            "objects": ["d01-x01-y01"], "y_label": "second bin"}}})
    run = parse(data, scratch)
    configuration = run.configuration(None)
    plans = completed(run, configuration)
    by = {p.name: p for p in plot.pages(run, configuration, plans)}
    page = by[[n for n in by if n.endswith("/xs")][0]].document
    assert (page["page"]["x_label"], page["page"]["y_label"]) == ("lepton", r"$\sigma$ [pb]") and len(page["curve"]) == 1
    scans = sorted((plans[0].out.parent / "plots" / "scan" / "xs").glob("*.yoda"))
    assert len(scans) == 2                                                          # a curve per page cell (PDF)
    import yoda
    points = [(p.x(), p.xErrs(), p.y()) for p in yoda.read(str(scans[0]))["/FIGURES/xs"].points()]
    assert [(x, tuple(e)) for x, e, _ in points] == [(-11.0, (11.0, 11.0)), (11.0, (5.5, 5.5)), (22.0, (5.5, 5.5))]
    assert page["page"]["markers"] is True                                           # a scan is markers (V86)
    assert by[[n for n in by if n.endswith("/b2")][0]].document["page"]["y_label"] == "second bin"
    assert plot.draw(run, configuration, plans, lambda line: None) == 0
    run.plot["figures"]["xs"]["x"] = "pdf"
    with pytest.raises(plot.HepError, match="not a curve axis"):
        plot.check_figures(run, configuration)


def test_a_scatter2d_figure_is_drawn_as_markers(stage):
    """V86: type = "Scatter2D" marks the page; Paint draws its curves as markers, the other pages as before."""
    run, configuration, plans = stage
    run.plot["figures"]["pts"] = {"objects": ["d05-*"], "type": "Scatter2D"}
    by = {p.name: p for p in plot.pages(run, configuration, plans)}
    assert by["em/d05-x01-y01"].document["page"]["markers"] is True
    assert "markers" not in by["em/d01-x01-y01"].document["page"]
    assert plot.draw(run, configuration, plans, lambda line: None) == 0


def test_a_2d_object_is_a_heat_map_per_point(stage):
    """V87: a 2D object's pages are heat maps, one per point of the cell, drawn by Paint alone; a
    derived figure projects it; a HeatMap type on a 1D object, or a 2D object in an overlay, is refused."""
    yoda = pytest.importorskip("yoda")
    run, configuration, plans = stage
    h = yoda.Histo2D(4, 0, 4, 3, 0, 3, "/photo_eic/d90-x01-y01")
    for i in range(60):
        h.fill(i % 4 + 0.5, i % 3 + 0.5, 1.0 + i % 5)
    extra = plans[0].out.parent / "h2.yoda"
    yoda.write([h], str(extra))
    for plan in plans:                                           # each point's YODA gains the 2D object
        product = plot.yoda_of(plan)
        product.write_text(product.read_text() + "\n" + extra.read_text())
    run.plot["figures"]["px"] = {"class": "derived", "op": "projection-x", "objects": ["d90-x01-y01"], "ratio": False}
    by = {p.name: p for p in plot.pages(run, configuration, plans)}
    maps = sorted(n for n in by if "/d90-x01-y01/" in n)
    assert len(maps) == len(plans) and all(by[n].document["page"]["heatmap"] for n in maps)
    assert by["em/px"].document["page"]["x_label"] is not None
    said = []
    assert plot.draw(run, configuration, plans, said.append) == 0, said
    assert (plans[0].res.parent / "plots" / "root" / maps[0]).with_suffix(".png").is_file()
    run.plot["figures"]["bad"] = {"objects": ["d01-*"], "type": "HeatMap"}
    with pytest.raises(plot.HepError, match="is a HeatMap, and /photo_eic/d01-x01-y01 is a 1D object"):
        plot.pages(run, configuration, plans)
    run.plot["figures"]["bad"] = {"class": "overlay", "objects": ["d90-x01-y01", "d01-x01-y01"]}
    with pytest.raises(plot.HepError, match="is a 2D object, which a heat map draws alone"):
        plot.pages(run, configuration, plans)


@pytest.mark.skipif(not shutil.which("pdflatex"), reason="pdflatex tiles a sheet's PDF")
def test_a_sheet_tiles_drawn_pages(stage):
    """V89: the pages its globs name, in order, tiled as drawn: a PDF by pdflatex, a PNG by PIL."""
    from PIL import Image
    run, configuration, plans = stage
    run.plot["formats"] = ["pdf", "png"]
    run.plot["figures"]["grid"] = {"class": "sheet", "pages": ["*/d01-x01-y01", "em/d04-x01-y01"], "columns": 2}
    said = []
    assert plot.draw(run, configuration, plans, said.append) == 0, said
    assert "plot: sheet grid, 3 page(s) in 2 column(s) (root: pdf, png)" in said
    sheets = plans[0].res.parent / "plots" / "root" / "sheets"
    page = Image.open(plans[0].res.parent / "plots" / "root" / "em" / "d01-x01-y01.png")
    assert Image.open(sheets / "grid.png").size == (2 * page.width, 2 * page.height)
    assert (sheets / "grid.pdf").read_bytes().startswith(b"%PDF")
    run.plot["figures"]["grid"]["pages"] = ["nowhere/*"]
    said.clear()
    assert plot.draw(run, configuration, plans, said.append) == 1
    assert "plot: sheet grid: 'nowhere/*' names no page drawn here" in said


def test_a_compare_figure_draws_configurations_together(stage):
    """V83: the objects' pages across configurations, curves labelled by the configuration first, drawn
    by the plot stage of whichever configuration completes it, into <run>/compare/<name>/."""
    run, configuration, plans = stage
    two = replace(configuration, key="two", label="Second")
    run.configurations["two"] = two
    run.plot["figures"]["stats"] = {"class": "compare", "objects": ["d01-*"], "configurations": ["one", "two"],
                                    "labels": ["1M", "10M"]}
    said = []
    assert plot.draw(run, configuration, plans, said.append, others=lambda key: []) == 0
    assert "plot: compare stats waits for two: no complete point yet" in said
    others = completed(run, two)
    said.clear()
    assert plot.draw(run, two, others, said.append, others=lambda key: plans) == 0, said
    compare = plans[0].res.parent.parent / "compare" / "stats"
    assert (compare / "root" / "em" / "d01-x01-y01.png").is_file() and (compare / "root" / "index.html").is_file()
    page = tomllib.loads((plans[0].out.parent.parent / "compare" / "stats" / "em" / "d01-x01-y01.toml").read_text())
    assert [c["label"] for c in page["curve"]] == ["1M, MSTW 2008 LO", "1M, NNPDF 2.3 LO", "10M, MSTW 2008 LO", "10M, NNPDF 2.3 LO"]
    assert "data" in page
    run.plot["figures"]["stats"]["configurations"] = ["one", "nope"]
    with pytest.raises(plot.HepError, match="names 'nope', which is not a configuration"):
        plot.check_figures(run, configuration)


def test_a_compare_figure_reaches_another_run_toml(stage, scratch):
    """V88: "<config>:<cfg>" names a configuration of another run TOML; its points are curves beside this
    run's, labelled by that run, drawn into this run's compare/; its page axes must have this run's tags."""
    import tomli_w
    from runner import config
    run, configuration, plans = stage
    other = raw(run__name="plotstage_other", run__one__sweeps=["lepton", "pdf"], run__one__plot_points=["lepton"],
                quantities__lepton={"key": {"pythia": "Beams:idB"}, "values": [11, -11], "tags": ["em", "ep"]},
                quantities__pdf__labels=["MSTW", "NNPDF"])
    path = scratch / "other.toml"
    path.write_text(tomli_w.dumps(other), encoding="utf-8")
    theirs = config.load(str(path))
    their_plans = completed(theirs, theirs.configuration(None))
    run.plot["figures"]["chains"] = {"class": "compare", "objects": ["d01-*"], "configurations": ["one", f"{path}:one"]}
    plot.check_figures(run, configuration)
    asked = []
    said = []
    assert plot.draw(run, configuration, plans, said.append, others=lambda ref: asked.append(ref) or their_plans) == 0, said
    assert asked == [f"{path}:one"]
    page = tomllib.loads((plans[0].out.parent.parent / "compare" / "chains" / "em" / "d01-x01-y01.toml").read_text())
    assert [c["label"] for c in page["curve"]] == ["one, MSTW 2008 LO", "one, NNPDF 2.3 LO",
                                                   "plotstage_other one, MSTW", "plotstage_other one, NNPDF"]
    other["quantities"]["lepton"]["tags"] = ["e-", "e+"]
    path.write_text(tomli_w.dumps(other), encoding="utf-8")
    with pytest.raises(plot.HepError, match="has other values of lepton, a page axis"):
        plot.check_figures(run, configuration)
    run.plot["figures"]["chains"]["configurations"] = [f"{path}:one", f"{path}:one2"]
    with pytest.raises(plot.HepError, match="names '.*:one2', which is not a configuration"):
        plot.check_figures(run, configuration)


@pytest.mark.skipif(not shutil.which("rivet-merge"), reason="load_hep: rivet-merge")
def test_a_merged_figure_merges_the_points_for_itself(stage):
    """V82: per plot_points cell, the pdf points merged (rivet-merge -e) into one curve, on the objects'
    pages under the figure's folder; the other pages keep the points apart; a second draw merges nothing."""
    run, configuration, plans = stage
    run.plot["figures"]["avg"] = {"class": "merged", "objects": ["d01-*", "d05-*"], "over": ["pdf"], "title": "both PDFs"}
    by = {p.name: p for p in plot.pages(run, configuration, plans)}
    assert {n for n in by if "/avg/" in n} == {"em/avg/d01-x01-y01", "em/avg/d05-x01-y01", "ep/avg/d01-x01-y01", "ep/avg/d05-x01-y01"}
    page = tomllib.loads(by["em/avg/d01-x01-y01"].config.read_text())
    assert [c["object"].split("/")[0] for c in page["curve"]] == ["em"] and page["page"]["title"] == "both PDFs"
    assert "data" in page and len(tomllib.loads(by["em/d01-x01-y01"].config.read_text())["curve"]) == 2
    merged = plans[0].out.parent / "plots" / "merged" / "avg" / "em.yoda"
    stamp = merged.stat().st_mtime_ns
    assert plot.draw(run, configuration, plans, lambda line: None) == 0
    assert merged.stat().st_mtime_ns == stamp                                        # nothing changed: not merged again
    assert (plans[0].res.parent / "plots" / "root" / "em" / "avg" / "d01-x01-y01.png").is_file()


@pytest.mark.slow
@pytest.mark.skipif(not shutil.which("rivet-mkhtml"), reason="load_hep: rivet-mkhtml")
@pytest.mark.parametrize("stage", ["yoda"], indirect=True)
def test_the_yoda_backend_draws_the_same_pages(stage):
    """S3 row 1 in miniature: the pages of the ROOT backend, drawn by rivet-mkhtml, one set per cell."""
    run, configuration, plans = stage
    said = []
    assert plot.draw(run, configuration, plans, said.append) == 0, said
    plots = plans[0].res.parent / "plots" / "yoda"                          # the yoda backend's own tree
    for cell in ("em", "ep"):
        assert len(list((plots / cell / "photo_eic").glob("*.pdf"))) == 17
    work = plans[0].out.parent / "plots" / "em" / "yoda"
    blocks = (work / "pages.plot").read_text()
    assert blocks.count("# BEGIN PLOT") == 17 and "XMin=" in blocks and "LogY=1" in blocks
    yoda = pytest.importorskip("yoda")
    references = yoda.read(str(work / "reference.yoda"))
    assert list(references) == ["/REF/photo_eic/d01-x01-y01"]                # only what the map names


def test_pages_are_paints_and_another_backend_moves_only_the_output(stage):
    run, configuration, plans = stage
    page = plot.pages(run, configuration, plans)[0]
    plots = plans[0].res.parent / "plots"
    assert page.output == plots / "root" / page.name
    assert tomllib.loads(page.config.read_text())["page"]["output"] == str(page.output)   # Paint's
    assert plot.for_backend(page, "yoda").output == plots / "yoda" / page.name


@pytest.mark.slow
@pytest.mark.skipif(not shutil.which("rivet-mkhtml"), reason="load_hep: rivet-mkhtml")
@pytest.mark.parametrize("stage", ["both"], indirect=True)
def test_both_backends_draw_both_trees(stage):
    run, configuration, plans = stage
    said = []
    assert plot.draw(run, configuration, plans, said.append) == 0, said
    plots = plans[0].res.parent / "plots"
    for cell in ("em", "ep"):
        assert len(list((plots / "root" / cell).glob("*.png"))) == 17
        assert len(list((plots / "yoda" / cell / "photo_eic").glob("*.pdf"))) == 17
    assert said[0].startswith("plot: 34 of 34") and said[-1].startswith("plot (yoda): 34 of 34")


def test_a_swept_analysis_option_is_a_curve_not_a_page(scratch):
    """Each point's YODA holds its own variant (/photo_eic:R=0.4/…): one page per object, one curve
    per point, each read from its own path (found by the Lambda masswindow run, P4 S1)."""
    data = raw(run__name="plotvariants", run__one__sweeps=["radius"],
               quantities__radius={"target": "rivet/photo_eic", "key": "R", "values": [0.4, 0.7], "tags": ["r04", "r07"]},
               plot={"formats": ["png"], "min_entries": 10})
    run = parse(data, scratch)
    configuration = run.configuration(None)
    master = quantities.load_master(run.project, run.master_toml)
    plans = []
    for point in sweep.points(run, configuration):
        plan = tools.plan_point(run, configuration, point, master)
        plan.identity = record.identity(plan)
        plans.append(plan)
    for plan, r in zip(plans, ("0.4", "0.7")):
        shutil.rmtree(plan.res, ignore_errors=True)
        shutil.rmtree(plan.out, ignore_errors=True)
        text = (LEGACY / "mini_27x920_ep_MSTW.yoda").read_text()
        text = text.replace("/photo_eic/", f"/photo_eic:R={r}/")
        product = plot.yoda_of(plan)
        product.parent.mkdir(parents=True, exist_ok=True)
        product.write_text(text)
        record.complete_marker(plan).parent.mkdir(parents=True, exist_ok=True)
        record.complete_marker(plan).write_text(plan.identity + "\n")
    pages = plot.pages(run, configuration, plans)
    assert len(pages) == 17 and {p.name for p in pages} == {f"d{n:02d}-x01-y01" for n in range(1, 18)}
    first = tomllib.loads(pages[0].config.read_text())
    assert [c["object"] for c in first["curve"]] == ["r04/photo_eic__R-0.4/" + pages[0].name, "r07/photo_eic__R-0.7/" + pages[0].name]
    assert [c["raw"] for c in first["curve"]] == [c["object"].replace("/", "/RAW/", 1) for c in first["curve"]]
    said = []
    assert plot.draw(run, configuration, plans, said.append) == 0, said


def test_use_data_false_draws_no_data_and_divides_by_the_first_curve(stage):
    """V44: the [plot.data] table stays but is not drawn; the ratio's reference is each page's first
    curve (the first value of its curve axis)."""
    run, configuration, plans = stage
    run.plot["use_data"] = False
    pages = plot.pages(run, configuration, plans)
    documents = {p.name: tomllib.loads(p.config.read_text()) for p in pages}
    assert not any("data" in d for d in documents.values())
    d01 = documents["em/d01-x01-y01"]
    assert d01["page"]["ratio"] is True and d01["page"]["ratio_label"] == "Ratio"
    assert d01["curve"][0]["label"] == "MSTW 2008 LO"
    assert plot.draw(run, configuration, plans, lambda line: None) == 0


def test_a_best_legend_is_drawn(stage):
    """V49: Paint takes the corner with the fewest drawn points under the legend."""
    run, configuration, plans = stage
    run.plot["style"] = {**run.plot.get("style", {}), "legend": {"position": "best"}}
    assert plot.draw(run, configuration, plans, lambda line: None) == 0


@pytest.mark.parametrize("stage", ["root", "yoda"], indirect=True)
def test_titles_and_overlays(stage):
    """V51: [plot] titles for every page, a child's override; an overlay is several objects of each
    point on one page, labelled by the overlay (and the point, when a page has several)."""
    run, configuration, plans = stage
    run.plot.update({"title": "All pages", "title_right": "Pythia 8", "legend_header": "header for all",
                     "figures": {**run.plot["figures"], "cuts": {"class": "overlay", "objects": ["d02-x01-y01", "d03-x01-y01"], "labels": ["E_{T} > 5", "E_{T} > 10"],
                                          "title": "#eta by cut", "title_left": "k_{T}"}}})
    run.plot["figures"]["d04"]["legend_header"] = "d04's own"
    by = {p.name: p for p in plot.pages(run, configuration, plans)}
    d01, d04, cuts = (tomllib.loads(by[n].config.read_text())["page"] for n in ("em/d01-x01-y01", "em/d04-x01-y01", "em/cuts"))
    assert (d01["title"], d01["title_right"], d01["legend_header"]) == ("All pages", "Pythia 8", "header for all")
    assert d04["legend_header"] == "d04's own" and d04["title"] == "override"        # the child's own title
    assert (cuts["title"], cuts["title_left"], cuts["title_right"]) == ("#eta by cut", "k_{T}", "Pythia 8")
    labels = [c["label"] for c in tomllib.loads(by["em/cuts"].config.read_text())["curve"]]
    assert labels == ["E_{T} > 5, MSTW 2008 LO", "E_{T} > 10, MSTW 2008 LO", "E_{T} > 5, NNPDF 2.3 LO", "E_{T} > 10, NNPDF 2.3 LO"]
    assert plot.draw(run, configuration, plans, lambda line: None) == 0

    if run.plot["backend"] == "yoda":
        plots = plans[0].res.parent / "plots" / "yoda"
        assert (plots / "em" / "overlay" / "cuts.png").exists()
        script = (plots / "em" / "photo_eic" / "d01-x01-y01.py").read_text()
        assert "'All pages'" in script and "'Pythia 8'" in script and "bbox_inches='tight'" in script


@pytest.mark.slow
@pytest.mark.skipif(not shutil.which("rivet-mkhtml"), reason="load_hep: rivet-mkhtml")
@pytest.mark.parametrize("stage", ["yoda"], indirect=True)
def test_the_mpl_backend_draws_mkhtml_s_pages_pixel_for_pixel(stage):
    """V71 (B4c, option B): until the user has verified it, mpl's pages are mkhtml's: every page and
    overlay, with titles and a best legend, is the same PNG."""
    from matplotlib import image
    np = pytest.importorskip("numpy")
    run, configuration, plans = stage
    run.plot.update({"backend": ["yoda", "mpl"], "title": "All pages", "title_right": "Pythia 8",
                     "figures": {**run.plot["figures"], "cuts": {"class": "overlay", "objects": ["d02-x01-y01", "d03-x01-y01"],
                                                                 "labels": ["$E_T > 5$", "$E_T > 10$"]}}})
    run.plot["figures"]["d05"] = {"objects": ["d05-*"], "style": {"legend": {"position": "best"}}}
    said = []
    assert plot.draw(run, configuration, plans, said.append) == 0, said
    plots = plans[0].res.parent / "plots"
    compared = 0
    for mine in sorted((plots / "mpl").rglob("*.png")):
        rel = mine.relative_to(plots / "mpl")
        theirs = plots / "yoda" / rel.parent / ("overlay" if rel.stem == "cuts" else "photo_eic") / rel.name
        a, b = image.imread(mine), image.imread(theirs)
        assert a.shape == b.shape and not (np.abs(a[..., :3] - b[..., :3]) > 1e-3).any(), rel
        compared += 1
    assert compared == 36 and (plots / "mpl" / "index.html").is_file()            # 2 cells × (17 + 1)
