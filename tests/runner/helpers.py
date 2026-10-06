"""Building run configs in tests: a dict in, a parsed RunConfig out (never written under configs/)."""

from __future__ import annotations

import copy
from pathlib import Path

from runner import config, quantities, record, sweep, tools

BASE = {
    "run": {"name": "t", "project": "PhotoProduction", "configuration": "one", "event_count": 10, "threads": 1,
            "cfgs": {"one": {"tools": [["pythia", "rivet"]]}}},
    "prelim": {"fifo": ["events.hepmc"]},
    "tools": {
        "pythia": {"tool": "pythia", "baseconfig": "photo_ep.cmnd", "output_file": "events.hepmc"},
        "rivet": {"tool": "rivet", "input": "events.hepmc", "analyses": ["photo_eic"], "output_file": "photo.yoda"},
    },
    "quantities": {
        "pdf": {"values": ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_lo_as_0130_qed"], "tags": ["MSTW08lo", "NNPDF23lo"]},
    },
}


def raw(**changes) -> dict:
    data = copy.deepcopy(BASE)
    for dotted, value in changes.items():
        table = data
        *head, last = dotted.split("__")
        for part in head:
            table = table.setdefault(part, {})
        if value is None:
            table.pop(last, None)
        else:
            table[last] = value
    return data


def parse(data: dict, scratch: Path) -> config.RunConfig:
    return config.parse(data, scratch / "t.toml")


def plan(data: dict, scratch: Path, configuration: str | None = None, point: int = 0):
    run = parse(data, scratch)
    conf = run.configuration(configuration)
    master = quantities.load_master(run.project, run.master_toml)
    points = sweep.points(run, conf)
    result = tools.plan_point(run, conf, points[point], master)
    tools.finalise(result, 12345)
    return run, conf, result


def plans_of(name: str, configuration: str | None = None, sets=()):
    """A config by name (it resolves under tests/fixtures/configs): its run, configuration, points and the
    points' plans, with identities and seeds, before the seeds are written into the cards."""
    run = config.load(name, sets=list(sets))
    conf = run.configuration(configuration)
    master = quantities.load_master(run.project, run.master_toml)
    points = sweep.points(run, conf)
    out = [tools.plan_point(run, conf, point, master) for point in points]
    for p in out:
        p.identity = record.identity(p)
    record.assign_seeds(out)
    return run, conf, points, out


def plans(name: str, configuration: str | None = None, sets=()):
    """The finalised plans of a config's points (seeds written), as `hep run --plan` makes them."""
    *_, out = plans_of(name, configuration, sets)
    for p in out:
        tools.finalise(p, p.seed)
    return out


def render_context(folder: str, **context) -> dict:
    """The context the runner passes a folder's render.py (L26: the real type): its [card] owned and
    [render] data (V61), and the keys given."""
    spec = tools.folders()[folder].spec
    return {"owned": list(spec.get("card", {}).get("owned", [])), "render": spec.get("render", {}), **context}

