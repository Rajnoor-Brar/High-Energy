"""`hep plot`: draw pages, or one point at a time (08 §2).

This replaces two commands. `ydmrg` drew a page per sweep group and `ydplt` drew one point on its own;
they shared their pipeline by copy. Here there is one pipeline (P4-S01), one page assembler, and a
`--points` flag that says "one curve per page" — because a single point is just a page with one curve,
and the ratio panels, voiding and data overlay should behave identically either way.

Where pages go: `results/<project>/studies/[NN_]<study>/plots/<page>/`, next to the manifest of the run
that produced the points (07 §1). `--out` overrides it for a quick look.
"""

from __future__ import annotations

import contextlib
import sys
import tempfile
from pathlib import Path
from typing import Any

import click

from ..config import load_config
from ..errors import HepError
from ..plan.cli import selectors
from ..results import layout as layout_module
from ..sweep import select as select_points
from . import page as page_module


@click.command("plot")
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@selectors
@click.option("--backend", type=click.Choice(["mkhtml", "mpl"]), help="override [plot].backend")
@click.option("--points", "per_point", is_flag=True, help="one page per point instead of per group")
@click.option("--out", type=click.Path(file_okay=False, path_type=Path),
              help="write the pages here instead of into the study directory")
@click.option("--keep", is_flag=True, help="keep the intermediate YODA files beside the pages")
@click.option("--open", "open_it", is_flag=True, help="open the first page when it is drawn")
@click.option("--suggest-data-map", is_flag=True,
              help="print a [plot.data].map that matches by histogram name, to review and paste")
@click.pass_context
def plot(context: click.Context, config_file: Path, study, pins, across, style, overlay, sets,
         backend, per_point, out, keep, open_it, suggest_data_map) -> None:
    """Draw pages or single points from existing results."""
    from ..plan import build as builder

    config = load_config(config_file, sets=tuple(sets))
    selection = select_points(config, study=study, pins=tuple(pins), across=across, style=style,
                              overlay=overlay)
    plan = builder.build(config, selection, check_analyses=False)
    layout = layout_module.Layout.of(config)
    chosen = backend or config.plot.backend

    if suggest_data_map:
        _suggest(plan, layout)
        return

    pages = _pages(plan, per_point)
    if not pages:
        raise HepError("nothing to plot", hint="`hep plan` shows what a config expands to")

    destination = Path(out) if out else _study_plots(layout, plan)
    drawn = []
    for spec in pages:
        # `--keep` puts the intermediates beside the page; otherwise they live in a directory that is
        # removed when the page is drawn. Either way nothing is left in a shared temporary tree
        # (00/B19) — the old tools' fixed /tmp names are what that finding is about.
        with contextlib.ExitStack() as stack:
            if keep:
                workdir = destination / spec.name / "_work"
            else:
                workdir = Path(stack.enter_context(
                    tempfile.TemporaryDirectory(prefix="hekit-plot-")))
            built = page_module.prepare_from_config(plan, layout, spec, workdir,
                                                    proc_dir=_proc_dir(layout, plan))
            for warning in built.warnings:
                click.echo(f"hep plot: {warning}", err=True)
            if built.voided is not None and built.voided.bins:
                click.echo(f"hep plot: {built.voided}", err=True)
            drawn.append(_draw(built, destination / spec.name, chosen, config, layout))
            click.echo(f"hep plot: {spec.name} ({len(built.curves)} curves) → {drawn[-1]}")

    if open_it and drawn:
        click.launch(str(drawn[0]))


def _draw(built: Any, output: Path, backend: str, config: Any, layout: Any) -> Path:
    if backend == "mpl":
        from ..plot.backends import mpl

        result = mpl.draw(built, output, style=mpl.Style.of(config),
                          data_legend=config.plot.data.legend)
        for key, reason in result.skipped.items():
            click.echo(f"hep plot: {key} skipped: {reason}", err=True)
        if not result.ok:
            raise HepError(f"nothing was drawn for page {built.name}")
        return mpl.index_html(result, built)

    from ..plot.backends import mkhtml
    from . import plotfile

    result = mkhtml.draw(built, output, rivet_refs=config.plot.data.rivet_refs,
                         data_legend=config.plot.data.legend,
                         analysis_paths=plotfile.search_paths(config.project))
    if not result.ok:
        raise HepError(f"{mkhtml.TOOL} failed with status {result.status} on page {built.name}",
                       hint="run it by hand: " + " ".join(result.command or []))
    return result.index


def _pages(plan: Any, per_point: bool) -> list[Any]:
    """The pages to draw: the plan's own, or one per point with `--points`."""
    if not per_point:
        return list(plan.pages)

    from ..plan.model import Page

    return [Page(name=point.name, suffix=getattr(point, "suffix", ""), members=[point],
                 legends=[point.legend or point.name]) for point in plan.points]


def _study_plots(layout: Any, plan: Any) -> Path:
    """`studies/<latest run of this study>/plots/`, or a new study directory when there is none."""
    study = plan.study or "adhoc"
    latest = layout.latest_study(study)
    if latest is None:
        latest = layout.new_study(study, serial=bool(getattr(plan.config.run, "serial", True)))
    return layout.pages(latest)


def _proc_dir(layout: Any, plan: Any) -> Path | None:
    """Where `hep proc` wrote, when it has been run for this study (12 §3)."""
    latest = layout.latest_study(getattr(plan, "study", "") or "adhoc")
    return (latest / "proc") if latest is not None else None


def _suggest(plan: Any, layout: Any) -> None:
    """Print a `[plot.data].map` the user can review — never applied automatically (00/B5)."""
    from . import data as data_module

    file_path = page_module._data_path(plan.config)
    if not file_path:
        raise HepError("no [plot.data].file to suggest a map for")
    first = plan.pages[0] if plan.pages else None
    if first is None:
        raise HepError("nothing to compare the data against")
    points = page_module.points_of(plan, layout, first)
    absent = page_module.missing(points)
    if absent:
        raise HepError("these results have not been produced yet:\n  " + "\n  ".join(absent))

    from . import select as select_module

    curves = select_module.curves_for(points, analysis=plan.config.plot.analysis)
    analysis = select_module.common_analysis(curves, override=plan.config.plot.analysis)
    found = data_module.suggest_map(file_path, [curve.path for curve in curves], analysis)
    if not found:
        click.echo("hep plot: no histogram names match; the map has to be written by hand", err=True)
        return
    click.echo("# review these before using them: a name match is not a physics match (00/B5)")
    click.echo("[plot.data]")
    click.echo("map = {")
    for histogram, source in sorted(found.items()):
        click.echo(f'    "{histogram}" = "{source}",')
    click.echo("}")
