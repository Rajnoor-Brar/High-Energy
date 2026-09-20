"""Turning a plan into pages a backend can draw (07 §4).

A **page** is a set of curves that belong on the same axes: the points of one sweep group, plus
whatever option variants they carry, plus optional reference data. `hep plan` already decides which
points share a page (03 §4); this assembles the files.

The order is the legacy one, because it is the order that works:

    select curves → unify analysis names → void uninformative bins → overlay data → auto-range

Voiding comes before the data overlay so the reference is aligned against the binning the curves will
actually be drawn with, and auto-range comes last so it sees both the curves and the data.

Everything is written into a **work directory the caller owns** — no fixed `/tmp` names (00/B19) — and
the intermediates are kept, because they are what the golden comparison against `ydmrg` checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import HepError
from . import data as data_module
from . import io, plotfile, select, transform
from .select import Curve


@dataclass
class Page:
    """One drawable page and everything that went into it."""

    name: str
    analysis: str
    curves: list[Curve] = field(default_factory=list)
    plot_file: Path | None = None
    ranges: Path | None = None
    data: data_module.DataOverlay | None = None
    fits: Any = None
    workdir: Path | None = None
    warnings: list[str] = field(default_factory=list)
    voided: transform.VoidReport | None = None

    @property
    def paths(self) -> list[Path]:
        return [curve.path for curve in self.curves]

    @property
    def drawable(self) -> list[Path]:
        """Everything a backend should put on the axes: the curves, then the fits (12 §3).

        Kept separate from `paths` because voiding, unification and auto-ranging all operate on the
        *curves* — a fitted function has no bins to void and no analysis name to unify.
        """
        found = list(self.paths)
        if self.fits is not None and getattr(self.fits, "path", None) is not None:
            found.append(self.fits.path)
        return found

    @property
    def legends(self) -> list[str]:
        return [curve.legend for curve in self.curves]


@dataclass
class PointFile:
    """A point as the plot pipeline sees it: a name, a legend, a YODA and which variant is its own.

    `analyses` matters when several points share one generation (03 §4): the file then holds *every*
    variant, and without this each point would contribute all of them — four curves on a page with
    two members. Empty means "whatever is in the file", which is right for a point that is the whole
    generation.
    """

    name: str
    yoda: Path
    legend: str = ""
    tag: str = ""
    analyses: tuple[str, ...] = ()


def points_of(plan: Any, layout: Any, page: Any) -> list[PointFile]:
    """The results a page's points produced, by looking in the layout rather than guessing."""
    found: list[PointFile] = []
    for point, legend in zip(page.members, page.legends):
        group = plan.group_of(point.name)
        directory = layout.point(group.name)
        yoda = directory / "analysis.yoda"
        if not yoda.is_file():
            # A generator running Rivet itself writes a gzipped YODA (`rivet.mode = "native"`,
            # 04 §4), and a stopped run leaves a partial one (D22). YODA reads both.
            for candidate in ("analysis.yoda.gz", "analysis.partial.yoda"):
                if (directory / candidate).is_file():
                    yoda = directory / candidate
                    break
        found.append(PointFile(name=point.name, yoda=yoda, legend=legend or point.name,
                               tag=getattr(point, "suffix", ""),
                               analyses=tuple(getattr(point, "analyses", ()) or ())))
    return found


def missing(points: list[PointFile]) -> list[str]:
    return [str(point.yoda) for point in points if not point.yoda.is_file()]


def prepare(points: list[PointFile], workdir: Path, *, name: str = "", project: str = "",
            analysis: str = "", legends: str = "label", void_empty: bool = False,
            min_entries: int = 0, auto_range: bool = False, range_pad: int = 0,
            data_file: Path | str = "", data_map: dict[str, str] | None = None,
            data_reference: bool = True, data_show: bool = True,
            proc_dir: Path | None = None) -> Page:
    """Run the pipeline for one page and return everything a backend needs."""
    absent = missing(points)
    if absent:
        raise HepError("these results have not been produced yet:\n  " + "\n  ".join(absent),
                       hint="run them with `hep run`, or select points that exist")

    workdir.mkdir(parents=True, exist_ok=True)
    curves = select.curves_for(points, analysis=analysis, legends=legends)
    if not curves:
        raise HepError(f"no curves for page {name or '(unnamed)'}")

    chosen = select.common_analysis(curves, override=analysis)
    curves = select.unify(curves, chosen, workdir / "unified")

    voided, report = transform.void_bins([curve.path for curve in curves], workdir / "voided",
                                         void_empty=void_empty, min_entries=min_entries)
    for curve, path in zip(curves, voided):
        curve.path = path

    page = Page(name=name, analysis=chosen, curves=curves, workdir=workdir, voided=report,
                plot_file=plotfile.find(chosen, project) if project else None)

    if data_file:
        page.data = data_module.overlay(
            data_file=data_file, mapping=dict(data_map or {}), curves=page.paths, analysis=chosen,
            destination=workdir / f"{io.base_analysis(chosen)}_data.yoda",
            reference=data_reference, show=data_show)
        page.warnings.extend(page.data.warnings)

    # `[plot].show_fits`: `hep proc`'s curves, renamed onto the histograms they were fitted to, as
    # one more input file (12 §3). Nothing edits `proc.yoda` itself — that is the record.
    if proc_dir is not None:
        from . import fits as fits_module

        proc_yoda = Path(proc_dir) / "proc.yoda"
        if proc_yoda.is_file():
            page.fits = fits_module.overlay(
                proc_yoda, on=io.read(page.paths[0]).keys() if page.paths else (),
                destination=workdir / "fits.yoda",
                targets=fits_module.targets_of(Path(proc_dir) / "fits.json"))
            for reason in page.fits.skipped:
                page.warnings.append(f"fit not drawn: {reason}")

    if auto_range:
        inputs = list(page.paths)
        if page.data is not None and page.data.path is not None:
            inputs.append(page.data.path)
        page.ranges = transform.auto_range(inputs, chosen, workdir, pad=range_pad)
    return page


def prepare_from_config(plan: Any, layout: Any, page_spec: Any, workdir: Path,
                        proc_dir: Path | None = None) -> Page:
    """The same, reading every option from a config's `[plot]` section."""
    config = plan.config
    plot = config.plot
    return prepare(
        points_of(plan, layout, page_spec), workdir,
        name=page_spec.name, project=config.project, analysis=plot.analysis,
        legends=plot.legends, void_empty=plot.void_empty, min_entries=plot.min_entries,
        auto_range=plot.auto_range, range_pad=plot.range_pad,
        data_file=_data_path(config), data_map=dict(getattr(plot.data, "map", {}) or {}),
        data_reference=plot.data.reference, data_show=plot.data.show,
        proc_dir=proc_dir if getattr(plot, "show_fits", False) else None)


def _data_path(config: Any) -> str:
    """`[plot.data].file`, resolved against the config's directory when it is relative."""
    entry = getattr(config.plot.data, "file", "")
    if not entry:
        return ""
    path = Path(entry)
    return str(path if path.is_absolute() else (config.path.parent / path).resolve())
