"""Points and pages from `sweeps` and `plot_points` (rank 1).

docs/04_Config_Reference.md §5.1–5.2. A string entry of `sweeps` is an independent axis; a list
entry is an entangled group that moves together (value i with value i). The points are the grid of
the axes, in `sweeps` order. Pages are the grid of the `plot_points` axes, and every other swept
quantity becomes the curves on a page.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

from .errors import HepError


@dataclass
class Point:
    index: int                                      # 1-based
    name: str                                       # tags joined by "_", in sweeps order; "point" if none
    choice: dict[str, int] = field(default_factory=dict)   # swept quantity → value index
    page: tuple = ()                                # the plot_points part of the choice


def tag_of(quantity, index: int) -> str:
    if quantity.tags:
        return quantity.tags[index]
    text = re.sub(r"[^A-Za-z0-9.+-]+", "-", str(quantity.values[index])).strip("-")
    return text or f"{quantity.name}{index + 1}"


def label_of(quantity, index: int) -> str:
    return quantity.labels[index] if quantity.labels else tag_of(quantity, index)


def axes(configuration) -> list[list[str]]:
    return [entry if isinstance(entry, list) else [entry] for entry in configuration.sweeps]


def points(run, configuration) -> list[Point]:
    groups = axes(configuration)
    ranges = [range(len(run.quantities[group[0]].values)) for group in groups]
    page_axes = [i for i, group in enumerate(groups) if set(group) & set(configuration.plot_points)]
    out: list[Point] = []
    for number, combination in enumerate(itertools.product(*ranges), start=1):
        choice = {name: index for group, index in zip(groups, combination) for name in group}
        tags = [tag_of(run.quantities[name], choice[name]) for group in groups for name in group]
        page = tuple(combination[i] for i in page_axes)
        out.append(Point(index=number, name="_".join(tags) or "point", choice=choice, page=page))
    names = [p.name for p in out]
    clashes = sorted({n for n in names if names.count(n) > 1})
    if clashes:
        raise HepError(f"these points would share a directory: {', '.join(clashes)}", where=f"{run.path}",
                       hint="give the swept quantities distinct tags (C11)")
    return out


def pages(configuration, point_list: list[Point]) -> dict[tuple, list[Point]]:
    """page key → its points, in point order. No plot_points: one page with every point."""
    out: dict[tuple, list[Point]] = {}
    for point in point_list:
        out.setdefault(point.page, []).append(point)
    return out


def select_points(run, configuration, point_list: list[Point], selector: str | None) -> list[Point]:
    """--points: comma-separated tags, 1-based indices, point names or quantity=tag filters."""
    if not selector:
        return point_list
    chosen = []
    for item in [s.strip() for s in selector.split(",") if s.strip()]:
        if "=" in item:
            name, _, wanted = item.partition("=")
            if name not in run.quantities:
                raise HepError(f"--points: '{name}' is not a quantity")
            matched = [p for p in point_list if name in p.choice and tag_of(run.quantities[name], p.choice[name]) == wanted]
        elif item.isdigit():
            matched = [p for p in point_list if p.index == int(item)]
        else:
            matched = [p for p in point_list if p.name == item or item in p.name.split("_")]
        if not matched:
            raise HepError(f"--points: '{item}' matches no point", hint=", ".join(p.name for p in point_list[:8]))
        chosen += [p for p in matched if p not in chosen]
    return chosen
