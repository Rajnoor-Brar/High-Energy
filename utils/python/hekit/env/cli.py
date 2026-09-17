"""`hep doctor` and `hep pdf` (08 §2, §4)."""

from __future__ import annotations

import json as json_module
from pathlib import Path

import click


@click.command("doctor")
@click.option("--json", "as_json", is_flag=True, help="machine-readable output (used by hep plan)")
@click.option("--brief", is_flag=True, help="one line per area (what hep_status shows)")
@click.option("--refresh", is_flag=True, help="re-probe instead of using the day-old cache")
def doctor(as_json: bool, brief: bool, refresh: bool):
    """Toolchain versions, Python imports, generator capabilities and environment sanity."""
    from . import doctor as checks

    found = checks.report(refresh=refresh)
    if as_json:
        click.echo(json_module.dumps(found.as_dict(), indent=1))
        return
    click.echo(checks.brief(found) if brief else checks.full(found))


@click.group("pdf")
def pdf():
    """LHAPDF sets: what a plan needs, what is installed, and installing the rest."""


@pdf.command("list")
@click.argument("pattern", required=False)
def list_sets(pattern: str | None):
    """The installed sets, optionally filtered."""
    from . import lhapdf

    sets = [name for name in lhapdf.installed_sets() if not pattern or pattern.lower() in name.lower()]
    for name in sets:
        click.echo(name)
    click.echo(f"{len(sets)} sets in {', '.join(str(path) for path in lhapdf.data_paths()) or 'nowhere'}",
               err=True)


@pdf.command("check")
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--study", help="check the sets this study needs")
@click.option("--json", "as_json", is_flag=True)
def check_sets(config_file: Path, study: str | None, as_json: bool):
    """Which PDF sets a config needs, and whether they are installed."""
    from ..config import load_config
    from ..plan import build as builder
    from ..sweep import select
    from . import lhapdf

    config = load_config(config_file)
    plan = builder.build(config, select(config, study=study))
    found = lhapdf.check(plan)
    if as_json:
        click.echo(json_module.dumps(found, indent=1))
    else:
        for name, present in found.items():
            click.echo(f"  {'ok     ' if present else 'MISSING'} {name}")
        missing = [name for name, present in found.items() if not present]
        click.echo(f"{len(found)} sets needed, {len(found) - len(missing)} installed")
        if missing:
            click.echo(f"install them with: hep pdf install {' '.join(missing)}")
    raise SystemExit(1 if any(not present for present in found.values()) else 0)


@pdf.command("install")
@click.argument("names", nargs=-1, required=True)
def install_sets(names: tuple[str, ...]):
    """Download PDF sets (this one reaches the network)."""
    from . import lhapdf

    lhapdf.install(list(names))
    click.echo(f"installed: {', '.join(names)}")
