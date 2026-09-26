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
        record.complete_marker(plan).write_text(plan.identity + "\n")
    base = plans[0].out.parent
    base.mkdir(parents=True, exist_ok=True)
    record.write_atomic(base / "points.json", json.dumps(record.points_manifest(plans, run, configuration), default=str))


def run_post(post_plan, plans, run, configuration, rerun=False):
    out = io.StringIO()
    ok = post.run(post_plan, plans, run, configuration, sink=PlainView(stream=out), journal=None,
                  stopper=execute.Stopper(), rerun=rerun, say=lambda text: out.write(text + "\n"))
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
