"""`hep doctor` and `hep pdf` (08 §2, §4)."""

from __future__ import annotations

import json as json_module
import subprocess
from pathlib import Path
from typing import Any

import click

from ..errors import HepError


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


# ── hep analyses ─────────────────────────────────────────────────────────────

@click.command("analyses")
@click.argument("pattern", required=False)
@click.option("--options", "show_options", is_flag=True, help="list each analysis's options")
@click.option("--paths", "show_paths", is_flag=True, help="where each one was found")
def analyses(pattern: str | None, show_options: bool, show_paths: bool) -> None:
    """Rivet analyses with their `.info` summaries, options and reference data (06 §5).

    A prettier `rivet --list-analyses`: it reads the same `.info` files Rivet does, including the
    project's own plugins, so a locally built analysis is listed beside the published ones.
    """
    from ..plot.plotfile import search_paths

    found = _analysis_entries(pattern, extra_paths=[path for project in _projects()
                                                    for path in search_paths(project)])
    if not found:
        click.echo(f"no analyses match {pattern!r}" if pattern else "no analyses found", err=True)
        return

    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(box=None, pad_edge=False)
    table.add_column("analysis")
    table.add_column("summary", overflow="fold")
    if show_paths:
        table.add_column("from", style="dim", overflow="fold")
    for entry in found:
        row = [entry["name"], entry.get("summary", "")]
        if show_paths:
            row.append(entry.get("path", ""))
        table.add_row(*row)
        if show_options and entry.get("options"):
            for option in entry["options"]:
                table.add_row("", f"[dim]  {option}[/dim]", *([""] if show_paths else []))
    console.print(table)


def _projects() -> list[str]:
    from .paths import analyses_root

    root = analyses_root()
    return sorted(entry.name for entry in root.iterdir() if entry.is_dir()) if root.is_dir() else []


def _analysis_entries(pattern: str | None, extra_paths: list[Path]) -> list[dict[str, Any]]:
    """Every analysis Rivet can load, from its own list and from the project plugin directories."""
    import fnmatch

    found: dict[str, dict[str, Any]] = {}
    for directory in extra_paths:
        for info in sorted(Path(directory).glob("*.info")):
            # First wins: `search_paths` is build tree, then source, then output, so a listed
            # analysis is the one Rivet would actually load (P4-S01).
            found.setdefault(info.stem, {"name": info.stem, "path": str(info), **_read_info(info)})
    for name in _rivet_analysis_names():
        found.setdefault(name, {"name": name, "path": "(installed with Rivet)"})

    entries = sorted(found.values(), key=lambda entry: entry["name"])
    if pattern:
        entries = [entry for entry in entries
                   if fnmatch.fnmatch(entry["name"].lower(), f"*{pattern.lower()}*")]
    return entries


def _read_info(path: Path) -> dict[str, Any]:
    """The few `.info` fields worth showing. Parsed loosely: an unreadable file costs one row."""
    summary, options, inside = "", [], False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:                                        # pragma: no cover
        return {}
    for line in text.splitlines():
        if line.startswith("Summary:"):
            summary = line.partition(":")[2].strip().strip("'\"")
        elif line.startswith("Options:"):
            inside = True
        elif inside:
            if line.startswith(" -") or line.startswith("- "):
                options.append(line.strip(" -").strip())
            elif line and not line[0].isspace():
                inside = False
    return {"summary": summary, "options": options}


def _rivet_analysis_names() -> list[str]:
    from shutil import which

    if which("rivet") is None:
        return []
    try:
        done = subprocess.run(["rivet", "--list-analyses"], capture_output=True, text=True,
                              timeout=60)
    except (OSError, subprocess.SubprocessError):           # pragma: no cover
        return []
    return [line.split()[0] for line in done.stdout.splitlines() if line.strip()]


# ── hep build ────────────────────────────────────────────────────────────────

