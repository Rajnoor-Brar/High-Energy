"""`hep plan`: what a config expands to, without running anything (08 §2)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import click

from ..config import load_config
from ..sweep import select

SELECTORS = [
    click.option("--study", help="run a named [study.<name>]"),
    click.option("--pin", "pins", multiple=True, metavar="QUANTITY=SELECTOR",
                 help="hold a quantity at a tag, a value or '#N' (repeatable)"),
    click.option("--across", help="scanned groups, e.g. 'energies+beams,pdf' ('+' couples)"),
    click.option("--style", type=click.Choice(["together", "grid"]),
                 help="for a flat --across list: one coupled group, or one group each"),
    click.option("--overlay", help="quantity drawn as curves; the other groups become pages"),
    click.option("--set", "sets", multiple=True, metavar="KEY=VALUE",
                 help="override any single value (repeatable)"),
]


def selectors(command):
    for option in reversed(SELECTORS):
        command = option(command)
    return command


@click.command("plan")
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@selectors
@click.option("--index", type=int, help="only this 1-based point")
@click.option("--explain", metavar="KEY", help="where a configuration value came from, layer by layer")
@click.option("--json", "as_json", is_flag=True, help="machine-readable output")
@click.option("--write", type=click.Path(file_okay=False, path_type=Path),
              help="also write the resolved specs and cards here (default: a temporary directory)")
def plan(config_file: Path, study, pins, across, style, overlay, sets, index, explain, as_json, write):
    """Show the points, generations, pages and stage chains a config expands to."""
    from . import build as builder
    from . import spec as spec_module

    config = load_config(config_file, sets=tuple(sets))
    if explain:
        for layer, origin, value in config.explain(explain):
            click.echo(f"{layer:<12} {origin:<40} {value!r}")
        return
    selection = select(config, study=study, pins=tuple(pins), across=across, style=style, overlay=overlay)
    plan_result = builder.build(config, selection, index=index)

    directory = Path(write) if write else Path(tempfile.mkdtemp(prefix="hep-plan-"))
    written = spec_module.write(plan_result, directory)

    if as_json:
        click.echo(json.dumps(as_document(plan_result, directory), indent=1))
        return
    render(plan_result, directory, written)


def as_document(plan_result: Any, directory: Path) -> dict[str, Any]:
    """The plan as data, for scripting and for the golden tests."""
    return {
        "config": str(plan_result.config.path),
        "project": plan_result.config.project,
        "study": plan_result.study,
        "points": [{"number": point.number, "name": point.name, "suffix": point.suffix,
                    "legend": point.legend, "analyses": point.analyses,
                    "group": plan_result.group_of(point.name).name,
                    "settings": [[item.key, item.value, item.origin] for item in point.settings],
                    "beams": point.beams, "energies": point.energies, "events": point.events}
                   for point in plan_result.points],
        "groups": [{"name": group.name, "hash": group.identity.hash, "aliases": group.aliases,
                    "seed": group.seeds.point, "instances": list(group.seeds.instances),
                    "analyses": group.analyses, "directory": str(group.directory),
                    "stages": [stage.name for stage in group.stages], "spec": group.spec}
                   for group in plan_result.groups],
        "pages": [{"name": page.name, "suffix": page.suffix,
                   "members": [point.name for point in page.members], "legends": page.legends}
                  for page in plan_result.pages],
        "warnings": plan_result.warnings,
        "rendered": str(directory),
    }


def render(plan_result: Any, directory: Path, written: list[Path]) -> None:
    """The human-readable form: points, then generations, then pages."""
    config = plan_result.config
    head = f"{config.path} [{plan_result.study or 'default scan'}]"
    click.echo(f"{head}: {len(plan_result.points)} points, {len(plan_result.groups)} generations, "
               f"{len(plan_result.pages)} pages")
    scanned = ", ".join("+".join(group) for group in plan_result.selection.groups) or "nothing"
    click.echo(f"  scan: {scanned}"
               f"{'  overlay: ' + '+'.join(plan_result.selection.overlay) if plan_result.selection.overlay else ''}")

    click.echo("\npoints")
    for point in plan_result.points:
        group = plan_result.group_of(point.name)
        shared = "" if len(group.points) == 1 else f"  (events: {group.name})"
        click.echo(f"  {point.number:>3}  {point.name}{shared}")
        click.echo(f"       analyses: {', '.join(point.analyses) or 'none'}")
        if point.legend:
            click.echo(f"       legend:   {point.legend}")

    click.echo("\ngenerations")
    for group in plan_result.groups:
        click.echo(f"  {group.name}")
        click.echo(f"       identity: {group.identity.short}  seeds: {group.seeds.point}"
                   f"…{group.seeds.instances[-1]} ({len(group.seeds.instances)} instances)")
        if len(group.aliases) > 1:
            click.echo(f"       also:     {', '.join(name for name in group.aliases if name != group.name)}")
        click.echo(f"       stages:   {' → '.join(stage.name for stage in group.stages)}")
        click.echo(f"       output:   {group.directory}")

    if plan_result.pages:
        click.echo("\npages")
        for page in plan_result.pages:
            click.echo(f"  {page.name}: {len(page.members)} curves "
                       f"({', '.join(page.legends) if page.legends else ''})")

    for warning in plan_result.warnings:
        click.echo(f"\nwarning: {warning}")
    click.echo(f"\nrendered {len(written)} files into {directory}")
