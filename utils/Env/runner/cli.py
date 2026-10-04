"""`hep run`, `hep plot`, `hep overlay`, `hep watch`, `hep check` and the housekeeping commands (`ls`,
`explain`, `status`, `clean`: house.py) (rank 5): argument parsing and the order of events.

docs/04_Config_Reference.md §14. `hep build` is handled by the shell dispatcher
(utils/Env/hep), which runs make.

Exit codes: 0 every point done (or skipped), 1 a point failed, 2 a config error before anything ran,
6 stopped by the user. Under [run].sweep_runs (V38), several runs one after another: 6 if one was
stopped, else 1 if any failed (or could not be planned at its turn), else 0.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import threading
import time
import tomllib
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config as configmod
from . import execute, house, plot, post, record, sweep, tools
from .errors import HepError
from .paths import output_root, results_root
from .quantities import load_master
from .events import Bus, Hub, Journal, RunBus, greeting, connect, hubs
from .watch import follow_events, follow_file, view


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="hep", description="the v2 runner")
    commands = top.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="plan and run a configuration")
    run.add_argument("config", help="configs/<Project>/<name>[.toml], or ./path from the repo root")
    run.add_argument("configuration", nargs="?", help="overrides [run].configuration; under [run].sweep_runs, runs only it")
    run.add_argument("--plan", action="store_true", help="print the plan; run nothing")
    run.add_argument("--why", action="store_true",
                     help="for each point that would run, what changed since it last completed; run nothing")
    run.add_argument("--show-config", action="store_true",
                     help="print each configuration's resolved values and where each came from; run nothing")
    run.add_argument("--points", metavar="SEL", help="run a subset: tags, indices or quantity=tag")
    run.add_argument("--set", metavar="KEY=VALUE", action="append", default=[],
                     help="override one value for this invocation (repeatable)")
    run.add_argument("--rerun", action="store_true", help="ignore skip-unchanged")
    run.add_argument("--only", choices=["pre", "post", "plot"], help="rerun only the pre tools, the post tools or the plots")
    run.add_argument("--plain", action="store_true", help="plain lines instead of the live view")
    run.add_argument("--journal", action="store_true",
                     help="also write every status event to output/…/status.jsonl (for hep watch --file and replay)")
    run.add_argument("--logs", action="store_true",
                     help="keep every tool's whole output in logs/<tag>.log (default: only a failed tool's last lines)")

    draw = commands.add_parser("plot", help="draw a configuration's pages from its complete points")
    draw.add_argument("config", help="the run config")
    draw.add_argument("configuration", nargs="?", help="overrides [run].configuration; under sweep_runs, only it")
    draw.add_argument("--set", metavar="KEY=VALUE", action="append", default=[], help="as for hep run")

    overlay = commands.add_parser("overlay", help="overlay any YODA/ROOT files through Paint, with no run TOML")
    overlay.add_argument("files", nargs="+", metavar="FILE", help="YODA (.yoda, .yoda.gz) or ROOT files")
    overlay.add_argument("-o", "--output", help="where the pages go (default results/plots/<first file>)")
    overlay.add_argument("--labels", help="legend labels, comma-separated, one per file")
    overlay.add_argument("--objects", nargs="+", default=[], metavar="GLOB", help="only these YODA paths")
    overlay.add_argument("--formats", default="pdf,png", help="pdf, png, svg, eps (default pdf,png)")
    overlay.add_argument("--ratio", action="store_true", help="a ratio panel against the first curve")
    overlay.add_argument("--style", metavar="FILE", help="a style file over utils/Apps/Paint/base.toml")

    listing = commands.add_parser("ls", help="every config and its configurations")
    listing.add_argument("project", nargs="?", help="only this project's configs")

    explain = commands.add_parser("explain", help="a run TOML key: its type, default and meaning (the schema's)")
    explain.add_argument("key", help="e.g. plot.y_gutter, run.event_count, quantities.<q>.styles")

    state = commands.add_parser("status", help="each configuration's points: complete, stale, incomplete or to run")
    state.add_argument("config", nargs="?", help="one config (default: every config)")
    state.add_argument("configuration", nargs="?", help="one configuration of it")
    state.add_argument("--stack", action="store_true", help="the software stack instead: each package's version (V78)")

    move = commands.add_parser("migrate", help="rewrite run TOMLs and their cards in today's forms (a diff, or --apply)")
    move.add_argument("configs", nargs="*", metavar="CONFIG", help="configs to migrate (default: every config)")
    move.add_argument("--apply", action="store_true", help="write the changes (default: print the diff)")

    again = commands.add_parser("reproduce", help="run a finished point again, from its provenance, beside it")
    again.add_argument("provenance", help="output/…/<point>/provenance.json")
    again.add_argument("--anyway", action="store_true", help="run it even though the setup changed since")
    again.add_argument("--plain", action="store_true", help="plain lines instead of the live view")

    clean = commands.add_parser("clean", help="remove what the runner made and no plan uses (output/ only)")
    clean.add_argument("config", nargs="?", help="one config (default: every config, and the unused caches)")
    clean.add_argument("--dry-run", action="store_true", help="list only")
    clean.add_argument("--yes", action="store_true", help="delete without asking")

    check = commands.add_parser("check", help="check run TOMLs: every configuration loaded, validated and planned")
    check.add_argument("configs", nargs="*", metavar="CONFIG",
                       help="configs to check (default: every configs/<Project>/*.toml with a [run])")

    watch = commands.add_parser("watch", help="attach the live view to a running job")
    watch.add_argument("config", nargs="?", help="the run config whose job to watch (default: the latest job)")
    watch.add_argument("configuration", nargs="?", help="overrides [run].configuration (or the sweep's latest)")
    watch.add_argument("--plain", action="store_true", help="plain lines instead of the live view")
    watch.add_argument("--file", metavar="STATUS.JSONL", help="follow a --journal run's status file instead")
    return top


@dataclass
class Planned:
    """One run, planned: what `hep run CONFIG CONFIGURATION` executes."""
    run: configmod.RunConfig
    configuration: configmod.Configuration
    every: list                                    # every point's plan
    plans: list                                    # the points to run (--points)
    post: object                                   # the post stage's plan, or None
    pre: object                                    # the pre stage's plan, or None
    combined: list                                 # the combined groups (V35)


def build_plans(args, key: str | None) -> Planned:
    run = configmod.load(args.config, sets=args.set)
    plot.validate(run)                       # before anything is planned (V54): a [plot] typo costs no planning
    configuration = run.configuration(key)
    master = load_master(run.project, run.master_toml)
    points = sweep.points(run, configuration)
    chosen = {p.index for p in sweep.select_points(run, configuration, points, args.points)}
    pre_plan = post.plan_pre(run, configuration, master, points)
    plans = []
    for point in points:
        plan = tools.plan_point(run, configuration, point, master, pre=pre_plan)
        plan.identity = record.identity(plan)
        plans.append(plan)
    again = getattr(args, "rerun", False) and getattr(args, "only", None) is None   # the points run anew
    record.assign_seeds(plans, frozenset(p.point.name for p in plans if again and p.point.index in chosen))
    for plan in plans:
        tools.finalise(plan, plan.seed)
        tools.check_cards(plan)                  # the tools read their cards (V59), cached by text
    if configuration.parallelism_auto:           # "auto" (V75): from the plans' cores
        configuration.parallelism = execute.auto_parallelism(plans)
    plot.check_texts(run, plans)                 # a placeholder typo costs no point run (V66) …
    plot.check_figures(run, configuration)       # … nor a band's (V69), nor what a figure merges (V82)
    return Planned(run, configuration, plans, [p for p in plans if p.point.index in chosen],
                   post.plan(run, configuration, master, plans), pre_plan,
                   post.plan_combined(run, configuration, master, plans))


def others_of(args):
    """Another configuration's plans, for a compare figure (V83): its points, or its combined groups."""
    def plans_of(key: str) -> list:
        planned = build_plans(argparse.Namespace(**{**vars(args), "points": None, "rerun": False}), key)
        return planned.combined or planned.every
    return plans_of


