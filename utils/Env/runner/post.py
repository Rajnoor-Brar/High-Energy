"""The pre and post stages: tools run once, before every point or after them (rank 4).

docs/02_Architecture.md §7, docs/04_Config_Reference.md §5.4 (V15). `[run.<cfg>].post` has the form of
`tools`. It is planned as one more point, named "post", in the configuration's directory:

* it takes no quantities;
* an `input` naming a product of the points (`input = "photo.yoda"`) reads that product of every
  point, spliced into argv by `{inputs}`;
* `{points}` is the points manifest, points.json: every point's values, tags and product paths;
* its identity hashes its own tools and every point's identity, so it reruns when any point changes,
  and is skipped otherwise, like a point.

It runs only when every point of the configuration is complete: a merge or a fit over a subset
would look like the whole.

`combine = ["replica"]` (V35) plans one more stage per group of points that differ only in the
combined quantities: rivet-merge -e of the group's YODA product into <cfg>/<group>/, a file of the
same name. Each runs once its own points are complete, and the plot stage draws the groups.
"""

from __future__ import annotations

from dataclasses import replace

from . import execute, record, tools
from .config import Tool
from .errors import HepError
from .sweep import Point, tag_of

NAME = "post"
PRE = "pre"
COMBINED = "combined"            # the group's name when every swept quantity is combined
MERGE_TAG = "combine"


def plan_pre(run, configuration, master: dict, points: list) -> tools.PointPlan | None:
    """The pre stage: once, before every point, in <cfg>/pre/. No quantities; `{points}` is the
    manifest. Its products are inputs every point may name, and its identity is in theirs."""
    if not configuration.pre:
        return None
    if any(point.name == PRE for point in points):
        raise HepError(f"a point is named '{PRE}', which is where the pre stage lives",
                       where=f"{run.path}: [run.{configuration.key}]", hint="give that value another tag")
    stage = replace(configuration, tools=configuration.pre, static={}, prelim={})
    manifest = tools.point_dirs(run, configuration, Point(index=-1, name=PRE))[0].parent / "points.json"
    pre = tools.plan_point(run, stage, Point(index=-1, name=PRE), master, post={"manifest": manifest, "products": {}})
    pre.identity = record.identity(pre)
    tools.finalise(pre, record.seed_of(pre.identity, pre.threads, pre.seed_range))
    return pre


def run_pre(pre: tools.PointPlan | None, run_config, configuration, *, sink, journal, stopper, rerun: bool) -> bool:
    """True unless the pre stage ran and failed (the points then do not run)."""
    if pre is None:
        return True
    if not rerun and record.is_complete(pre):
        sink.skipped(pre)
        return True
    return execute.run_point(pre, run_config, configuration, sink=sink, journal=journal, stopper=stopper).ok


def plan(run, configuration, master: dict, plans: list) -> tools.PointPlan | None:
    if not configuration.post:
        return None
    if any(p.point.name == NAME for p in plans):
        raise HepError(f"a point is named '{NAME}', which is where the post stage lives",
                       where=f"{run.path}: [run.{configuration.key}]", hint="give that value another tag")
    products: dict[str, list] = {}                  # name → [(point, path)], in point order
    for p in plans:
        for interface in p.interfaces.values():
            if interface.kind == "product" and not interface.shard:
                products.setdefault(interface.name, []).append((p.point.name, interface.path))
    stage = replace(configuration, tools=configuration.post, static={}, prelim={})
    manifest = plans[0].out.parent / "points.json"
    post = tools.plan_point(run, stage, Point(index=0, name=NAME), master,
                            post={"manifest": manifest, "products": products})
    post.upstream = [p.identity for p in plans]
    post.identity = record.identity(post)
    tools.finalise(post, record.seed_of(post.identity, post.threads, post.seed_range))
    return post


def run(post: tools.PointPlan | None, every: list, run_config, configuration, *, sink, journal, stopper,
        rerun: bool, say) -> bool:
    """True unless the post stage ran and failed."""
    if post is None:
        return True
    missing = [p.point.name for p in every if not record.is_complete(p)]
    if missing:
        say(f"post: not run, {len(missing)} point(s) incomplete ({', '.join(missing[:4])}"
            f"{', …' if len(missing) > 4 else ''})")
        return True
    if not rerun and record.is_complete(post):
        sink.skipped(post)
        return True
    result = execute.run_point(post, run_config, configuration, sink=sink, journal=journal, stopper=stopper)
    return result.ok


