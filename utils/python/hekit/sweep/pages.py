"""Grouping points into plot pages and event groups (03 §4).

A **page** holds the points that differ only in the overlay group: they become the curves of one plot.
An **event group** holds points that differ only in analysis-side quantities: they share one generation,
so the planner runs them together (P1-S05, P6-S02).
"""

from __future__ import annotations

from typing import Any

from . import quantity as qt
from .expand import Point
from .select import Selection


def group_pages(points: list[Point]) -> dict[tuple[tuple[str, int], ...], list[Point]]:
    """Points by page key, in the order the points were expanded."""
    pages: dict[tuple[tuple[str, int], ...], list[Point]] = {}
    for point in points:
        pages.setdefault(point.page, []).append(point)
    return pages


def event_groups(points: list[Point]) -> dict[tuple[tuple[str, int], ...], list[Point]]:
    """Points by generation identity: analysis-only variants land in the same group (03 §4)."""
    groups: dict[tuple[tuple[str, int], ...], list[Point]] = {}
    for point in points:
        key = tuple(sorted(point.generation_choice.items()))
        groups.setdefault(key, []).append(point)
    return groups


def constant_suffix(config: Any, selection: Selection) -> str:
    """Tags of the quantities that are applied but not scanned, plus the settle tag."""
    parts = [qt.tag(config.quantities[name], index, config.output.tag_style)
             for name, index in selection.uses.items() if not selection.is_scanned(name)]
    if config.settle.tag:
        parts.append(config.settle.tag)
    return "_".join(part for part in parts if part)


def page_suffix(config: Any, selection: Selection, page: tuple[tuple[str, int], ...]) -> str:
    """Name of one page: the constant tags, this page's fixed values, then the curve quantities.

    The `by_<curves>` ending keeps a page name distinct from any point name, so a merged YODA never
    collides with a point's YODA.
    """
    parts = [constant_suffix(config, selection)]
    parts += [qt.tag(config.quantities[name], index, config.output.tag_style) for name, index in page]
    if selection.overlay:
        parts.append("by_" + "_".join(selection.overlay))
    return "_".join(part for part in parts if part)


def page_name(config: Any, selection: Selection, page: tuple[tuple[str, int], ...]) -> str:
    suffix = page_suffix(config, selection, page)
    return "_".join(part for part in (config.run.name, suffix) if part) or "page"


def curve_legend(config: Any, selection: Selection, point: Point) -> str:
    """Legend for one curve: the overlay labels on a grid, else every scanned label."""
    if len(selection.groups) > 1 and selection.overlay:
        shown = [name for name in selection.overlay if config.quantities[name].in_legend] \
            or selection.overlay[:1]
        return ", ".join(qt.legend(config.quantities[name], point.choice[name], config.plot.legends)
                         for name in shown)
    return point.legend or point.suffix or point.name
