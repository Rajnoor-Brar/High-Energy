"""A run's results, read from Python (rank 3, V77): for notebooks and the statistics tools (category 9).

    import sys; sys.path.insert(0, "<repo>/utils/Env")
    from runner import results

    for point in results.load("PhotoProduction/eic", "pdf"):
        print(point.name, point.values["pdf"].label, point.complete, point.yoda())

It reads what a run wrote, its `points.json` manifest (output/<P>/<run>/<cfg>/points.json, every point
even under --points), and plans nothing, so it is quick and needs no tool installed. `complete` is the
manifest's, as of the run that wrote it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import config as configmod
from .errors import HepError
from .paths import output_root
from .tools import run_dir


@dataclass(frozen=True)
class Value:
    tag: str
    label: str
    value: object
    swept: bool


@dataclass(frozen=True)
class Point:
    name: str
    index: int
    values: dict[str, Value]
    products: dict[str, Path]                       # product name → its path in results/
    results: Path
    output: Path
    complete: bool
    identity: str = ""
    seed: int | None = None
    page: tuple = field(default_factory=tuple)      # the plot_points part of its values

    def yoda(self) -> Path | None:
        """The point's YODA product (the first, if it has several)."""
        return next((p for name, p in self.products.items() if name.endswith(".yoda")), None)

    def root(self) -> Path | None:
        return next((p for name, p in self.products.items() if name.endswith(".root")), None)


def manifest(config: str, configuration: str | None = None) -> Path:
    """Where a configuration's points.json is."""
    run = configmod.load(config)
    return output_root() / run_dir(run, run.configuration(configuration)) / "points.json"


def load(config: str, configuration: str | None = None) -> list[Point]:
    """The points of one configuration, as its last run recorded them."""
    path = manifest(config, configuration)
    if not path.is_file():
        raise HepError("this configuration has no results yet", where=str(path), hint="hep run it first")
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for entry in data.get("points", []):
        out.append(Point(
            name=entry["name"], index=entry.get("index", 0),
            values={q: Value(v.get("tag", ""), v.get("label", ""), v.get("value"), bool(v.get("swept")))
                    for q, v in entry.get("values", {}).items()},
            products={name: Path(p) for name, p in entry.get("products", {}).items()},
            results=Path(entry.get("results", "")), output=Path(entry.get("output", "")),
            complete=bool(entry.get("complete")), identity=entry.get("identity", ""), seed=entry.get("seed"),
            page=tuple(entry.get("page", []))))
    return out


def runs(config: str) -> dict[str, list[Point]]:
    """Every configuration of a config that has run: its key → its points."""
    run = configmod.load(config)
    found = {}
    for key in run.configurations:
        try:
            found[key] = load(config, key)
        except HepError:
            continue
    return found
