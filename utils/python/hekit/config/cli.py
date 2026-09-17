"""`hep studies`: what a config offers (08 §2)."""

from __future__ import annotations

from pathlib import Path

import click

from . import load_config


@click.command("studies")
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="machine-readable output")
def studies(config_file: Path, as_json: bool):
    """List the studies a config declares, with their scans and point counts."""
    import json

    from ..sweep import expand, select

    config = load_config(config_file)
    rows = []
    for name, study in config.studies.items():
        try:
            selection = select(config, study=name)
            count = len(expand(config, selection))
            scan = ", ".join("+".join(group) for group in selection.groups) or "one point"
            overlay = "+".join(selection.overlay)
            rows.append({"name": name, "description": study.description, "points": count,
                         "scan": scan, "overlay": overlay, "error": ""})
        except Exception as error:               # a broken study must not hide the others
            rows.append({"name": name, "description": study.description, "points": 0,
                         "scan": "", "overlay": "", "error": str(error)})
    if as_json:
        click.echo(json.dumps(rows, indent=1))
        return
    if not rows:
        click.echo(f"{config_file}: no studies declared")
        return
    width = max(len(row["name"]) for row in rows)
    click.echo(f"{config_file}: {len(rows)} studies")
    for row in rows:
        detail = row["error"] or f"{row['points']:>3} points   scan: {row['scan']}" + \
            (f"   overlay: {row['overlay']}" if row["overlay"] else "")
        click.echo(f"  {row['name']:<{width}}  {detail}")
        if row["description"]:
            click.echo(f"  {'':<{width}}  {row['description']}")