# ── combine: the points that differ only in the combined quantities, merged (V35) ──────────────

def _combiner() -> tuple[str, tuple[str, ...]]:
    """The tool folder that merges points (V60: [outputs] combines = ["yoda"], the merge folder), and the
    product suffixes it merges."""
    for name, folder in tools.folders().items():
        if folder.get("outputs", "combines"):
            return name, tuple("." + s for s in folder.get("outputs", "combines"))
    raise HepError("no tool folder says [outputs] combines: nothing can merge the points")


def _yoda_product(plan) -> tuple[str, object] | None:
    suffixes = _combiner()[1]
    for interface in plan.interfaces.values():
        if interface.kind == "product" and not interface.shard and interface.path.suffix in suffixes:
            return interface.name, interface.path
    return None


def plan_combined(run, configuration, master: dict, plans: list) -> list[tools.PointPlan]:
    """One stage per group, planned like post in <cfg>/<group>/: the merge folder (rivet-merge -e) of
    the group's YODA product into a file of the same name. The group is named by its other swept
    quantities' tags, "combined" when there are none, and its point carries their choice, so the
    plot stage draws the groups as it would draw points."""
    if not configuration.combine:
        return []
    where = f"{run.path}: [run.{configuration.key}].combine"
    if MERGE_TAG in run.tools:
        raise HepError(f"[tools.{MERGE_TAG}] is the name combine uses for its merges", where=where,
                       hint="rename that table")
    combined = set(configuration.combine)
    kept = [name for entry in configuration.sweeps for name in (entry if isinstance(entry, list) else [entry])
            if name not in combined]
    groups: dict[tuple, list] = {}
    for p in plans:
        groups.setdefault(tuple(p.point.choice[name] for name in kept), []).append(p)
    taken = {p.point.name for p in plans} | {NAME, PRE}
    stage = replace(configuration, tools=[[MERGE_TAG]], static={}, prelim={}, pre=[], post=[], combine=[])
    manifest = plans[0].out.parent / "points.json"
    out = []
    for number, (key, members) in enumerate(groups.items(), start=1):
        choice = dict(zip(kept, key))
        name = "_".join(tag_of(run.quantities[q], choice[q]) for q in kept) or COMBINED
        if name in taken:
            raise HepError(f"the combined group '{name}' would share a directory with a point or stage", where=where,
                           hint="give the swept quantities distinct tags (C11)")
        found = [_yoda_product(m) for m in members]
        if not all(found):
            raise HepError("combine merges the points' YODA product, and these points have none", where=where)
        product = found[0][0]
        source = f"{product} of the combined points"           # not the product's own name: the output is
        stage_run = replace(run, tools={**run.tools, MERGE_TAG: Tool(tag=MERGE_TAG, tool=_combiner()[0], input=[source],
                                                                      output_file=[product])})
        plan = tools.plan_point(stage_run, stage, Point(index=number, name=name, stage=COMBINED), master,
                                post={"manifest": manifest, "products": {source: [(m.point.name, f[1])
                                                                                  for m, f in zip(members, found)]}})
        plan.point = replace(plan.point, choice=choice)
        plan.upstream = [m.identity for m in members]
        plan.identity = record.identity(plan)
        tools.finalise(plan, record.seed_of(plan.identity, plan.threads, plan.seed_range))
        out.append(plan)
    return out


def run_combined(groups: list, every: list, run_config, configuration, *, sink, journal, stopper, rerun: bool,
                 say) -> int:
    """Each group once its own points are complete; the number that failed."""
    failed = 0
    for group in groups:
        members = [p for p in every if p.identity in set(group.upstream)]
        missing = [p.point.name for p in members if not record.is_complete(p)]
        if missing:
            say(f"combine: {group.point.name} not merged, {len(missing)} of its points incomplete")
            continue
        if not rerun and record.is_complete(group):
            sink.skipped(group)
            continue
        result = execute.run_point(group, run_config, configuration, sink=sink, journal=journal, stopper=stopper)
        if result.stopped or stopper.requested:
            return failed + 1
        failed += not result.ok
    return failed
