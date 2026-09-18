"""Overlaying reference data, by an explicit map only (07 §4; finding 00/B5).

The old `remap_data_yoda` matched a data object to an MC histogram **by name**: `d08-x01-y01` in the
ZEUS file was drawn on `d08-x01-y01` of `photo_eic`, whatever the two histograms actually were. In this
project they were different observables, so the plots showed data over the wrong quantity and nothing
complained. That is 00/B5, and it is the reason this module exists.

So: a data file is overlaid only where `[plot.data].map` says so.

```toml
[plot.data]
file = "datasets/zeus_eic.yoda"
map = { "d01-x01-y01" = "/REF/ZEUS_2012_I1116258/d01-x01-y01" }
```

Without a map there is no overlay and a warning says why; a mapped entry that does not exist is an
error, because a silent miss is exactly what the finding is about. Everything else the old function did
right — reference vs plain curves, binning alignment, `MainPanel` — is kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import HepError
from . import io
from .transform import align_to_edges, edge_index


@dataclass
class DataOverlay:
    """What came of overlaying a data file: the file written, and what was said about it."""

    path: Path | None = None
    mapped: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)

    @property
    def drew_anything(self) -> bool:
        return self.path is not None


def mc_binnings(paths: list[Path], analysis: str) -> dict[str, list[float] | None]:
    """The binning of each MC histogram on the page, by histogram name."""
    found: dict[str, list[float] | None] = {}
    for path in paths:
        for obj_path, obj in io.read(path).items():
            parsed = io.split_object_path(obj_path)
            if parsed is None or obj_path.startswith("/REF/"):
                continue
            if io.base_analysis(parsed[0]) != io.base_analysis(analysis):
                continue
            found.setdefault(parsed[1], io.edges_of(obj))
    return found


def overlay(*, data_file: Path | str, mapping: dict[str, str], curves: list[Path], analysis: str,
            destination: Path, reference: bool = True, show: bool = True) -> DataOverlay:
    """Write a copy of the data file whose objects sit on the MC histograms `mapping` names.

    `mapping` is `{MC histogram name: data object path}` — explicit, never inferred (00/B5).
    """
    result = DataOverlay()
    data_file = Path(data_file)
    if not mapping:
        result.warnings.append(
            f"{data_file.name} was not overlaid: [plot.data].map is empty. Name matching is not "
            f"used, because it once drew this experiment's data over the wrong observable (00/B5)")
        return result

    binnings = mc_binnings(curves, analysis)
    if not binnings:
        raise HepError(f"the selected results have no /{io.base_analysis(analysis)}/ histograms",
                       hint="check [plot].analysis, or the points this page covers")

    objects = io.read(data_file)
    base = io.base_analysis(analysis)
    remapped = []
    for histogram, source in sorted(mapping.items()):
        obj = objects.get(source) or objects.get(f"/REF{source}") or objects.get(source.lstrip("/"))
        if obj is None:
            raise HepError(f"[plot.data].map points at {source}, which {data_file.name} does not have",
                           hint="`yoda-ls` lists a file's objects")
        if histogram not in binnings:
            raise HepError(f"[plot.data].map names the histogram {histogram}, which "
                           f"/{base}/ does not have")

        if reference:
            if not io.is_reference(obj, source):
                obj.setAnnotation("IsRef", 1)
            obj.setPath(f"/REF/{base}/{histogram}")
        else:
            obj.setPath(f"/{base}/{histogram}")
            if obj.hasAnnotation("IsRef"):
                obj.rmAnnotation("IsRef")

        mc_edges = binnings.get(histogram)
        if mc_edges is not None:
            original = io.edges_of(obj)
            if original is not None:
                if not reference and (len(original) != len(mc_edges) or any(
                        edge_index(mc_edges, edge) is None for edge in original)):
                    result.skipped[histogram] = "binning differs from the MC curve"
                    result.warnings.append(
                        f"data {histogram} skipped: its binning differs from the MC "
                        f"(set [plot.data].reference = true to overlay it as a reference)")
                    continue
                aligned = align_to_edges(obj, mc_edges)
                if aligned is None:
                    result.skipped[histogram] = "no bin edges match the MC binning"
                    result.warnings.append(
                        f"data {histogram} skipped: none of its bin edges {original} match the MC")
                    continue
                kept = io.edges_of(aligned) or []
                if kept != original:
                    result.warnings.append(
                        f"data {histogram} trimmed to [{kept[0]:g}, {kept[-1]:g}] to match the MC "
                        f"binning")
                obj = aligned

        if not show:
            obj.setAnnotation("MainPanel", 0)   # kept as the ratio denominator, not drawn
        remapped.append(obj)
        result.mapped[histogram] = source

    if not remapped:
        result.warnings.append(f"nothing from {data_file.name} could be overlaid on /{base}/")
        return result

    result.path = io.write(remapped, destination)
    return result


def suggest_map(data_file: Path | str, curves: list[Path], analysis: str) -> dict[str, str]:
    """A starting point for `[plot.data].map`, for `hep plot --suggest-data-map`.

    It offers name matches **as a suggestion the user must confirm**, which is the difference between
    a convenience and 00/B5: the plot is drawn from the map in the config, never from this.
    """
    binnings = mc_binnings(curves, analysis)
    found: dict[str, str] = {}
    for obj_path in io.read(data_file):
        parsed = io.split_object_path(obj_path)
        if parsed and parsed[1] in binnings:
            found.setdefault(parsed[1], obj_path)
    return found
