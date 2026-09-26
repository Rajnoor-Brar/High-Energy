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
def stage(scratch):
    data = raw(run__name="plotstage", run__one__sweeps=["lepton", "pdf"], run__one__plot_points=["lepton"],
               quantities__lepton={"key": {"pythia": "Beams:idB"}, "values": [11, -11], "tags": ["em", "ep"]},
               quantities__pdf__labels=["MSTW 2008 LO", "NNPDF 2.3 LO"],
               plot={"formats": ["png"], "ratio": True, "min_entries": 10, "range_pad": 1,
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
        source = LEGACY / ("mini_27x920_ep_MSTW.yoda" if "MSTW" in plan.point.name else "mini_27x920_ep_NNLO.yoda")
        product = plot.yoda_of(plan)
        product.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, product)
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
        assert pages["em/d01-x01-y01"]["x_label"] == "E_{T} [GeV]"
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
    drawn = sorted((plans[0].res.parent / "plots").rglob("*.png"))
    assert len(drawn) == 34, said
    assert "34 of 34" in said[-1]


def test_inputs_are_converted_once(stage):
    run, configuration, plans = stage
    plot.pages(run, configuration, plans)
    inputs = plans[0].out.parent / "plots" / "inputs"
    before = {p: p.stat().st_mtime_ns for p in inputs.glob("*.root")}
    plot.pages(run, configuration, plans)
    assert {p: p.stat().st_mtime_ns for p in inputs.glob("*.root")} == before and len(before) == 4
