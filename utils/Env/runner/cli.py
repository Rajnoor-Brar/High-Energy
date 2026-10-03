"""`hep run`, `hep plot` and `hep watch` (rank 5): argument parsing and the order of events.

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
import signal
import tomllib
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config as configmod
from . import execute, plot, post, record, sweep, tools
from .errors import HepError
from .paths import output_root
from .quantities import load_master
from .events import Bus, Hub, Journal, greeting, connect, hubs
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

    draw = commands.add_parser("plot", help="draw pages: a configuration's, or any YODA/ROOT files")
    draw.add_argument("targets", nargs="+", metavar="TARGET",
                      help="CONFIG [CONFIGURATION] (its pages, as after a run), or FILE… (YODA/ROOT files to overlay)")
    draw.add_argument("--set", metavar="KEY=VALUE", action="append", default=[], help="as for hep run (config mode)")
    draw.add_argument("-o", "--output", help="files: where the pages go (default results/plots/<first file>)")
    draw.add_argument("--labels", help="files: legend labels, comma-separated, one per file")
    draw.add_argument("--objects", nargs="+", default=[], metavar="GLOB", help="files: only these YODA paths")
    draw.add_argument("--formats", default="pdf,png", help="files: pdf, png, svg, eps (default pdf,png)")
    draw.add_argument("--ratio", action="store_true", help="files: a ratio panel against the first curve")
    draw.add_argument("--style", metavar="FILE", help="files: a style file over utils/Apps/Paint/base.toml")

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
    plot.check_texts(run, plans)                 # a placeholder typo costs no point run (V66) …
    plot.check_band(run, configuration)          # … nor a band's (V69)
    return Planned(run, configuration, plans, [p for p in plans if p.point.index in chosen],
                   post.plan(run, configuration, master, plans), pre_plan,
                   post.plan_combined(run, configuration, master, plans))


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
    try:
        return _runs(args, run, keys, stopper, bus)
    finally:
        if bus is not None:
            hub.close()


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
                  "parallelism": configuration.parallelism, "swept": configuration.swept,
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
            planned: Planned | None = None, bus: Bus | None = None) -> int:
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
        return 1 if plot.draw(run, configuration, combined or every, print) else 0
    if args.only == "post" and post_plan is None:
        raise HepError(f"configuration '{configuration.key}' has no post tools", where=f"{run.path}: [run.{configuration.key}].post")
    if args.only == "pre" and pre_plan is None:
        raise HepError(f"configuration '{configuration.key}' has no pre tools", where=f"{run.path}: [run.{configuration.key}].pre")
    if stopper.requested:                    # Ctrl-C while this run was being planned
        return 6

    bus = bus if bus is not None else Bus()
    shown = view(args.plain)
    bus.subscribe(shown)
    catch_signals(stopper)
    logs = bool(getattr(args, "logs", False))

    base = plans[0].out.parent if plans else None
    journal = Journal(base / "status.jsonl") if base and getattr(args, "journal", False) else None
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
                                                       rerun=args.rerun, logs=logs)
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
            failed += plot.draw(run, configuration, combined or every, bus.say) > 0   # the groups, when combined
        bus.say(verdict)                     # before end(): the view's thread prints it (V32)
    finally:
        onward = {"next": str(following)} if following and not stopper.requested else {}
        bus.emit("", "", {"k": "run", "state": "finished", "verdict": verdict, **onward})
        bus.unsubscribe(shown)
        shown.end()
        manifest()
        if journal:
            bus.unsubscribe(journal)
            journal.close()
    return 1 if failed else 0


def cmd_plot(args) -> int:
    """`hep plot CONFIG [CONFIGURATION]`: the configuration's pages from its complete points (what
    `hep run … --only plot` does). `hep plot FILE…`: any YODA/ROOT files overlaid through Paint."""
    if all(plot._is_plot_file(t) for t in args.targets):
        formats = [f.strip() for f in args.formats.split(",") if f.strip()]
        bad = [f for f in formats if f not in plot.FORMATS]
        if bad:
            raise HepError(f"format '{bad[0]}' is not one of {', '.join(plot.FORMATS)}")
        labels = [x.strip() for x in args.labels.split(",")] if args.labels else None
        return 1 if plot.files(args.targets, Path(args.output) if args.output else None, labels=labels,
                               objects=args.objects, formats=formats, ratio=args.ratio, style=args.style) else 0
    if len(args.targets) > 2:
        raise HepError("hep plot takes CONFIG [CONFIGURATION], or files ending .yoda/.yoda.gz/.root")
    args.config, args.configuration = args.targets[0], (args.targets[1] if len(args.targets) > 1 else None)
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
        failed = plot.draw(planned.run, planned.configuration, planned.combined or planned.every, print) or failed
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
        return cmd_watch(args)
    except HepError as error:
        print(error.render(), file=sys.stderr)
        return 2
