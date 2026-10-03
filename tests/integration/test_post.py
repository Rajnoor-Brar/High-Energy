"""The post stage (P3 S3 row 3, V15) on fake complete points: a custom post tool is handed
points.json and the points' products, runs once, is skipped when nothing changed, and does not run
over a subset.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path

import pytest

from runner import execute, post, quantities, record, sweep, tools
from runner.errors import HepError
from runner.events import Bus
from runner.watch import PlainView

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "runner"))
from helpers import parse, raw  # noqa: E402

SCRIPT = """
import json, sys
manifest, output, *inputs = sys.argv[1:]
points = json.load(open(manifest))["points"]
json.dump({"inputs": inputs, "points": [{"name": p["name"], "pdf": p["values"]["pdf"]["tag"],
                                           "products": p["products"], "complete": p["complete"]} for p in points]},
          open(output, "w"))
"""


def stage(scratch, name="poststage", **changes):
    script = scratch / "summary.py"
    script.write_text(SCRIPT)
    changes = {"run__name": name, "run__one__sweeps": ["pdf"], "run__one__post": ["summary"],
               "tools__summary": {"tool": "custom", "executable": sys.executable, "input": "photo.yoda",
                                  "output_file": "summary.json",
                                  "arguments": [str(script), "{points}", "{partial:output}", "{inputs}"]},
               **changes}
    data = raw(**{k: v for k, v in changes.items() if not k.startswith("tools__summary__")})
    for key, value in changes.items():
        if key.startswith("tools__summary__"):
            data["tools"]["summary"][key.removeprefix("tools__summary__")] = value
    run = parse(data, scratch)
    configuration = run.configuration(None)
    master = quantities.load_master(run.project, run.master_toml)
    plans = []
    for point in sweep.points(run, configuration):
        plan = tools.plan_point(run, configuration, point, master)
        plan.identity = record.identity(plan)
        plans.append(plan)
    shutil.rmtree(plans[0].res.parent, ignore_errors=True)
    shutil.rmtree(plans[0].out.parent, ignore_errors=True)
    return run, configuration, master, plans


def complete(plans, run, configuration):
    for plan in plans:
        product = next(i.path for i in plan.interfaces.values() if i.kind == "product")
        product.parent.mkdir(parents=True, exist_ok=True)
        product.write_text(f"yoda of {plan.point.name}\n")
        record.complete_marker(plan).parent.mkdir(parents=True, exist_ok=True)
        record.complete_marker(plan).write_text(plan.identity + "\n")
    base = plans[0].out.parent
    base.mkdir(parents=True, exist_ok=True)
    record.write_atomic(base / "points.json", json.dumps(record.points_manifest(plans, run, configuration), default=str))


def run_post(post_plan, plans, run, configuration, rerun=False):
    out = io.StringIO()
    view, bus = PlainView(stream=out), Bus()
    bus.subscribe(view)
    ok = post.run(post_plan, plans, run, configuration, bus=bus, stopper=execute.Stopper(), rerun=rerun, say=bus.say)
    view.flush()                                                       # the view writes on its own thread (V32)
    return ok, out.getvalue()


def test_a_post_tool_gets_every_point_and_its_products(scratch):
    run, configuration, master, plans = stage(scratch)
    complete(plans, run, configuration)
    post_plan = post.plan(run, configuration, master, plans)
    ok, said = run_post(post_plan, plans, run, configuration)
    assert ok, said
    got = json.loads((post_plan.res / "summary.json").read_text())
    products = [str(next(i.path for i in p.interfaces.values() if i.kind == "product")) for p in plans]
    assert got["inputs"] == products                                  # {inputs}: every point, in point order
    assert [p["pdf"] for p in got["points"]] == ["MSTW08lo", "NNPDF23lo"]
    assert [p["products"]["photo.yoda"] for p in got["points"]] == products
    assert all(p["complete"] for p in got["points"])
    assert post_plan.res == plans[0].res.parent / "post" and record.is_complete(post_plan)


def test_post_is_skipped_when_nothing_changed_and_reruns_when_a_point_did(scratch):
    run, configuration, master, plans = stage(scratch)
    complete(plans, run, configuration)
    first = post.plan(run, configuration, master, plans)
    assert run_post(first, plans, run, configuration)[0]
    ok, said = run_post(post.plan(run, configuration, master, plans), plans, run, configuration)
    assert ok and "skipped" in said
    plans[0].identity = "changed"
    assert post.plan(run, configuration, master, plans).identity != first.identity


def test_post_does_not_run_over_a_subset(scratch):
    run, configuration, master, plans = stage(scratch)
    complete(plans, run, configuration)
    record.complete_marker(plans[1]).unlink()
    post_plan = post.plan(run, configuration, master, plans)
    ok, said = run_post(post_plan, plans, run, configuration)
    assert ok and "1 point(s) incomplete" in said
    assert not (post_plan.res / "summary.json").exists()


def test_a_post_tool_may_not_overwrite_the_points_product(scratch):
    run, configuration, master, plans = stage(scratch, tools__summary__output_file="photo.yoda")
    with pytest.raises(HepError, match="points' product"):
        post.plan(run, configuration, master, plans)


def test_no_post_tools_no_post_plan(scratch):
    run, configuration, master, plans = stage(scratch, run__one__post=[])
    assert post.plan(run, configuration, master, plans) is None


# ── the pre stage ─────────────────────────────────────────────────────────────────────────────

PRE_SCRIPT = """
import sys
open(sys.argv[1], "w").write("made before every point\\n")
"""


def pre_stage(scratch, marker="first"):
    script = scratch / "pre.py"
    script.write_text(PRE_SCRIPT)
    data = raw(run__name="prestage", run__one__sweeps=["pdf"], run__one__pre=["fetch"],
               run__one__tools=[["pythia", "rivet"], "use"],
               tools__fetch={"tool": "custom", "executable": sys.executable, "output_file": "shared.txt",
                             "arguments": [str(script), "{partial:output}", marker]},
               tools__use={"tool": "custom", "executable": sys.executable, "input": "shared.txt",
                           "arguments": ["-c", "pass", "{input}"]})
    run = parse(data, scratch)
    configuration = run.configuration(None)
    master = quantities.load_master(run.project, run.master_toml)
    points = sweep.points(run, configuration)
    pre = post.plan_pre(run, configuration, master, points)
    plans = [tools.plan_point(run, configuration, point, master, pre=pre) for point in points]
    for plan in plans:
        plan.identity = record.identity(plan)
    return run, configuration, pre, plans


def test_a_pre_product_is_an_input_every_point_may_name(scratch):
    run, configuration, pre, plans = pre_stage(scratch)
    shared = pre.interfaces["shared.txt"].path
    assert shared == pre.res / "shared.txt" and pre.res.name == "pre" and pre.point.index == -1
    for plan in plans:
        assert plan.rendered["use"].argv[-1] == str(shared) and plan.upstream == [pre.identity]
    other = pre_stage(scratch, marker="second")[3]
    assert other[0].identity != plans[0].identity                     # a changed pre reruns the points
    shutil.rmtree(pre.res, ignore_errors=True)
    shutil.rmtree(pre.out, ignore_errors=True)
    ok = post.run_pre(pre, run, configuration, stopper=execute.Stopper(), rerun=False)
    assert ok and shared.read_text() == "made before every point\n" and record.is_complete(pre)


def test_a_failing_pre_stops_the_run(scratch):
    run, configuration, pre, plans = pre_stage(scratch)
    pre.rendered["fetch"].argv = [sys.executable, "-c", "raise SystemExit(3)"]
    shutil.rmtree(pre.out, ignore_errors=True)
    out = io.StringIO()
    view, bus = PlainView(stream=out), Bus()
    bus.subscribe(view)
    assert not post.run_pre(pre, run, configuration, bus=bus, stopper=execute.Stopper(), rerun=True)
    view.flush()
    assert "── pre (before every point) ── FAILED [fetch]" in out.getvalue()


def test_a_point_may_not_be_named_pre(scratch):
    data = raw(run__one__sweeps=["pdf"], run__one__pre=["fetch"], quantities__pdf__tags=["pre", "x"],
               tools__fetch={"tool": "custom", "executable": sys.executable, "arguments": ["-c", "pass"]})
    run = parse(data, scratch)
    configuration = run.configuration(None)
    with pytest.raises(HepError, match="named 'pre'"):
        post.plan_pre(run, configuration, quantities.load_master(run.project, run.master_toml),
                      sweep.points(run, configuration))


# ── plotmerge: one file for a sweep ───────────────────────────────────────────────────────────

LEGACY = REPO / "tests" / "reference" / "legacy_run"


@pytest.mark.skipif(not (REPO / "build" / "App_yd2rt.exe").exists(), reason="make utils/App_yd2rt.exe")
@pytest.mark.parametrize("target", ["sweep.root", "sweep.yoda"])
def test_plotmerge_puts_every_point_in_one_file(scratch, target):
    run, configuration, master, plans = stage(scratch, name=f"plotmerge_{target.split('.')[1]}", run__one__post=["bundle"],
                                              tools__bundle={"tool": "plotmerge", "input": "photo.yoda", "output_file": target})
    complete(plans, run, configuration)
    for plan, name in zip(plans, ("mini_27x920_ep_MSTW.yoda", "mini_27x920_ep_NNLO.yoda")):
        shutil.copy(LEGACY / name, next(i.path for i in plan.interfaces.values() if i.kind == "product"))
    post_plan = post.plan(run, configuration, master, plans)
    assert post_plan.rendered["bundle"].argv[3:5] == [f"{p.point.name}={next(i.path for i in p.interfaces.values() if i.kind == 'product')}"
                                                     for p in plans]
    ok, said = run_post(post_plan, plans, run, configuration)
    assert ok, said
    merged = post_plan.res / target
    if target.endswith(".root"):
        uproot = pytest.importorskip("uproot")
        with uproot.open(merged) as f:
            assert {k.split("/")[0] for k in f.keys() if "/" in k} == {"MSTW08lo", "NNPDF23lo"}
            assert f["MSTW08lo/photo_eic/d01-x01-y01"].values().sum() > 0 and "points.json;1" in f.keys()
    else:
        text = merged.read_text()
        assert "/MSTW08lo/photo_eic/d01-x01-y01" in text and "/NNPDF23lo/photo_eic/d01-x01-y01" in text
