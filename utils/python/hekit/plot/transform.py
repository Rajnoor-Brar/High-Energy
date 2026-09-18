"""The transforms that make a page readable (07 §4).

Ported from `rivpyth_common`'s `void_bins`, `auto_range_plot`, `edge_index` and `align_to_edges`. Their
behaviour is already validated against real plots, so this is a port and not a redesign; the tests
compare the two implementations bin for bin while the old tools still exist.

What each is for:

* **voiding** — a bin that is zero in every curve, or that too few raw entries went into, is blanked
  (NaN, no errors) in *all* curves, so `rivet-mkhtml` leaves a gap instead of drawing 0/0 = 1 ± 1 in
  the ratio panel. The decision is made across the whole page, never per curve, or the curves would
  disagree about which bins exist.
* **auto-range** — each x axis is clipped to the bins that carry content, widened by `range_pad`.
* **alignment** — `rivet-mkhtml` rebins MC onto the reference binning, which only works when every
  reference edge is also an MC edge; otherwise YODA indexes past the end. A data object is trimmed to
  its longest run of aligned bins, or dropped with a warning.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import io


@dataclass
class VoidReport:
    bins: int = 0
    histograms: int = 0
    rule: str = ""

    def __str__(self) -> str:
        return f"voided {self.bins} bins ({self.rule}) in {self.histograms} histograms"


def void_bins(paths: list[Path], workdir: Path, *, void_empty: bool = False,
              min_entries: int = 0) -> tuple[list[Path], VoidReport]:
    """Blank uninformative bins consistently across the curves of one page."""
    report = VoidReport(rule="empty" + (f" or < {min_entries} entries" if min_entries else ""))
    if not void_empty and not min_entries:
        return list(paths), report

    contents = [io.read(path) for path in paths]
    empty: dict[str, list[bool]] = {}
    sparse: dict[str, list[bool]] = {}

    for objects in contents:
        for obj_path, obj in objects.items():
            if obj_path.startswith(("/REF/", "/RAW/")) or not io.is_binned_1d(obj):
                continue
            key = io.plot_key(obj_path)
            if key is None:
                continue
            zero = [value == 0.0 for value in io.values_of(obj)]
            if key in empty and len(empty[key]) == len(zero):
                empty[key] = [a and b for a, b in zip(empty[key], zero)]
            else:
                empty.setdefault(key, zero)
            # The raw histogram Rivet keeps next to each finalized object holds the entry counts.
            raw = objects.get("/RAW" + obj_path)
            if min_entries and raw is not None and raw.numBins() == obj.numBins():
                low = [entry.numEntries() < min_entries for entry in raw.bins()]
                previous = sparse.get(key, [False] * len(low))
                sparse[key] = [a or b for a, b in zip(previous, low)]

    voids: dict[str, list[bool]] = {}
    for key, zero in empty.items():
        mask = zero if void_empty else [False] * len(zero)
        if key in sparse and len(sparse[key]) == len(mask):
            mask = [a or b for a, b in zip(mask, sparse[key])]
        if any(mask):
            voids[key] = mask

    result: list[Path] = []
    workdir.mkdir(parents=True, exist_ok=True)
    for position, (path, objects) in enumerate(zip(paths, contents)):
        changed = False
        for obj_path, obj in objects.items():
            if obj_path.startswith(("/REF/", "/RAW/")):
                continue
            key = io.plot_key(obj_path)
            mask = voids.get(key) if key else None
            if mask is None or not io.is_binned_1d(obj) or obj.numBins() != len(mask):
                continue
            for index, blank in enumerate(mask, start=1):
                if blank:
                    obj.bin(index).setVal(float("nan"))
                    obj.bin(index).rmErrs()
                    changed = True
        if changed:
            destination = workdir / f"void_{position:03d}_{path.name}"
            io.write(objects, destination)
            result.append(destination)
        else:
            result.append(path)

    report.bins = sum(sum(mask) for mask in voids.values())
    report.histograms = len(voids)
    return result, report


def auto_range(paths: list[Path], analysis: str, workdir: Path, *, pad: int = 0,
               name: str = "auto_range.plot") -> Path | None:
    """A `.plot` file clipping each 1D plot's x axis to the bins that have content.

    Written after the project's own `.plot` file so it overrides only `XMin`/`XMax`.
    """
    spans: dict[str, tuple[float, float]] = {}
    for path in paths:
        for obj_path, obj in io.read(path).items():
            if obj_path.startswith("/RAW/") or not io.is_binned_1d(obj):
                continue
            parsed = io.split_object_path(obj_path)
            if parsed is None or io.base_analysis(parsed[0]) != io.base_analysis(analysis):
                continue
            values = io.values_of(obj)
            filled = [index for index, value in enumerate(values)
                      if math.isfinite(value) and value != 0.0]
            edges = io.edges_of(obj)
            if not filled or edges is None:
                continue
            first = max(filled[0] - pad, 0)
            last = min(filled[-1] + pad, len(values) - 1)
            low, high = edges[first], edges[last + 1]
            key = f"/{io.base_analysis(analysis)}/{parsed[1]}"
            if key in spans:
                low, high = min(low, spans[key][0]), max(high, spans[key][1])
            spans[key] = (low, high)

    if not spans:
        return None
    workdir.mkdir(parents=True, exist_ok=True)
    blocks = [f"# BEGIN PLOT {key}\nXMin={low:g}\nXMax={high:g}\n# END PLOT\n"
              for key, (low, high) in sorted(spans.items())]
    destination = workdir / name
    destination.write_text("\n".join(blocks), encoding="utf-8")
    return destination


def edge_index(edges: list[float], value: float) -> int | None:
    for index, edge in enumerate(edges):
        if math.isclose(edge, value, rel_tol=1e-9, abs_tol=1e-12):
            return index
    return None


def align_to_edges(obj: Any, mc_edges: list[float]) -> Any | None:
    """Trim a 1D object to its longest run of bins whose edges are all MC edges.

    Returns the object unchanged when it already aligns, a trimmed clone when part of it does, and
    None when nothing does — the caller then drops the curve with a warning rather than letting YODA
    index past the end of an array.
    """
    import yoda

    data_edges = io.edges_of(obj)
    if data_edges is None:
        return obj
    aligned = [edge_index(mc_edges, edge) is not None for edge in data_edges]
    if all(aligned):
        return obj

    best, start = (0, 0), None
    for index, ok in enumerate(aligned + [False]):
        if ok and start is None:
            start = index
        elif not ok and start is not None:
            if index - start > best[1] - best[0]:
                best = (start, index)
            start = None
    first, last = best
    if last - first < 2:
        return None

    trimmed = yoda.BinnedEstimate1D(data_edges[first:last], obj.path(), obj.title())
    for key in obj.annotations():
        if key not in {"Path", "Type", "Title"}:
            trimmed.setAnnotation(key, obj.annotation(key))
    for number in range(1, last - first):
        trimmed.set(number, obj.bin(first + number))
    return trimmed
