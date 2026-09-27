"""The plot stage end to end on fake complete points (P3 S2 rows 1 and 4).

Four points (lepton × pdf) whose products are the two legacy mini YODAs; plot_points = lepton, so
two pages per object with two curves each. Reference data are mapped for d01 only.
"""

from __future__ import annotations

import shutil
import sys
import tomllib
from pathlib import Path

import pytest

from runner import plot, quantities, record, sweep, tools

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
                     "object": {"d04-*": {"logy": True, "y_gutter": 3.0, "title": "override"}}})
    run = parse(data, scratch)
    configuration = run.configuration(None)
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
    return run, configuration, plans


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
    assert pages["em/d02-x01-y01"]["y_gutter"] == 1.5
    if (REPO / "build" / "Rivet" / "photo_eic.plot").exists():
        assert pages["em/d01-x01-y01"]["x_label"] == "#it{E}_{#it{T}} [GeV]"
        assert pages["em/d02-x01-y01"]["logy"] is False


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
    merged = plans[0].res.parent / "plots" / "root" / f"{configuration.name}.root"
    assert {c["file"] for p in pages for c in tomllib.loads(p.config.read_text())["curve"]} == {str(merged)}
    before = merged.stat().st_mtime_ns
    plot.pages(run, configuration, plans)
    assert merged.stat().st_mtime_ns == before                         # nothing changed: not rebuilt
    uproot = pytest.importorskip("uproot")
    with uproot.open(merged) as f:
        assert {k.split("/")[0] for k in f.keys() if "/" in k} == {p.point.name for p in plans}
        assert "points.json" in {k.split(";")[0] for k in f.keys()} or not (plans[0].out.parent / "points.json").exists()


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
