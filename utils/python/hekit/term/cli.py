"""`hep watch`: the same dashboard, from a file, from anywhere (06 §6).

A run writes `status.jsonl` as it goes, so watching it needs no shared terminal and no connection to
the process — a second terminal, an SSH session, or a session that attaches an hour later all render
the same thing from the same file. On a pipe it degrades to plain lines, because a progress bar in a
log is noise.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import click

from ..errors import HepError
from ..run import journal
from . import model
from .plain import PlainRenderer, render_lines

POLL = 0.25


def find_run(target: str, *, project: str = "") -> Path:
    """The directory of a run: `latest`, a point or study name, or a path."""
    from ..env import paths

    candidate = Path(target)
    if candidate.is_dir() and (candidate / journal.NAME).is_file():
        return candidate
    if candidate.is_file():
        return candidate.parent

    root = paths.results_root()
    roots = [root / project] if project else [entry for entry in sorted(root.iterdir())
                                             if entry.is_dir()] if root.is_dir() else []
    found: list[Path] = []
    for base in roots:
        found.extend(path.parent for path in base.glob(f"*/*/{journal.NAME}"))
    if not found:
        raise HepError(f"no run to watch under {root}",
                       hint="start one with `hep run`, or give a directory holding status.jsonl")
    if target in {"latest", ""}:
        return max(found, key=lambda path: (path / journal.NAME).stat().st_mtime)
    named = [path for path in found if path.name == target]
    if not named:
        raise HepError(f"no run called '{target}'",
                       hint="`hep runs` lists them; `hep watch latest` takes the newest")
    return max(named, key=lambda path: (path / journal.NAME).stat().st_mtime)


@click.command()
@click.argument("target", default="latest")
@click.option("--project", default="", help="look only in this project's results")
@click.option("--follow/--no-follow", default=True, help="keep watching until the run ends")
@click.option("--plain", "force_plain", is_flag=True, help="plain lines, even on a terminal")
@click.option("--log-tail", default=6, show_default=True, help="curated log lines to keep on screen")
@click.pass_context
def watch(context: click.Context, target: str, project: str, follow: bool, force_plain: bool,
          log_tail: int) -> None:
    """Attach to a run and render it, read-only.

    TARGET is `latest` (the default), a point or study directory name, or a path.
    """
    from . import theme

    theme.autodetect(sys.stdout)          # a C-locale log must not die on a "σ"
    directory = find_run(target, project=project)
    path = directory / journal.NAME
    plain = force_plain or (context.obj or {}).get("plain") or not sys.stdout.isatty()

    view = model.from_journal(journal.read(path), log_tail=log_tail)
    alive = journal.running_pid(directory)

    if not follow or (alive is None and view.finished):
        if plain:
            for line in render_lines(view):
                click.echo(line)
        else:
            from .dashboard import render_once
            click.echo(render_once(view), nl=False)
        return

    if plain:
        _follow_plain(path, view)
    else:
        _follow_live(path, view, log_tail=log_tail)


def _follow_plain(path: Path, view: model.RunView) -> None:
    renderer = PlainRenderer(view=view, stream=sys.stdout)
    renderer.run_started()
    seen = len(journal.read(path))
    renderer.refresh()
    while view.finished == 0.0:
        lines = journal.read(path)
        if len(lines) > seen:
            fresh = lines[seen:]
            seen = len(lines)
            _feed(view, fresh)
            renderer.refresh()
        else:
            time.sleep(POLL)
    renderer.run_finished()


def _follow_live(path: Path, view: model.RunView, *, log_tail: int) -> None:
    from .dashboard import Dashboard

    seen = len(journal.read(path))
    with Dashboard(view=view) as dashboard:
        while view.finished == 0.0:
            lines = journal.read(path)
            if len(lines) > seen:
                _feed(view, lines[seen:])
                seen = len(lines)
            dashboard.refresh()
            time.sleep(POLL)


def _feed(view: model.RunView, lines: list[str]) -> None:
    """Fold new journal lines into an existing view (the same reader `from_journal` uses)."""
    fresh = model.from_journal(lines, log_tail=view.log_tail)
    # Rebuilding is simpler and fast enough for a poll loop: a journal is a few thousand lines.
    for point in fresh.points:
        existing = view.point(point.name)
        for name, stage in point.stages.items():
            existing.stages[name] = stage
        for attribute in ("events", "events_wanted", "xsec_pb", "xsec_err_pb", "xsec_final",
                          "exit_code", "reason", "finished"):
            value = getattr(point, attribute)
            if value:
                setattr(existing, attribute, value)
        if point.state != model.QUEUED:
            existing.state = point.state
        for entry in point.logs:
            view.log(existing, entry.level, entry.source, entry.message, entry.time)
        for output in point.outputs:
            if output not in existing.outputs:
                existing.outputs.append(output)
    if fresh.command:
        view.command = fresh.command
    if fresh.finished:
        view.finish(fresh.exit_code or 0, fresh.finished)


@click.command()
@click.argument("target", default="")
@click.option("-n", "--events", default=3, show_default=True, help="how many events to show")
def events(target: str, events: int) -> None:                # pragma: no cover - P5-S03
    """Inspect events from a config, point or store."""
    from ..errors import NotImplementedYet
    raise NotImplementedYet("events", "P5-S03")