def journal_path(run, configuration) -> Path:
    """output/<P>/<run>/<cfg>/status.jsonl: a --journal run's events, which hep watch --file follows."""
    return output_root() / tools.run_dir(run, configuration) / "status.jsonl"


def header(number: int, configuration) -> str:
    """'run 02 - Beam energies -': a run's place in a sweep of runs, and its title (V38)."""
    return f"run {number:02d} - {configuration.title} -"


def _print_stage(title: str, stage, run) -> None:
    print(f"{title}   identity {stage.identity[:12]}")
    for line in tools.describe(stage, run)[1:]:
        print(line)
    print(f"  results {stage.res}   ({'complete' if record.is_complete(stage) else 'to run'})")


def parallel_note(configuration, plans) -> str:
    """', 4 at once (~52 of 24 cores)' for the title and --plan; nothing when one at a time (V36)."""
    if configuration.parallelism <= 1 or not plans:
        return ""
    each = max(execute.cores(p) for p in plans)
    return f", {configuration.parallelism} at once (~{configuration.parallelism * each} of {os.cpu_count()} cores)"


def crowded(configuration, plans) -> str:
    """A warning when the points at once want more cores than the machine has."""
    if configuration.parallelism <= 1 or not plans:
        return ""
    each = max(execute.cores(p) for p in plans)
    if configuration.parallelism * each <= (os.cpu_count() or 1):
        return ""
    return (f"parallelism {configuration.parallelism} × ~{each} cores a point is more than the {os.cpu_count()} "
            f"here: lower threads, shards or parallelism, or accept the oversubscription")


