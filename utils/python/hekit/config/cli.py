"""`hep studies` and `hep config`: inspecting, migrating and documenting configuration (08 §2)."""

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


@click.group("config")
def config():
    """Start, check, migrate and document configuration files."""


@config.command("validate")
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False, allow_dash=True, path_type=Path))
def validate(config_file: Path):
    """Load a config and report what it says, or why it cannot be loaded."""
    import sys
    import tempfile

    path = config_file
    if str(config_file) == "-":
        text = sys.stdin.read()
        handle = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        path = Path(handle.name)
    loaded = load_config(path)
    click.echo(f"{config_file}: valid schema-{loaded.schema} configuration for project "
               f"'{loaded.project}'")
    click.echo(f"  generator: {loaded.generator.tool}  analyses: {', '.join(loaded.rivet.analyses) or 'none'}")
    click.echo(f"  quantities: {', '.join(loaded.quantities) or 'none'}")
    click.echo(f"  studies: {', '.join(loaded.studies) or 'none'}")
    for warning in loaded.warnings:
        click.echo(f"  warning: {warning}")


@config.command("migrate")
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--stdout", "to_stdout", is_flag=True, help="print the result instead of writing it")
@click.option("--write", type=click.Path(dir_okay=False, path_type=Path),
              help="where to write (default: <name>.v2.toml next to the original)")
@click.option("--keep-tags", is_flag=True, help="do not rename misleading tags (00/B12)")
@click.option("--force", is_flag=True, help="overwrite an existing file")
def migrate(config_file: Path, to_stdout: bool, write: Path | None, keep_tags: bool, force: bool):
    """Translate a schema-1 file into schema 2, reporting every change."""
    from .migrate import dumps, migrate_file

    target = write or config_file.with_suffix(".v2.toml")
    result = migrate_file(config_file, rename_tags=not keep_tags)
    text = dumps(result, name=target.name, source=str(config_file))
    if to_stdout:
        click.echo(text)
        return
    if target.exists() and not force:
        import sys

        # never block on a prompt that nothing can answer (a script, a pipe, an agent)
        if not sys.stdin.isatty():
            raise click.ClickException(f"{target} exists; pass --force to overwrite it")
        if not click.confirm(f"{target} exists; overwrite?", default=False):
            raise click.Abort
    target.write_text(text, encoding="utf-8")
    click.echo(f"{config_file} → {target}")
    for note in result.notes:
        click.echo(f"  - {note}")


@config.command("reference")
@click.option("--write", type=click.Path(dir_okay=False, path_type=Path),
              help="where to write (default: print)")
def reference(write: Path | None):
    """The configuration reference, generated from the schema."""
    from .reference import markdown

    text = markdown()
    if write:
        write.parent.mkdir(parents=True, exist_ok=True)
        write.write_text(text, encoding="utf-8")
        click.echo(f"wrote {write} ({len(text.splitlines())} lines)")
    else:
        click.echo(text)


@config.command("init")
@click.argument("project")
@click.option("--write", type=click.Path(dir_okay=False, path_type=Path),
              help="where to write (default: print)")
def init(project: str, write: Path | None):
    """A commented starter configuration for a new project."""
    from .reference import starter

    text = starter(project)
    if write:
        if write.exists():
            raise click.ClickException(f"{write} exists")
        write.parent.mkdir(parents=True, exist_ok=True)
        write.write_text(text, encoding="utf-8")
        click.echo(f"wrote {write}")
        click.echo("next: set [rivet].analyses (or add a [[analyzers.module]]), then run hep plan")
    else:
        click.echo(text)
