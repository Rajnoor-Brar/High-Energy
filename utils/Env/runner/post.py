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


def _plan_stage(run, configuration, master: dict, point: Point, groups: list, products: dict, manifest,
                upstream: list | None = None) -> tools.PointPlan:
    """One stage, planned as a point is (V63): its tool groups, no quantities, `{points}` the manifest, an
    `input` naming a product of the points reads `products`; its identity holds `upstream` (the
    identities it follows), and its seed follows from its identity."""
    stage = replace(configuration, tools=groups, static={}, prelim={}, pre=[], post=[], combine=[])
    plan = tools.plan_point(run, stage, point, master, post={"manifest": manifest, "products": products})
    if upstream is not None:
        plan.upstream = upstream
    plan.identity = record.identity(plan)
    tools.finalise(plan, record.seed_of(plan.identity, plan.threads, plan.seed_range))
    return plan


def _run_stage(stage: tools.PointPlan, waits_on: list, run_config, configuration, *, bus=None, stopper, logs: bool = False,
               rerun: bool, say, missing: str):
    """One stage, once every plan it waits on is complete (V63): its result, or None when it did not run
    (incomplete upstream: `missing`, formatted with the count and the names, is said; or complete)."""
    incomplete = [p.point.name for p in waits_on if not record.is_complete(p)]
    if incomplete:
        say(missing.format(count=len(incomplete), names=", ".join(incomplete[:4]) + (", …" if len(incomplete) > 4 else "")))
        return None
    if not rerun and record.is_complete(stage):
        if bus is not None:
            bus.emit(stage.point.name, "", {"k": "point", "state": "skipped", "index": stage.point.index,
                                            **({"stage": stage.point.stage} if stage.point.stage else {})})
        return None
    return execute.run_point(stage, run_config, configuration, bus=bus, stopper=stopper, logs=logs)


def _reserved(run, configuration, names, name: str, stage: str) -> None:
    if name in names:
        raise HepError(f"a point is named '{name}', which is where the {stage} stage lives",
                       where=f"{run.path}: [run.{configuration.key}]", hint="give that value another tag")


def plan_pre(run, configuration, master: dict, points: list) -> tools.PointPlan | None:
    """The pre stage: once, before every point, in <cfg>/pre/. No quantities; `{points}` is the
    manifest. Its products are inputs every point may name, and its identity is in theirs."""
    if not configuration.pre:
        return None
    _reserved(run, configuration, {p.name for p in points}, PRE, "pre")
    manifest = tools.point_dirs(run, configuration, Point(index=-1, name=PRE))[0].parent / "points.json"
    return _plan_stage(run, configuration, master, Point(index=-1, name=PRE), configuration.pre, {}, manifest)


def run_pre(pre: tools.PointPlan | None, run_config, configuration, *, bus=None, stopper, logs: bool = False, rerun: bool) -> bool:
    """True unless the pre stage ran and failed (the points then do not run)."""
    if pre is None:
        return True
    result = _run_stage(pre, [], run_config, configuration, bus=bus, stopper=stopper, logs=logs,
                        rerun=rerun, say=print, missing="")
    return result is None or result.ok


def plan(run, configuration, master: dict, plans: list) -> tools.PointPlan | None:
    if not configuration.post:
        return None
    _reserved(run, configuration, {p.point.name for p in plans}, NAME, "post")
    products: dict[str, list] = {}                  # name → [(point, path)], in point order
    for p in plans:
        for interface in p.interfaces.values():
            if interface.kind == "product" and not interface.shard:
                products.setdefault(interface.name, []).append((p.point.name, interface.path))
    return _plan_stage(run, configuration, master, Point(index=0, name=NAME), configuration.post, products,
                       plans[0].out.parent / "points.json", upstream=[p.identity for p in plans])


def run(post: tools.PointPlan | None, every: list, run_config, configuration, *, bus=None, stopper, logs: bool = False,
        rerun: bool, say) -> bool:
    """True unless the post stage ran and failed. It runs only when every point is complete."""
    if post is None:
        return True
    result = _run_stage(post, every, run_config, configuration, bus=bus, stopper=stopper, logs=logs,
                        rerun=rerun, say=say, missing="post: not run, {count} point(s) incomplete ({names})")
    return result is None or result.ok


# ── combine: the points that differ only in the combined quantities, merged (V35) ──────────────

def _yoda_product(plan) -> tuple[str, object] | None:
    suffixes = tools.combiner()[1]
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
        stage_run = replace(run, tools={**run.tools, MERGE_TAG: Tool(tag=MERGE_TAG, tool=tools.combiner()[0], input=[source],
                                                                      output_file=[product])})
        plan = _plan_stage(stage_run, configuration, master, Point(index=number, name=name, stage=COMBINED), [[MERGE_TAG]],
                           {source: [(m.point.name, f[1]) for m, f in zip(members, found)]}, manifest,
                           upstream=[m.identity for m in members])
        plan.point = replace(plan.point, choice=choice)
        out.append(plan)
    return out


def run_combined(groups: list, every: list, run_config, configuration, *, bus=None, stopper, logs: bool = False, rerun: bool,
                 say) -> int:
    """Each group once its own points are complete; the number that failed."""
    failed = 0
    for group in groups:
        members = [p for p in every if p.identity in set(group.upstream)]
        result = _run_stage(group, members, run_config, configuration, bus=bus, stopper=stopper, logs=logs,
                            rerun=rerun, say=say, missing=f"combine: {group.point.name} not merged, {{count}} of its points incomplete")
        if result is None:
            continue
        if result.stopped or stopper.requested:
            return failed + 1
        failed += not result.ok
    return failed