def print_plan(run, configuration, plans, post_plan=None, pre_plan=None, combined=()) -> None:
    print(f"run {run.name} ({run.path}) · configuration {configuration.key}: {len(plans)} point(s), "
          f"{configuration.event_count} events, {configuration.threads} threads" + parallel_note(configuration, plans))
    if crowded(configuration, plans):
        print(f"note: {crowded(configuration, plans)}")
    for note in notes_of(plans):
        print(f"note: {note}")
    if configuration.seed_type != "identity":
        print(f"seeds: {configuration.seed_type}")
    if configuration.manual_seed is not None and configuration.seed_type != "manual":
        print(f"note: manual_seed = {configuration.manual_seed} is unused: seed_type is '{configuration.seed_type}'")
    if pre_plan is not None:
        _print_stage("pre (before every point)", pre_plan, run)
    for plan in plans:
        state = "complete" if record.is_complete(plan) else "to run"
        for line in tools.describe(plan, run):
            print(line)
        print(f"  output  {plan.out}\n  results {plan.res}   ({state})")
    for group in combined:
        _print_stage(f"combined {group.point.name} (merges {len(group.upstream)} points: "
                     f"{', '.join(configuration.combine)})", group, run)
    if post_plan is not None:
        _print_stage("post (after every point)", post_plan, run)
    if run.plot and plans:
        count = len(sweep.pages(configuration, [p.point for p in plans]))
        print(f"plot ({', '.join(plot.backends(run.plot))}): {count} page(s) per object, "
              f"{', '.join(plot.formats_of(run.plot))} → {plans[0].res.parent / 'plots'}")


def print_why(run, configuration, plans, post_plan=None, pre_plan=None, combined=()) -> None:
    """--why (V57): each point and stage that would run, and what changed since it last completed."""
    stages = [*([pre_plan] if pre_plan else []), *plans, *combined, *([post_plan] if post_plan else [])]
    todo = [p for p in stages if not record.is_complete(p)]
    print(f"run {run.name} · configuration {configuration.key}: {len(todo)} of {len(stages)} to run")
    for plan in todo:
        print(f"{plan.point.name}   identity {plan.identity[:12]}")
        for line in record.why(plan):
            print(f"  {line}")


def notes_of(plans) -> list[str]:
    """What the plans say once (V59): a base card's line the runner overrides, …; each note once."""
    return list(dict.fromkeys(note for plan in plans for note in plan.notes))


def catch_signals(stopper: execute.Stopper) -> None:
    """Ctrl-C (SIGINT) and SIGTERM ask the run to stop; a second one is the default behaviour."""
    def on_signal(signum, frame):
        if stopper.requested:
            signal.signal(signum, signal.SIG_DFL)
        stopper.requested = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)


def cmd_run(args) -> int:
    """One run; or, under [run].sweep_runs, every swept configuration as a run of its own, one after
    another (V38). Each is exactly `hep run CONFIG <cfg>`, after a `run NN - <title> -` line. All are
    planned before the first starts, so a config error anywhere exits 2 with nothing run; one is
    planned again at its turn only if the TOML was edited meanwhile, so edits still count. A failed run leaves the next to
    start; a stop starts no more."""
    run = configmod.load(args.config, sets=args.set)
    keys = run.runs(args.configuration)
    if getattr(args, "show_config", False):
        for line in show_config(run, keys):
            print(line)
        return 0
    stopper = execute.Stopper()
    if getattr(args, "why", False) or args.plan or args.only == "plot":
        bus = None                           # nothing runs: nothing to watch
    else:                                    # one stream for the whole process, served while it lives (V72)
        bus = Bus()
        hub = Hub({"config": str(run.path), "run": run.name, "configurations": keys})
        bus.subscribe(hub)
    code = 2
    try:
        code = _runs(args, run, keys, stopper, bus)
        return code
    finally:
        if bus is not None:
            hub.close()
            notify(run, code)


