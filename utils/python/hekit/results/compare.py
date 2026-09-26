"""`hep compare`: how far apart two curves are, as a table (07 §5).

A PDF study is four curves and fifteen histograms; opening sixty plots to see whether anything moved
is the reason this exists. One table per comparison — χ²/ndf, bins used, max pull — is usually enough
to know which two plots are worth opening.

The reference is either the data (`--ref data`, the overlay the plot pipeline builds) or a point
(`--ref POINT`), which is how a tune study asks "how far is each variation from the baseline". The
table goes to the terminal and to `compare.md` in the study directory, so it survives the session.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import HepError
from ..plot import io
from . import stats
from .layout import write_atomic

NAME = "compare.md"


@dataclass
class Row:
    """One curve compared with the reference, for one histogram."""

    curve: str
    histogram: str
    comparison: stats.Comparison

    @property
    def sort_key(self) -> tuple:
        return (self.histogram, self.curve)


@dataclass
class Table:
    """Every curve of a page against one reference."""

    reference: str
    rows: list[Row] = field(default_factory=list)
    page: str = ""
    analysis: str = ""

    def per_curve(self) -> dict[str, stats.Report]:
        found: dict[str, stats.Report] = {}
        for row in self.rows:
            report = found.setdefault(row.curve, stats.Report(left=row.curve, right=self.reference))
            report.rows.append(row.comparison)
        return found

    def markdown(self) -> str:
        lines = [f"# {self.page or 'comparison'}", "",
                 f"Reference: `{self.reference}`", ""]
        if self.analysis:
            lines += [f"Analysis: `{self.analysis}`", ""]
        lines += ["| curve | histogram | chi2/ndf | bins | max pull | note |",
                  "|---|---|---:|---:|---:|---|"]
        for row in sorted(self.rows, key=lambda entry: entry.sort_key):
            comparison = row.comparison
            value = f"{comparison.chi2_per_ndf:.3g}" if comparison.comparable else "—"
            pull = f"{comparison.max_pull:+.2g}" if comparison.comparable else "—"
            note = comparison.note or _skips(comparison)
            lines.append(f"| {row.curve} | {row.histogram} | {value} | {comparison.used} | "
                         f"{pull} | {note} |")
        lines += ["", "## Totals", "",
                  "| curve | chi2/ndf | bins | worst histogram |", "|---|---:|---:|---|"]
        for curve, report in sorted(self.per_curve().items()):
            worst = report.worst
            lines.append(f"| {curve} | {report.chi2_per_ndf:.3g} | {report.total_ndf} | "
                         f"{worst.path if worst else '—'} |")
        return "\n".join(lines) + "\n"

    def write(self, directory: Path) -> Path:
        return write_atomic(Path(directory) / NAME, self.markdown())


def _skips(comparison: stats.Comparison) -> str:
    parts = []
    if comparison.skipped_unaligned:
        parts.append(f"{comparison.skipped_unaligned} unaligned")
    if comparison.skipped_void:
        parts.append(f"{comparison.skipped_void} voided")
    if comparison.skipped_no_error:
        parts.append(f"{comparison.skipped_no_error} without errors")
    return ", ".join(parts)


def against_reference(page: Any) -> Table:
    """Every curve of a prepared page against the overlaid reference data (`--ref data`)."""
    if page.data is None or page.data.path is None:
        raise HepError("this page has no reference data to compare against",
                       hint="give [plot.data].file and a [plot.data].map, or use --ref POINT")
    table = Table(reference=str(page.data.path), page=page.name, analysis=page.analysis)
    references = io.read(page.data.path)
    for curve in page.curves:
        for obj_path, obj in sorted(io.read(curve.path).items()):
            if obj_path.startswith(("/RAW/", "/REF/")) or not io.is_binned_1d(obj):
                continue
            parsed = io.split_object_path(obj_path)
            if parsed is None:
                continue
            other = references.get(f"/REF/{io.base_analysis(parsed[0])}/{parsed[1]}")
            if other is None:
                continue
            table.rows.append(Row(curve=curve.name, histogram=parsed[1],
                                  comparison=stats.compare_objects(obj, other, path=obj_path)))
    return table


def against_curve(page: Any, reference_name: str) -> Table:
    """Every other curve of a page against one of them (`--ref POINT`)."""
    chosen = next((curve for curve in page.curves
                   if reference_name in {curve.name, curve.point}), None)
    if chosen is None:
        raise HepError(f"'{reference_name}' is not a curve of this page",
                       hint="curves: " + ", ".join(curve.name for curve in page.curves))
    table = Table(reference=chosen.name, page=page.name, analysis=page.analysis)
    references = io.read(chosen.path)
    for curve in page.curves:
        if curve.name == chosen.name:
            continue
        for obj_path, obj in sorted(io.read(curve.path).items()):
            if obj_path.startswith(("/RAW/", "/REF/")) or not io.is_binned_1d(obj):
                continue
            parsed = io.split_object_path(obj_path)
            other = references.get(obj_path)
            if parsed is None or other is None:
                continue
            table.rows.append(Row(curve=curve.name, histogram=parsed[1],
                                  comparison=stats.compare_objects(obj, other, path=obj_path)))
    return table


def render(table: Table, *, plain: bool = False) -> None:
    """Print the table the way 07 §5 describes: one row per curve and histogram."""
    import click

    if plain:
        click.echo(table.markdown())
        return

    from rich.console import Console
    from rich.table import Table as RichTable

    console = Console()
    grid = RichTable(title=f"{table.page or 'comparison'} vs {Path(table.reference).name}",
                     title_justify="left", box=None, pad_edge=False)
    for name, justify in (("curve", "left"), ("histogram", "left"), ("chi2/ndf", "right"),
                          ("bins", "right"), ("max pull", "right"), ("note", "left")):
        grid.add_column(name, justify=justify)
    for row in sorted(table.rows, key=lambda entry: entry.sort_key):
        comparison = row.comparison
        colour = _colour(comparison)
        grid.add_row(row.curve, row.histogram,
                     f"[{colour}]{comparison.chi2_per_ndf:.3g}[/]" if comparison.comparable else "—",
                     str(comparison.used),
                     f"{comparison.max_pull:+.2g}" if comparison.comparable else "—",
                     comparison.note or _skips(comparison))
    console.print(grid)

    totals = RichTable(box=None, pad_edge=False, title="totals", title_justify="left")
    for name in ("curve", "chi2/ndf", "bins", "worst histogram"):
        totals.add_column(name)
    for curve, report in sorted(table.per_curve().items()):
        worst = report.worst
        totals.add_row(curve, f"{report.chi2_per_ndf:.3g}", str(report.total_ndf),
                       worst.path if worst else "—")
    console.print()
    console.print(totals)


def _colour(comparison: stats.Comparison) -> str:
    """Green, yellow, red — a reader scanning sixty rows wants the eye drawn to the odd one."""
    if not comparison.comparable or math.isnan(comparison.chi2_per_ndf):
        return "dim"
    value = comparison.chi2_per_ndf
    if value < 2:
        return "green"
    return "yellow" if value < 5 else "red"
