"""Overlaying a fitted curve on the histogram it was fitted to (12 §3, `[plot].show_fits`).

`hep proc` writes `/PROC/<fit>/curve` into `proc.yoda`. That path says which *fit* a curve is, which
is what `fits.json` wants — and it is the wrong path for drawing, because a plotter puts objects on
the same axes when their paths match, and `/PROC/peak/curve` matches nothing.

So this renames each curve to the **target it was fitted to** and writes a small YODA that joins the
page's inputs as one more curve. The rename is the whole trick, and it is done on a copy: nothing
edits `proc.yoda`, which is the record.

A fit whose target is not on this page is skipped rather than being drawn somewhere it does not
belong — a page is a set of histograms, and `proc.yoda` holds the fits of a whole study.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from . import io


@dataclass
class FitOverlay:
    """The YODA of renamed fit curves, and what went into it."""

    path: Path | None = None
    names: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.path is not None and bool(self.names)


def find(study_dir: Path | None) -> Path | None:
    """`proc.yoda` of a study, when `hep proc` has been run."""
    if study_dir is None:
        return None
    candidate = Path(study_dir) / "proc" / "proc.yoda"
    return candidate if candidate.is_file() else None


def targets_of(fits_json: Path) -> dict[str, str]:
    """fit name → the YODA path it was fitted to, from `fits.json`."""
    import json

    if not fits_json.is_file():
        return {}
    try:
        payload = json.loads(fits_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found: dict[str, str] = {}
    for entry in payload.get("fits", []) or []:
        name = str(entry.get("name") or "")
        target = str(entry.get("target") or "")
        if name and target:
            found[name] = target
    return found


def overlay(proc_yoda: Path, *, on: Sequence[str], destination: Path,
            targets: dict[str, str] | None = None) -> FitOverlay:
    """Rename each fit curve to its target and write them where a plotter will find them.

    `on` is the set of object paths already on the page: a fit is drawn only when its target is one
    of them.
    """
    import yoda

    made = FitOverlay()
    objects = io.read(proc_yoda)
    if not objects:
        return made

    wanted = {path.split(":", 1)[0] for path in on}
    keep: list[Any] = []
    for path, obj in objects.items():
        if not path.startswith("/PROC/"):
            continue
        # `/PROC/<fit>/curve` or `/PROC/<fit>/<point>/curve`.
        parts = path.strip("/").split("/")
        if len(parts) < 3:
            continue
        name = parts[1]
        target = (targets or {}).get(name, "")
        if not target:
            made.skipped.append(f"{name} (no target in fits.json)")
            continue
        if target.split(":", 1)[0] not in wanted:
            made.skipped.append(f"{name} (its target is not on this page)")
            continue
        # Several points on one page each have their own fit of the *same* target, so writing them
        # all at that path would leave one survivor — a dict is keyed by path. An analysis **option**
        # keeps them distinct while `io.plot_key` still maps them to the same figure, which is the
        # very mechanism two option variants already use to share a plot (07 §4).
        path_out = target
        point = parts[2] if len(parts) > 3 else ""
        if point:
            analysis, _, histogram = target.strip("/").partition("/")
            if histogram:
                path_out = f"/{analysis}:fit={point}/{histogram}"

        copied = obj.clone()
        copied.setPath(path_out)
        # No colon in the title: YODA writes annotations as a YAML block, and `Title: fit: name`
        # is not parseable YAML — it fails on *reading*, so the file writes fine and the next
        # command is the one that breaks.
        copied.setTitle(f"fit {name}" + (f" {point}" if point else ""))
        keep.append(copied)
        made.names.append(name if not point else f"{name}/{point}")

    if not keep:
        return made
    destination.parent.mkdir(parents=True, exist_ok=True)
    yoda.write(keep, str(destination))
    made.path = destination
    return made