def notify(run, code: int) -> bool:
    """[run] notify = "desktop" (V76): a notify-send when the command ends, for runs of hours. Never
    fails the run: no notify-send, or no desktop, and it says nothing."""
    if run.raw.get("run", {}).get("notify", "none") != "desktop" or not shutil.which("notify-send"):
        return False
    verdict = {0: "done", 1: "a point failed", 2: "a config error", 6: "stopped"}.get(code, f"exit {code}")
    try:
        subprocess.Popen(["notify-send", "--app-name=hep", f"hep run {run.name}", f"{run.path.name}: {verdict}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    return True


def _runs(args, run, keys: list[str], stopper: execute.Stopper, bus) -> int:
    if len(keys) == 1:
        return run_one(args, keys[0], stopper, bus=bus)
    if args.points:
        raise HepError("--points picks points of one configuration, and this sweep runs several",
                       where=f"{run.path}: [run].sweep_runs", hint=f"name it: hep run {args.config} <configuration> --points …")
    skipped, ahead = {}, {}
    stamp = run.path.stat().st_mtime_ns
    for key in keys:
        try:
            ahead[key] = planned = build_plans(args, key)
        except HepError as error:
            error.message = f"configuration '{key}': {error.message}"
            raise
        if args.only in ("pre", "post") and getattr(planned, args.only) is None:
            skipped[key] = f"   no {args.only} tools: skipped"
    if len(skipped) == len(keys):
        raise HepError(f"no configuration of this sweep has {args.only} tools", where=f"{run.path}: [run].sweep_runs")
    if bus is not None and args.only is None:
        return _pipelined(args, run, keys, stopper, bus, ahead, stamp)
    failed = False
    for number, key in enumerate(keys, 1):
        if stopper.requested:
            return 6
        following = next((journal_path(run, run.configurations[k]) for k in keys[number:] if k not in skipped), None) \
            if args.journal else None
        if key in skipped:
            print(("\n" if number > 1 else "") + header(number, run.configurations[key]))
            print(skipped[key])
            continue
        try:                                 # planned again only if the TOML was edited meanwhile (V38, V54)
            unchanged = run.path.stat().st_mtime_ns == stamp
            code = run_one(args, key, stopper, number=number, following=following,
                           planned=ahead[key] if unchanged else None, bus=bus)
        except HepError as error:            # the TOML was edited since the check: this run fails alone
            print(("\n" if number > 1 else "") + header(number, run.configurations[key]))
            print(error.render(), file=sys.stderr)
            not_run(journal_path(run, run.configurations[key]) if args.journal else None,
                    header(number, run.configurations[key]), error.message, following, bus)
            code = 2
        if code == 6:
            return 6
        failed = failed or code != 0
    return 1 if failed else 0


def _pipelined(args, run, keys: list[str], stopper: execute.Stopper, bus: Bus, ahead: dict, stamp: int) -> int:
    """A sweep of runs, pipelined (V75, the user's B8 decision): each run starts once the one before has
    started all its points, and its points take the free cores of a budget the runs share (never more
    than the largest run alone would use), so a run's last points and the next run's first overlap. Each
    run's own order (pre, points, combined, post, plots) is kept. One view for the sweep; each run's
    events carry its key. A stop starts no more runs; a failed run leaves the next to start."""
    each = {key: max((execute.cores(p) for p in ahead[key].plans), default=1) for key in keys}
    budget = execute.Budget(max(os.cpu_count() or 1,
                                *(max(1, ahead[key].configuration.parallelism) * each[key] for key in keys)))
    shown = view(args.plain)
    bus.subscribe(shown)
    catch_signals(stopper)
    codes: dict[str, int] = {}
    errors: list[BaseException] = []
    threads: list[threading.Thread] = []
    gate: threading.Event | None = None
    try:
        for number, key in enumerate(keys, 1):
            while gate is not None and not gate.wait(0.25) and not stopper.requested:
                pass
            if stopper.requested:
                break
            following = next((journal_path(run, run.configurations[k]) for k in keys[number:]), None) \
                if args.journal else None
            gate = threading.Event()

            def job(key=key, number=number, following=following, gate=gate) -> None:
                voice = RunBus(bus, key)
                try:                         # planned again only if the TOML was edited meanwhile (V38, V54)
                    unchanged = run.path.stat().st_mtime_ns == stamp
                    codes[key] = run_one(args, key, stopper, number=number, following=following,
                                         planned=ahead[key] if unchanged else None, bus=voice, shown=shown,
                                         budget=budget, gate=gate)
                except HepError as error:    # the TOML was edited since the check: this run fails alone
                    voice.say(header(number, run.configurations[key]))
                    voice.say(error.render())
                    not_run(journal_path(run, run.configurations[key]) if args.journal else None,
                            header(number, run.configurations[key]), error.message, following, voice)
                    codes[key] = 2
                except BaseException as error:           # the runner's own error: raised once all have ended
                    errors.append(error)
                    codes[key] = 1
                finally:
                    gate.set()

            thread = threading.Thread(target=job, name=f"hep-run-{key}")
            thread.start()
            threads.append(thread)
        while any(t.is_alive() for t in threads):        # the main thread takes the signals
            time.sleep(0.25)
    finally:
        for thread in threads:
            thread.join()
        bus.unsubscribe(shown)
        shown.end()
    if errors:
        raise errors[0]
    if stopper.requested or 6 in codes.values():
        return 6
    return 1 if any(codes.values()) else 0


def show_config(run, keys: list[str]) -> list[str]:
    """--show-config (V56): every resolved value of each configuration with the layer it came from: its
    own table, one it extends, [run.defaults], [run], or the schema's default; and what [master].include
    gave the file."""
    from . import schema
    order = [k for k in schema.keys("configuration") if k not in ("extends",)]
    lines = []
    for key in keys:
        configuration = run.configurations[key]
        lines.append(f"run {run.name} ({run.path}) · configuration {key}")
        fields = {"serial": configuration.serial, "name": configuration.run_folder, "label": configuration.label,
                  "title": configuration.title, "description": configuration.description,
                  "event_count": configuration.event_count, "threads": configuration.threads,
                  "parallelism": "auto" if configuration.parallelism_auto else configuration.parallelism,
                  "swept": configuration.swept,
                  "seed_type": configuration.seed_type, "manual_seed": configuration.manual_seed,
                  "sweeps": configuration.sweeps, "plot_points": configuration.plot_points,
                  "combine": configuration.combine, "tools": configuration.tools, "pre": configuration.pre,
                  "post": configuration.post, "static": configuration.static, "prelim": configuration.prelim}
        width = max(map(len, order))
        for name in order:
            value = fields.get(name)
            if value in (None, [], {}, "") and name not in configuration.origins:
                continue
            own = run.raw.get("run", {}).get(key, {})
            origin = configuration.origins.get(name, f"[run.{key}]" if name in own else "default")
            lines.append(f"  {name:{width}s} = {json.dumps(value, default=str):40s} {origin}")
    for entry, source in sorted(run.included.items()):
        lines.append(f"  included {entry} from {source}")
    return lines


def not_run(path: Path | None, title: str, message: str, following: Path | None, bus=None) -> None:
    """A run that could not be planned at its turn still says so: to the watchers, and in its journal
    (--journal), so hep watch --file moves on."""
    journal = Journal(path) if path is not None else None
    for event in ({"k": "run", "state": "started", "points": 0, "title": title, "header": title},
                  {"k": "run", "state": "finished", "verdict": f"not run: {message}",
                   **({"next": str(following)} if following else {})}):
        if bus is not None:
            bus.emit("", "", event)
        if journal is not None:
            journal.event({"v": 1, "point": "", "tool": "", **event})
    if journal is not None:
        journal.close()


def run_one(args, key: str, stopper: execute.Stopper, *, number: int = 0, following: Path | None = None,
            planned: Planned | None = None, bus: Bus | None = None, shown=None, budget=None,
            gate: threading.Event | None = None) -> int:
    """One run: the pre stage, every point not complete, the combined groups, the post stage and the
    plots, said on `bus` (V72). In a sweep of runs, `number` is its place (a `run NN - <title> -` line
    first), and `following` is the next run's journal (--journal), named in this one's `run finished`
    event so that hep watch --file follows on."""
    planned = planned or build_plans(args, key)
    run, configuration, every, plans = planned.run, planned.configuration, planned.every, planned.plans
    post_plan, pre_plan, combined = planned.post, planned.pre, planned.combined
    title_line = header(number, configuration) if number else ""
    if getattr(args, "why", False):
        if title_line:
            print(("\n" if number > 1 else "") + title_line)
        print_why(run, configuration, plans, post_plan, pre_plan, combined)
        return 0
    if args.plan or args.only == "plot":
        if title_line:
            print(("\n" if number > 1 else "") + title_line)
        if args.plan:
            print_plan(run, configuration, plans, post_plan, pre_plan, combined)
            return 0
        return 1 if plot.draw(run, configuration, combined or every, print, others=others_of(args)) else 0
    if args.only == "post" and post_plan is None:
        raise HepError(f"configuration '{configuration.key}' has no post tools", where=f"{run.path}: [run.{configuration.key}].post")
    if args.only == "pre" and pre_plan is None:
        raise HepError(f"configuration '{configuration.key}' has no pre tools", where=f"{run.path}: [run.{configuration.key}].pre")
    if stopper.requested:                    # Ctrl-C while this run was being planned
        return 6

    bus = bus if bus is not None else Bus()
    own_view = shown is None                 # a pipelined sweep's runs share the sweep's view (V75)
    if own_view:
        shown = view(args.plain)
        bus.subscribe(shown)
    if threading.current_thread() is threading.main_thread():
        catch_signals(stopper)
    logs = bool(getattr(args, "logs", False))

    base = plans[0].out.parent if plans else None
    journal = Journal(base / "status.jsonl", run=getattr(bus, "run", None)) \
        if base and getattr(args, "journal", False) else None
    if journal:
        bus.subscribe(journal)
    title = (f"{run.name} · {configuration.key}: {len(plans)} point(s), {configuration.event_count} events, "
             f"{configuration.threads} threads" + parallel_note(configuration, plans))
    if number > 1:
        bus.say("")
    bus.emit("", "", {"k": "run", "state": "started", "points": len(plans), "title": title,
                      **({"header": title_line} if title_line else {})})
    if crowded(configuration, plans):
        bus.say(f"   note: {crowded(configuration, plans)}")
    for note in notes_of(plans):
        bus.say(f"   note: {note}")
    def manifest() -> None:
        if base:
            record.write_atomic(base / "points.json",
                                json.dumps(record.points_manifest(every, run, configuration), indent=1, default=str) + "\n")
    manifest()
    failed = done = 0
    verdict = "stopped"
    try:
        if args.only in (None, "pre"):
            if not post.run_pre(pre_plan, run, configuration, bus=bus, stopper=stopper, logs=logs,
                                rerun=args.rerun or args.only == "pre"):
                verdict = "pre failed: no point ran"
                return 6 if stopper.requested else 1
            if args.only == "pre":
                verdict = "pre done"
                return 0
        if args.only != "post":
            done, failed, stopped = execute.run_points(plans, run, configuration, bus=bus, stopper=stopper,
                                                       rerun=args.rerun, logs=logs, budget=budget,
                                                       started_all=gate.set if gate is not None else None)
            if stopped:
                return 6
        verdict = f"{done} done, {failed} failed, {len(plans) - done - failed} skipped" if args.only != "post" else ""
        manifest()                           # post tools read it: it must say which points are complete
        if combined and args.only != "post":
            bad = post.run_combined(combined, every, run, configuration, bus=bus, stopper=stopper, logs=logs,
                                    rerun=args.rerun, say=bus.say)
            if stopper.requested:
                return 6
            if bad:
                failed += bad
                verdict = f"{verdict}, {bad} combined group(s) failed"
        if not post.run(post_plan, every, run, configuration, bus=bus, stopper=stopper, logs=logs,
                        rerun=args.rerun or args.only == "post", say=bus.say):
            if stopper.requested:
                return 6
            failed += 1
            verdict = ", ".join(v for v in (verdict, "post failed") if v)
        elif post_plan is not None and args.only == "post":
            verdict = "post done"
        if args.only != "post":
            failed += plot.draw(run, configuration, combined or every, bus.say, others=others_of(args)) > 0   # the groups, when combined
        bus.say(verdict)                     # before end(): the view's thread prints it (V32)
    finally:
        onward = {"next": str(following)} if following and not stopper.requested else {}
        bus.emit("", "", {"k": "run", "state": "finished", "verdict": verdict, **onward})
        if own_view:
            bus.unsubscribe(shown)
            shown.end()
        manifest()
        if journal:
            bus.unsubscribe(journal)
            journal.close()
    return 1 if failed else 0


def cmd_overlay(args) -> int:
    """`hep overlay FILE…` (V74, was `hep plot FILE…`): any YODA/ROOT files overlaid through Paint."""
    bad = [f for f in args.files if not plot._is_plot_file(f)]
    if bad:
        raise HepError(f"{bad[0]} is not a YODA or ROOT file", hint="hep overlay takes files ending .yoda, .yoda.gz "
                                                                   "or .root; a configuration's pages: hep plot CONFIG")
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    wrong = [f for f in formats if f not in plot.FORMATS]
    if wrong:
        raise HepError(f"format '{wrong[0]}' is not one of {', '.join(plot.FORMATS)}")
    labels = [x.strip() for x in args.labels.split(",")] if args.labels else None
    return 1 if plot.files(args.files, Path(args.output) if args.output else None, labels=labels,
                           objects=args.objects, formats=formats, ratio=args.ratio, style=args.style) else 0


def cmd_plot(args) -> int:
    """`hep plot CONFIG [CONFIGURATION]`: the configuration's pages from its complete points (what
    `hep run … --only plot` does)."""
    if plot._is_plot_file(args.config):                     # break and migrate (V74)
        raise HepError("hep plot draws a configuration's pages; files are overlaid by hep overlay",
                       hint=f"hep overlay {args.config} …")
    args.points = None
    run = configmod.load(args.config, sets=args.set)
    if not run.plot:
        raise HepError(f"{run.path} has no [plot] table", hint="add [plot], or give the files: hep plot FILE…")
    keys = run.runs(args.configuration)
    failed = False
    for number, key in enumerate(keys, 1):   # under [run].sweep_runs, every swept configuration's pages (V38)
        planned = build_plans(args, key)
        if len(keys) > 1:
            print(("\n" if number > 1 else "") + header(number, planned.configuration))
        failed = plot.draw(planned.run, planned.configuration, planned.combined or planned.every, print,
                           others=others_of(args)) or failed
    return 1 if failed else 0


def cmd_check(args) -> int:
    """`hep check [CONFIG…]` (V57): each config loaded, its [plot] validated and every configuration's
    points planned (the C-rules, paths, consumers, connections, cards), nothing run or written. 0 when
    all are well, 2 when any is not: for a pre-commit hook, or before a long sweep."""
    from .paths import configs_root
    names = list(args.configs)
    if not names:
        root = configs_root()
        for path in sorted(root.glob("*/*.toml")):
            try:
                has_run = "run" in tomllib.loads(path.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError):
                has_run = True                                   # a broken file is checked, and fails
            if has_run:
                names.append(str(path.relative_to(root).with_suffix("")))
    failed = 0
    for name in names:
        try:
            run = configmod.load(name)
            points = 0
            for key in run.configurations:
                planned = build_plans(argparse.Namespace(config=name, set=[], points=None, rerun=False, only=None), key)
                points += len(planned.every)
            print(f"ok    {name}: {len(run.configurations)} configuration(s), {points} point(s)")
        except HepError as error:
            failed += 1
            print(f"FAIL  {name}")
            print("      " + error.render().replace("\n", "\n      "))
    return 2 if failed else 0


def cmd_watch(args) -> int:
    """Follow a job from another terminal (V72): a running `hep run`'s watch socket (the latest one, or
    the one running CONFIG [CONFIGURATION]), or with --file a --journal run's status.jsonl."""
    if args.file:
        path = Path(args.file)
        if not path.exists():
            raise HepError("no such status file", where=str(path), hint="a run writes one with hep run … --journal")
        return follow_file(path, plain=args.plain)
    wanted = configmod.load(args.config) if args.config else None
    found = []
    for name in hubs():
        hello = greeting(name)
        if not hello:
            continue
        if wanted is not None and hello.get("config") != str(wanted.path):
            continue
        if args.configuration and args.configuration not in hello.get("configurations", []):
            continue
        found.append((hello.get("started", 0), name))
    if not found:
        raise HepError("no running job to watch" + (f" for {wanted.path}" if wanted else ""),
                       hint="start one with hep run; a finished run's events: hep run … --journal, then hep watch --file "
                            "output/<P>/<run>/<cfg>/status.jsonl")
    return follow_events(connect(max(found)[1]), plain=args.plain)


def _planned_all(names: list[str], configuration: str | None = None) -> tuple[list, list[str]]:
    """Every configuration of these configs, planned as for a run: the plans, and what did not plan."""
    planned, failed = [], []
    for name in names:
        try:
            run = configmod.load(name)
            for key in ([configuration] if configuration else list(run.configurations)):
                planned.append(build_plans(argparse.Namespace(config=name, set=[], points=None, rerun=False, only=None), key))
        except HepError as error:
            failed.append(f"{name}: {error.message}")
    return planned, failed


def cmd_status(args) -> int:
    """`hep status [CONFIG [CONFIGURATION]]` (V74): each configuration's points and stages. `--stack`
    (V78): each package of utils/Env/stack.toml, its version and where it is."""
    if getattr(args, "stack", False):
        from .plugins import load
        from .paths import repo_root
        for line in load(repo_root() / "utils" / "Env" / "stack.py", "stack").versions():
            print(line)
        return 0
    names = [args.config] if args.config else house.config_names()
    planned, failed = _planned_all(names, args.configuration)
    for line in house.status(planned, house.running_configs()):
        print(line)
    for line in failed:
        print(f"not planned: {line}")
    return 2 if failed else 0


def cmd_clean(args) -> int:
    """`hep clean [CONFIG] [--dry-run] [--yes]` (V74): the output folders no plan uses, `.partial`
    leftovers and (with no config) unused run folders and prepare caches. It lists them first, and asks
    on a terminal (or needs --yes); results/ is never cleaned but for `.partial` leftovers."""
    if hubs():
        raise HepError("a job is running on this machine", hint="clean when it has ended (hep watch shows it)")
    names = [args.config] if args.config else house.config_names()
    planned, failed = _planned_all(names)
    if failed and not args.config:
        for line in failed:
            print(f"not planned: {line}")
        raise HepError("every config must plan before a whole clean: one that does not might own what would go",
                       hint="fix it, or clean one config: hep clean CONFIG")
    if failed:
        raise HepError(failed[0])
    targets, kept = house.clean_targets(planned, everything=not args.config)
    for path in targets:
        print(f"remove  {path}")
    for path in kept:
        print(f"kept    {path}   (results are yours: remove by hand if you mean to)")
    if not targets:
        print("nothing to clean")
        return 0
    if args.dry_run:
        print(f"{len(targets)} to remove (dry run)")
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            raise HepError(f"{len(targets)} to remove: not deleted", hint="--yes to delete, --dry-run to only list")
        if input(f"remove these {len(targets)}? [y/N] ").strip().lower() not in ("y", "yes"):
            print("nothing removed")
            return 0
    freed = house.remove(targets)
    print(f"removed {len(targets)}, {freed / 1e6:.1f} MB freed")
    return 0


def cmd_migrate(args) -> int:
    """`hep migrate [CONFIG…] [--apply]` (V79): the diff of each file today's forms change, or (--apply)
    the files rewritten. Configs are read as they are (the forms the runner now refuses included)."""
    from . import migrate
    names = list(args.configs) or house.config_names()
    changes = migrate.plan(names)            # every one must read, leniently, before anything is written
    for path, (old, new) in changes.items():
        sys.stdout.write(migrate.diff(path, old, new))
    if not changes:
        print("nothing to migrate")
        return 0
    if args.apply:
        migrate.apply(changes)
        print(f"migrated {len(changes)} file(s)")
        for name in names:                   # and now they read strictly
            configmod.load(name)
        return 0
    print(f"{len(changes)} file(s) to migrate (a dry run: --apply writes them)")
    return 0


def cmd_reproduce(args) -> int:
    """`hep reproduce output/…/<point>/provenance.json` (V77, F10): the point again, exactly as it ran,
    into output/<P>/.reproduce/<identity>/ (its own output/ and results/), never over the original; then
    each product compared with the original's. The setup must still be the one that ran (the identity
    the provenance records), else it says what changed (--why) and stops, unless --anyway. A random
    seed is the recorded one; any other seed follows from the identity, as it did."""
    import hashlib
    path = Path(args.provenance)
    if path.is_dir():
        path = path / "provenance.json"
    try:
        record_ = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HepError(f"cannot read {path}: {error}", hint="give a finished point's provenance.json")
    config_file, key, name = record_["config_file"], record_["configuration"], record_["point"]
    given = list(record_.get("sets", []))                     # the --set overrides it ran with
    planned = build_plans(argparse.Namespace(config=config_file, set=given, points=None, rerun=False, only=None), key)
    plan = next((p for p in planned.every if p.point.name == name), None)
    if plan is None:
        raise HepError(f"configuration '{key}' has no point '{name}' any more", where=config_file)
    if plan.identity != record_["identity"]:
        print(f"the setup of {name} changed since it ran ({record_['identity'][:12]} → {plan.identity[:12]}):")
        for line in record.why(plan):
            print(f"  {line}")
        if not args.anyway:
            raise HepError("not reproduced: this would be a different point", hint="--anyway runs today's setup with its seed")
    where = output_root() / record_["project"] / ".reproduce" / record_["identity"][:12]
    sets = []
    if planned.configuration.seed_type == "random":
        sets = ["--set", f'run.{key}.seed_type="manual"', "--set", f"run.{key}.manual_seed={record_['seed']}"]
    argv = [sys.executable, str(Path(__file__).resolve().parents[1] / "run"), "run", config_file, key,
            "--points", name, "--rerun", *[x for item in given for x in ("--set", item)], *sets,
            *(["--plain"] if args.plain else [])]
    env = dict(os.environ, HEKIT_OUTPUT=str(where / "output"), HEKIT_RESULTS=str(where / "results"))
    print(f"reproducing {record_['run']} · {key} · {name} (seed {record_['seed']}) in {where}", flush=True)
    code = subprocess.run(argv, env=env).returncode
    if code != 0:
        return code
    original, again_ = plan.res, where / "results" / plan.res.relative_to(results_root())

    same = True
    for made in sorted(f for f in again_.rglob("*") if f.is_file() and not f.name.endswith(".json")):
        rel = made.relative_to(again_)
        before = original / rel
        verdict = same_contents(before, made) if before.is_file() else "missing in the original"
        same = same and verdict in ("identical", "the same values")
        print(f"  {rel}: {verdict}")
    return 0 if same else 1


def same_contents(a: Path, b: Path) -> str:
    """Two products compared by what they hold (V77): a YODA file object by object (values and errors),
    a ROOT file histogram by histogram (uproot), anything else byte for byte. Bytes alone differ for
    the same physics: a sharded Rivet's merge order and ROOT's write times are in the files."""
    import hashlib
    if hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest():
        return "identical"
    try:
        if a.name.endswith((".yoda", ".yoda.gz")):
            import yoda

            def table(path):
                out = {}
                for key, obj in yoda.read(str(path)).items():
                    vals = [obj.vals()] if hasattr(obj, "vals") else []
                    errs = [obj.errs()] if hasattr(obj, "errs") else []
                    out[key] = (obj.type(), repr(vals), repr(errs))
                return out
            return "the same values" if table(a) == table(b) else "differs"
        if a.suffix == ".root":
            import numpy as np
            import uproot

            def histograms(path):
                with uproot.open(path) as file:
                    return {k: np.asarray(file[k].values()).tolist() for k in file.keys(cycle=False)
                            if hasattr(file[k], "values") and callable(getattr(file[k], "values"))}
            return "the same values" if histograms(a) == histograms(b) else "differs"
    except ImportError:
        return "differs in bytes (not read: no yoda/uproot)"
    return "differs"


def parse(argv: list[str]) -> argparse.Namespace:
    """The command line, with options and positionals in any order (`hep run eic --plain pdf`, V54):
    argparse's intermixed parsing does not take subcommands, so the subcommand's own parser reads the rest."""
    top = parser()
    commands = next(a for a in top._actions if isinstance(a, argparse._SubParsersAction))
    if argv and argv[0] in commands.choices:
        args = commands.choices[argv[0]].parse_intermixed_args(argv[1:])
        args.command = argv[0]
        return args
    return top.parse_args(argv)                  # --help, or an unknown command: argparse's own message


def main(argv: list[str]) -> int:
    args = parse(argv)
    try:
        if args.command == "run":
            return cmd_run(args)
        if args.command == "plot":
            return cmd_plot(args)
        if args.command == "check":
            return cmd_check(args)
        if args.command == "overlay":
            return cmd_overlay(args)
        if args.command == "ls":
            for line in house.ls(args.project):
                print(line)
            return 0
        if args.command == "explain":
            for line in house.explain(args.key):
                print(line)
            return 0
        if args.command == "status":
            return cmd_status(args)
        if args.command == "clean":
            return cmd_clean(args)
        if args.command == "reproduce":
            return cmd_reproduce(args)
        if args.command == "migrate":
            return cmd_migrate(args)
        return cmd_watch(args)
    except HepError as error:
        print(error.render(), file=sys.stderr)
        return 2
