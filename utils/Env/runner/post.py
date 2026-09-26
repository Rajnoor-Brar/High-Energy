"""The post stage: tools that need every point, run once after them (rank 4).

docs/rework_v2/02_Architecture.md §6, 04_Config.md §4.3 (V15). `[run.<cfg>].post` has the form of
`tools`. It is planned as one more point, named "post", in the configuration's directory:

* it takes no quantities;
* an `input` naming a product of the points (`input = "photo.yoda"`) reads that product of every
  point, spliced into argv by `{inputs}`;
* `{points}` is the points manifest, points.json: every point's values, tags and product paths;
* its identity hashes its own tools and every point's identity, so it reruns when any point changes,
  and is skipped otherwise, like a point.

It runs only when every point of the configuration is complete: a merge or a fit over a subset
would look like the whole.
"""

from __future__ import annotations

from dataclasses import replace

from . import execute, record, tools
from .errors import HepError
from .sweep import Point

NAME = "post"


def plan(run, configuration, master: dict, plans: list) -> tools.PointPlan | None:
    if not configuration.post:
        return None
    if any(p.point.name == NAME for p in plans):
        raise HepError(f"a point is named '{NAME}', which is where the post stage lives",
                       where=f"{run.path}: [run.{configuration.key}]", hint="give that value another tag")
    products: dict[str, list] = {}
    for p in plans:
        for interface in p.interfaces.values():
            if interface.kind == "product":
                products.setdefault(interface.name, []).append(interface.path)
    stage = replace(configuration, tools=configuration.post, static={}, prelim={})
    manifest = plans[0].out.parent / "points.json"
    post = tools.plan_point(run, stage, Point(index=0, name=NAME), master,
                            post={"manifest": manifest, "products": products})
    post.upstream = [p.identity for p in plans]
    post.identity = record.identity(post)
    tools.finalise(post, record.seed_of(post.identity, post.threads))
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
