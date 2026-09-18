"""`hep runs` and `hep show`: what has been run, and what one result is made of (06 §5–6).

Both read files only. A run that is still going is not interrogated — its `status.jsonl` and `run.pid`
say everything — and a finished one is explained entirely by what it left behind: `run.summary.json`,
`provenance.json`, the outputs and the logs. That is the test of whether a result is self-describing,
and it is why both commands work on a directory copied from another machine.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from ..env import paths
from ..errors import HepError
from ..prov import provenance as prov
from ..run import journal
from ..term import theme
from . import manifest
from .layout import serial_of, study_of


def _console(plain: bool = False):
    import sys

    from rich.console import Console

    theme.autodetect(sys.stdout)          # ASCII fallback where the locale cannot hold "σ" or "·"
    return Console(no_color=plain, highlight=not plain, safe_box=True)


def project_roots(project: str = "") -> list[Path]:
    root = paths.results_root()
    if not root.is_dir():
        return []
    if project:
        return [root / project] if (root / project).is_dir() else []
    return [entry for entry in sorted(root.iterdir()) if entry.is_dir()]


def point_dirs(project: str = "") -> list[Path]:
    found: list[Path] = []
    for root in project_roots(project):
        points = root / "points"
        if points.is_dir():
            found.extend(entry for entry in sorted(points.iterdir()) if entry.is_dir())
    return found


def study_dirs(project: str = "") -> list[Path]:
    found: list[Path] = []
    for root in project_roots(project):
        studies = root / "studies"
        if studies.is_dir():
            found.extend(entry for entry in sorted(studies.iterdir()) if entry.is_dir())
    return found


def summary_of(directory: Path) -> dict:
    path = directory / "run.summary.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def state_of(directory: Path) -> str:
    """What a point directory holds, in one word."""
    if journal.running_pid(directory):
        return "running"
    summary = summary_of(directory)
    if summary.get("run", {}).get("stopped"):
        return "stopped"
    if any(directory.glob("*.partial.yoda")):
        return "stopped"
    if (directory / "analysis.yoda").is_file():
        return "done"
    return "incomplete"


# ── hep runs ─────────────────────────────────────────────────────────────────

@click.command()
@click.option("--project", default="", help="only this project")
@click.option("--limit", default=20, show_default=True, help="how many rows to show")
@click.option("--json", "as_json", is_flag=True, help="machine-readable output")
@click.pass_context
def runs(context: click.Context, project: str, limit: int, as_json: bool) -> None:
    """List runs: the ones going on now, and the most recent studies and points."""
    active = []
    for directory in point_dirs(project) + study_dirs(project):
        pid = journal.running_pid(directory)
        if pid:
            active.append({"path": str(directory), "pid": pid, "name": directory.name})

    studies = []
    for directory in study_dirs(project):
        payload = manifest.read(directory) or {}
        studies.append({
            "path": str(directory), "name": directory.name,
            "serial": serial_of(directory.name), "study": payload.get("study",
                                                                      study_of(directory.name)),
            "label": payload.get("label", ""), "points": len(payload.get("points", []) or []),
            "finished": payload.get("finished", ""), "exit": payload.get("exit"),
        })
    studies.sort(key=lambda row: (row["serial"] or 0, row["name"]), reverse=True)

    points = []
    for directory in point_dirs(project):
        summary = summary_of(directory)
        run = summary.get("run", {})
        points.append({
            "path": str(directory), "name": directory.name, "state": state_of(directory),
            "events": run.get("events", 0), "xsec_pb": run.get("xsec_pb"),
            "err_pb": run.get("xsec_err_pb"), "wall_s": run.get("wall_s"),
            "finished": summary.get("finished", ""),
        })
    points.sort(key=lambda row: row["finished"], reverse=True)

    if as_json:
        click.echo(json.dumps({"active": active, "studies": studies[:limit],
                               "points": points[:limit]}, indent=2))
        return

    console = _console((context.obj or {}).get("plain", False))
    if not active and not studies and not points:
        console.print(f"[dim]no results under {paths.results_root()}[/dim]")
        return

    from rich.table import Table

    if active:
        table = Table(title="running now", title_justify="left", box=None, pad_edge=False)
        table.add_column("pid", style="dim")
        table.add_column("run")
        table.add_column("path", style="dim")
        for row in active:
            table.add_row(str(row["pid"]), row["name"], row["path"])
        console.print(table)
        console.print()

    if studies:
        table = Table(title="studies", title_justify="left", box=None, pad_edge=False)
        for name in ("run", "study", "label", "points", "finished", "exit"):
            table.add_column(name, style="dim" if name in {"label", "finished"} else None)
        for row in studies[:limit]:
            table.add_row(row["name"], row["study"], row["label"] or "", str(row["points"]),
                          row["finished"][:19], "" if row["exit"] in (None, 0) else str(row["exit"]))
        console.print(table)
        console.print()

    if points:
        table = Table(title="points", title_justify="left", box=None, pad_edge=False)
        for name in ("point", "state", "events", "sigma", "wall"):
            table.add_column(name)
        for row in points[:limit]:
            table.add_row(row["name"],
                          f"[{theme.COLOUR.get(row['state'], '')}]{row['state']}[/]",
                          theme.count(row["events"]),
                          theme.sigma(row["xsec_pb"], row["err_pb"]),
                          theme.duration(row["wall_s"]))
        console.print(table)


# ── hep show ─────────────────────────────────────────────────────────────────

@click.command()
@click.argument("target")
@click.option("--project", default="", help="only this project")
@click.option("--json", "as_json", is_flag=True, help="print the provenance document itself")
@click.pass_context
def show(context: click.Context, target: str, project: str, as_json: bool) -> None:
    """Everything known about a point: cross section, counts, seeds, warnings, outputs, provenance."""
    directory = find_point(target, project=project)
    summary = summary_of(directory)
    provenance = prov.read(directory) or {}

    if as_json:
        click.echo(json.dumps(provenance or summary, indent=2))
        return

    console = _console((context.obj or {}).get("plain", False))
    from rich.table import Table

    run = summary.get("run", {})
    console.print(f"[bold]{summary.get('point') or directory.name}[/bold]  "
                  f"[dim]{directory}[/dim]")
    if summary.get("hash"):
        console.print(f"[dim]{summary['hash']}[/dim]")

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column()

    def row(label: str, value: str) -> None:
        if value not in ("", None):
            table.add_row(label, str(value))

    row("state", state_of(directory))
    row("events", f"{theme.count(run.get('events'))} of {theme.count(run.get('events_requested'))}"
                  f"   ({run.get('attempted', 0)} attempted)" if run else "")
    row("sigma", theme.sigma(run.get("xsec_pb"), run.get("xsec_err_pb")) if run.get("xsec_pb") else "")
    row("wall", theme.duration(run.get("wall_s")) if run.get("wall_s") else "")
    row("threads", f"{run.get('threads')}  ({run.get('mode', 'serial')}, chunk {run.get('chunk')})"
        if run.get("threads") else "")
    seeds = run.get("seeds", {})
    row("seeds", f"point {seeds.get('point')}  instances {seeds.get('instances')}" if seeds else "")
    row("origin", summary.get("origin", ""))
    row("host", f"{summary.get('host', '')}  {summary.get('finished', '')}")
    git = provenance.get("git") or {}
    row("git", f"{git.get('sha', '')}{'+dirty' if git.get('dirty') else ''}"
               f"  {git.get('branch', '')}" if git.get("sha") else "")
    tools = provenance.get("tools") or {}
    row("tools", "  ".join(f"{name} {version}" for name, version in sorted(tools.items())))
    console.print(table)

    warnings = run.get("warnings") or {}
    if warnings:
        console.print("\n[bold]warnings[/bold]")
        warning_table = Table.grid(padding=(0, 2))
        warning_table.add_column(justify="right", style="yellow")
        warning_table.add_column()
        for message, count in sorted(warnings.items(), key=lambda item: -item[1]):
            warning_table.add_row(f"×{count}", message[:100])
        console.print(warning_table)

    analyses = (provenance.get("resources") or {}).get("analyses") or {}
    if analyses:
        console.print("\n[bold]analyses[/bold]")
        analysis_table = Table.grid(padding=(0, 2))
        analysis_table.add_column()
        analysis_table.add_column(style="dim")
        for name, entry in sorted(analyses.items()):
            analysis_table.add_row(name, (entry.get("so_sha256") or "")[:16])
        console.print(analysis_table)

    outputs = provenance.get("outputs") or summary.get("outputs") or []
    if outputs:
        console.print("\n[bold]outputs[/bold]")
        output_table = Table.grid(padding=(0, 2))
        output_table.add_column()
        output_table.add_column(justify="right", style="dim")
        for entry in outputs:
            path = entry.get("path", "")
            size = entry.get("bytes")
            output_table.add_row(Path(path).name if path else "",
                                 f"{size / 1024:.0f} KiB" if size else "")
        console.print(output_table)

    logs = sorted((directory / "logs").glob("*.log")) if (directory / "logs").is_dir() else []
    if logs:
        console.print("\n[bold]logs[/bold]")
        for path in logs:
            console.print(f"  [dim]{path}[/dim]")
        settings = changed_settings(logs)
        if settings:
            console.print("\n[bold]settings the generator changed[/bold]")
            setting_table = Table.grid(padding=(0, 2))
            setting_table.add_column(style="dim")
            setting_table.add_column()
            for key, value in settings:
                setting_table.add_row(key, value)
            console.print(setting_table)


def changed_settings(logs: list[Path], limit: int = 40) -> list[tuple[str, str]]:
    """Pythia's `Init:showChangedSettings` block, if a log holds one (06 §5).

    Parsed rather than stored: the generator already prints exactly what it changed, and copying that
    into provenance would be a second source of truth that can disagree with the run.
    """
    found: list[tuple[str, str]] = []
    for path in logs:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        inside = False
        for line in text.splitlines():
            if "Changed settings" in line or "PYTHIA Settings" in line:
                inside = True
                continue
            if inside:
                if line.strip().startswith("---") or not line.strip():
                    if found:
                        inside = False
                    continue
                parts = line.split()
                if len(parts) >= 2 and ":" in parts[0]:
                    found.append((parts[0], " ".join(parts[1:])))
                if len(found) >= limit:
                    return found
    return found


def find_point(target: str, *, project: str = "") -> Path:
    candidate = Path(target)
    if candidate.is_dir():
        return candidate
    matches = [entry for entry in point_dirs(project) if entry.name == target]
    if not matches:
        near = [entry.name for entry in point_dirs(project) if target in entry.name]
        raise HepError(f"no point called '{target}'",
                       hint=("did you mean: " + ", ".join(near[:5])) if near
                            else "`hep runs` lists what is there")
    return matches[0]
