"""Building run configs in tests: a dict in, a parsed RunConfig out (never written under configs/)."""

from __future__ import annotations

import copy
from pathlib import Path

from runner import config, quantities, sweep, tools

BASE = {
    "run": {"name": "t", "project": "PhotoProduction", "configuration": "one", "event_count": 10, "threads": 1,
            "one": {"tools": [["pythia", "rivet"]]}},
    "prelim": {"fifo": ["events.hepmc"]},
    "tools": {
        "pythia": {"tool": "pythia", "baseconfig": "photo_ep.cmnd", "output_file": "events.hepmc"},
        "rivet": {"tool": "rivet", "input": "events.hepmc", "analyses": ["photo_eic"], "output_file": "photo.yoda"},
    },
    "quantities": {
        "pdf": {"values": ["MSTW2008lo68cl", "NNPDF23_lo_as_0130_qed"], "tags": ["MSTW08lo", "NNPDF23lo"]},
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