@click.command("build")
@click.argument("targets", nargs=-1)
@click.option("--analyses", "analysis_project", default="", metavar="PROJECT",
              help="build a project's Rivet plugins")
@click.option("--modules", "module_project", default="", metavar="PROJECT",
              help="build a project's analysis modules")
@click.option("--clean", is_flag=True, help="configure from scratch first")
@click.option("--jobs", "-j", type=int, default=0, help="parallel jobs (default: all cores)")
@click.option("--dry-run", is_flag=True, help="print the cmake commands instead of running them")
def build(targets: tuple[str, ...], analysis_project: str, module_project: str, clean: bool,
          jobs: int, dry_run: bool) -> None:
    """Build analyses, modules and `hep-run` (wraps cmake).

    This is the replacement for `make PhotoProduction/photo_eic.so`: one build directory, one
    configuration, and the same targets CMake already defines.
    """
    import os
    import shutil

    from .paths import build_root, repo_root

    if shutil.which("cmake") is None:
        raise HepError("cmake is not on PATH", hint="`hep doctor` reports the toolchain")

    root, directory = repo_root(), build_root()
    wanted = list(targets)
    if analysis_project:
        wanted.append(f"rivet_{analysis_project}")
    if module_project:
        wanted.append(f"modules_{module_project}")

    commands = []
    if clean and directory.exists():
        commands.append(["cmake", "-E", "rm", "-rf", str(directory)])
    if clean or not (directory / "CMakeCache.txt").is_file():
        commands.append(["cmake", "-S", str(root), "-B", str(directory)])
    line = ["cmake", "--build", str(directory)]
    if jobs:
        line += ["-j", str(jobs)]
    for target in wanted:
        line += ["--target", target]
    commands.append(line)

    for command in commands:
        if dry_run:
            click.echo(" ".join(command))
            continue
        status = subprocess.run(command, cwd=root).returncode
        if status:
            raise HepError(f"cmake failed with status {status}",
                           hint="run it by hand: " + " ".join(command))
    if not dry_run:
        click.echo(f"hep build: {', '.join(wanted) if wanted else 'everything'} → {directory}")


@click.command("new")
@click.argument("kind", type=click.Choice(["analysis", "module", "project"]))
@click.argument("name")
@click.option("--project", default="", metavar="NAME",
              help="which project an analysis or module belongs to (default: its own name)")
@click.option("--into", type=click.Path(file_okay=False, path_type=Path),
              help="write here instead of the repository's analyses/, modules/ or configs/")
def new(kind: str, name: str, project: str, into: Path | None) -> None:
    """Scaffold an analysis, module or project.

    What it writes builds and runs as it stands — a template with a TODO where the important line
    goes teaches nothing and costs a search through the docs anyway.
    """
    from . import paths, scaffold

    scaffold.check_name(name, kind)
    root = Path(into) if into else paths.repo_root()
    written: list[Path] = []

    if kind == "analysis":
        where = root / "analyses" / (project or name)
        written.append(scaffold.write(where / f"{name}.cc", scaffold.analysis_source(name)))
        written.append(scaffold.write(where / f"{name}.info", scaffold.analysis_info(name)))
        after = (f"hep build && hep analyses {name}    # then name it in [rivet].analyses")
    elif kind == "module":
        where = root / "modules" / (project or name)
        written.append(scaffold.write(where / f"{name}.cc", scaffold.module_source(name)))
        after = (f"hep build    # then [[sinks.module]] name = \"{name}\"")
    else:
        where = root / "configs" / name
        written.append(scaffold.write(where / "base.cmnd", scaffold.project_card(name)))
        written.append(scaffold.write(
            where / f"{name.lower()}.toml", scaffold.project_config(name, f"{name}Analysis")))
        after = f"hep new analysis {name}Analysis --project {name} && hep plan {written[-1]}"

    for path in written:
        click.echo(f"hep new: {path}")
    click.echo(f"hep new: next, {after}")
