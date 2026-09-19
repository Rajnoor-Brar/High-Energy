"""`hep watch`: the same dashboard, from a file, from anywhere (06 §6).

A run writes `status.jsonl` as it goes, so watching it needs no shared terminal and no connection to
the process — a second terminal, an SSH session, or a session that attaches an hour later all render
the same thing from the same file. On a pipe it degrades to plain lines, because a progress bar in a
log is noise.
"""

from __future__ import annotations

import shutil
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


@click.command("events")
@click.argument("target", default="")
@click.option("-n", "--events", "count", default=3, show_default=True,
              help="how many events to show")
@click.option("--from", "from_file", type=click.Path(exists=True, path_type=Path),
              help="read this HepMC3 file instead of finding events for TARGET")
@click.option("--tree", is_flag=True, help="show the decay tree instead of a table")
@click.option("--final", "final_only", is_flag=True, help="final-state particles only")
@click.option("--hard", "hard_only", is_flag=True, help="the hard process only")
@click.option("--limit", default=0, help="at most this many particles per event (0 = all)")
@click.pass_context
def events(context: click.Context, target: str, count: int, from_file: Path | None, tree: bool,
           final_only: bool, hard_only: bool, limit: int) -> None:
    """Inspect events from a config, a point, a store or a HepMC3 file (06 §5).

    TARGET is a store directory, a point directory, a config file, or a point name. With no target,
    the newest store under the results tree is used.
    """
    from . import events as events_module
    from . import theme

    theme.autodetect(sys.stdout)
    source = from_file if from_file is not None else _events_source(target, count)
    found = events_module.read_events(source, limit=count)
    if not found:
        raise HepError(f"no events in {source}")

    from rich.console import Console

    console = Console(no_color=(context.obj or {}).get("plain", False))
    console.print(f"[dim]{source}[/dim]")
    for event in found:
        particles = events_module.select(event, final=final_only, hard=hard_only, limit=limit)
        console.print()
        if tree:
            console.print(events_module.tree_for(event, particles))
        else:
            console.print(events_module.table_for(event, particles))
        console.print(f"[dim]  {events_module.summary_of(event)}[/dim]")


def _events_source(target: str, count: int) -> Path:
    """Where to read events from: a store, a file, or a config that has to generate a few first."""
    from ..env import paths
    from ..store import index as index_module

    candidate = Path(target) if target else None
    if candidate is not None and candidate.is_file() and candidate.suffix == ".toml":
        return _generate_events(candidate, count)
    if candidate is not None and candidate.exists():
        if candidate.is_dir() and (candidate / "events").is_dir():
            return candidate / "events"
        return candidate

    stores = index_module.find_stores(paths.results_root())
    if target:
        named = [store for store in stores if store.parent.name == target]
        if named:
            return named[0]
        raise HepError(f"no events for '{target}'",
                       hint="give a store, a point, a config, or a HepMC3 file with --from; "
                            "`hep store ls` lists the stores")
    if not stores:
        raise HepError("there are no event stores to look at",
                       hint="run with [store].enabled = true, or pass a config to generate a few")
    return max(stores, key=lambda store: (store / index_module.NAME).stat().st_mtime)


def _generate_events(config_file: Path, count: int) -> Path:
    """Generate a handful of events into a scratch store, so a config can be inspected too.

    06 §5 describes this as `hep-run --list`; a temporary store is the same thing with a renderer
    that can show particles, and it reuses the pipeline instead of widening the status protocol.
    """
    import subprocess
    import tomli_w

    from ..config import load_config
    from ..env import paths
    from ..plan import build as builder
    from ..plan import spec as spec_module
    from ..sweep import select as select_points

    config = load_config(config_file)
    plan = builder.build(config, select_points(config), index=1, check_analyses=False)
    group = plan.groups[0]

    directory = paths.scratch_root() / "events" / group.name
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True, exist_ok=True)
    card_name = f"point.{'cmnd' if config.generator.tool == 'pythia' else 'card'}"
    if group.card:
        (directory / card_name).write_text(group.card, encoding="utf-8")

    document = dict(group.spec)
    document["run"] = {**document.get("run", {}), "events": count, "threads": 1,
                       "seeds": {"point": document.get("run", {}).get("seed", 1),
                                 "instances": [document.get("run", {}).get("seed", 1)]}}
    source = dict(document.get("source", {}))
    if source.get("cards"):
        cards = list(source["cards"])
        cards[-1] = str(directory / card_name)
        source["cards"] = cards
    document["source"] = source
    document["output"] = {**document.get("output", {}), "dir": str(directory)}
    document["sink"] = [{"kind": "store", "dir": str(directory / "events"), "compression": "none"}]
    spec_path = directory / "run.toml"
    spec_path.write_text(tomli_w.dumps(document), encoding="utf-8")

    from ..env.doctor import hep_run_path

    binary = hep_run_path()
    if not binary:
        raise HepError("hep-run is not built", hint="`hep build`")
    done = subprocess.run([binary, str(spec_path), "--plain"], capture_output=True, text=True,
                          timeout=1800, cwd=paths.scratch_root())
    if done.returncode != 0:
        message = next((line for line in done.stderr.splitlines() if line.startswith("hep-run:")),
                       f"exit {done.returncode}")
        raise HepError(f"could not generate events: {message.replace('hep-run: ', '')}")
    return directory / "events"
