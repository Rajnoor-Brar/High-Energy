"""Which curves go on a page, and under what name (07 §4).

The legacy `common_analysis` and `unify_yodas` answered "what do we plot when two points used
different analysis plugins?" — rename the objects of the odd ones out so everything overlays. That is
kept, and two things are added that the new layout makes possible:

* **an analysis-option variant is a curve, not a page.** `photo_eic:R=0.4` and `photo_eic:R=0.7` live
  in one YODA, produced by one generation (03 §4), so selecting a variant is selecting an object path
  rather than finding a different file;
* **every curve gets its own namespace** (00/B17), so a page cannot silently lose a curve to a name
  collision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import io


@dataclass
class Curve:
    """One line on a plot: where it comes from, what it is called, and how it is labelled."""

    name: str                       # unique; the point name, or point + variant
    path: Path                      # the YODA holding it
    analysis: str = ""              # with options, as it appears in the file
    legend: str = ""
    point: str = ""                 # the point it belongs to
    options: dict[str, str] = field(default_factory=dict)

    @property
    def base(self) -> str:
        return io.base_analysis(self.analysis)


def variants_in(path: Path, *, analysis: str = "") -> list[str]:
    """Every analysis (with options) present in a YODA file, in a stable order."""
    found: list[str] = []
    for obj_path in io.read(path):
        parsed = io.split_object_path(obj_path)
        if parsed is None or obj_path.startswith("/REF/"):
            continue
        if analysis and io.base_analysis(parsed[0]) != io.base_analysis(analysis):
            continue
        if parsed[0] not in found:
            found.append(parsed[0])
    return sorted(found)


def curves_for(points: Iterable[Any], *, analysis: str = "", legends: str = "label") -> list[Curve]:
    """One curve per point, or per option variant when a point has several.

    `points` are objects with `name`, `yoda` (a path) and optionally `legend`/`label` — the study
    manifest's entries, or anything shaped like them.

    **A point that says which variant is its own gets only that one.** Several points can share one
    generation when they differ only in an analysis option (03 §4), and their one YODA then holds
    every variant; expanding all of them for each point would put four curves on a two-member page.
    A point that declares nothing still gets every variant in its file, which is how a single point
    with several radii becomes several curves.
    """
    curves: list[Curve] = []
    for point in points:
        path = Path(getattr(point, "yoda", "") or getattr(point, "path", ""))
        name = getattr(point, "name", path.stem)
        found = variants_in(path, analysis=analysis) if path.is_file() else []
        declared = [variant for variant in (getattr(point, "analyses", ()) or []) if variant in found]
        chosen = declared or found or [analysis or ""]
        # Only a point being split into several curves needs its option in the name and the legend;
        # when the point *is* the variant, its own label already says so.
        split = not declared and len(found) > 1
        for variant in chosen:
            options = io.options_of(variant)
            suffix = ("_" + "_".join(f"{key}{value}" for key, value in sorted(options.items()))
                      if split else "")
            curves.append(Curve(
                name=f"{name}{suffix}",
                path=path, analysis=variant, point=name, options=options,
                legend=legend_for(point, variant, legends, with_options=split)))
    return curves


def legend_for(point: Any, variant: str, legends: str = "label", *, with_options: bool = True) -> str:
    """What a curve is called on the page: its label, its tag, or its value (`[plot].legends`).

    `with_options = False` leaves the variant out of the text, for a point whose own label already is
    the variant — otherwise the radius study reads "R = 0.4 (R=0.4)".
    """
    options = io.options_of(variant) if with_options else {}
    chosen = {
        "label": getattr(point, "legend", "") or getattr(point, "label", ""),
        "tag": getattr(point, "tag", "") or getattr(point, "name", ""),
        "value": getattr(point, "value", "") or getattr(point, "legend", ""),
    }.get(legends, "")
    text = str(chosen or getattr(point, "name", ""))
    if options:
        text += " (" + ", ".join(f"{key}={value}" for key, value in sorted(options.items())) + ")"
    return text


def common_analysis(curves: Iterable[Curve], *, override: str = "") -> str:
    """The analysis name every curve is renamed onto: `[plot].analysis`, else the first one."""
    curves = list(curves)
    if override:
        return override
    return curves[0].base if curves else ""


def unify(curves: list[Curve], analysis: str, workdir: Path) -> list[Curve]:
    """Rename objects so curves produced by *different* plugins overlay on one page.

    A point that already uses `analysis` is left alone — its file is used as it is, which keeps the
    common case free.
    """
    unified: list[Curve] = []
    workdir.mkdir(parents=True, exist_ok=True)
    for index, curve in enumerate(curves):
        if curve.base == io.base_analysis(analysis):
            unified.append(curve)
            continue
        objects = io.read(curve.path)
        renamed = []
        for obj_path, obj in objects.items():
            parsed = io.split_object_path(obj_path)
            if parsed is not None and io.base_analysis(parsed[0]) == curve.base:
                prefix = "/REF" if obj_path.startswith("/REF/") else ""
                tail = parsed[0][len(curve.base):]          # keep the options
                obj.setPath(f"{prefix}/{io.base_analysis(analysis)}{tail}/{parsed[1]}")
            renamed.append(obj)
        destination = workdir / f"{index:03d}_{curve.path.name}"
        io.write(renamed, destination)
        unified.append(Curve(name=curve.name, path=destination,
                             analysis=io.base_analysis(analysis) + (
                                 ":" + ",".join(f"{key}={value}"
                                                for key, value in sorted(curve.options.items()))
                                 if curve.options else ""),
                             legend=curve.legend, point=curve.point, options=dict(curve.options)))
    return unified


def with_namespaces(curves: list[Curve], workdir: Path) -> list[Curve]:
    """Move every curve's objects under its own name (00/B17).

    Used when curves are merged into one file — `ydmrg`'s job — where sharing one namespace let two
    points' objects collide and one disappear without a word.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    result: list[Curve] = []
    for curve in curves:
        objects = io.read(curve.path)
        moved = []
        for obj_path, obj in objects.items():
            if io.split_object_path(obj_path) is None:
                continue
            obj.setPath(io.namespaced(obj_path, curve.name))
            moved.append(obj)
        destination = workdir / f"{curve.name}.yoda"
        io.write(moved, destination)
        result.append(Curve(name=curve.name, path=destination, analysis=curve.analysis,
                            legend=curve.legend, point=curve.point, options=dict(curve.options)))
    return result
