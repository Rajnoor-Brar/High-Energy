"""`hep run`, `hep plot` and `hep watch` (rank 5): argument parsing and the order of events.

docs/04_Config_Reference.md §14. `hep build` is handled by the shell dispatcher
(utils/Env/hep), which runs make.

Exit codes: 0 every point done (or skipped), 1 a point failed, 2 a config error before anything ran,
6 stopped by the user. Under [run].sweep (V38), several runs one after another: 6 if one was
stopped, else 1 if any failed (or could not be planned at its turn), else 0.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config as configmod
from . import execute, plot, post, record, sweep, tools
from .errors import HepError
from .paths import output_root
from .quantities import load_master
from .status import Journal
from .watch import follow, view


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="hep", description="the v2 runner")
    commands = top.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="plan and run a configuration")
    run.add_argument("config", help="configs/<Project>/<name>[.toml], or ./path from the repo root")
    run.add_argument("configuration", nargs="?", help="overrides [run].configuration; under [run].sweep, runs only it")
    run.add_argument("--plan", action="store_true", help="print the plan; run nothing")
    run.add_argument("--points", metavar="SEL", help="run a subset: tags, indices or quantity=tag")
    run.add_argument("--set", metavar="KEY=VALUE", action="append", default=[],
                     help="override one value for this invocation (repeatable)")
    run.add_argument("--rerun", action="store_true", help="ignore skip-unchanged")
    run.add_argument("--only", choices=["pre", "post", "plot"], help="rerun only the pre tools, the post tools or the plots")
    run.add_argument("--plain", action="store_true", help="plain lines instead of the live view")

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

    watch = commands.add_parser("watch", help="attach the live view to a running job")
    watch.add_argument("config", nargs="?", help="the run config whose job to watch (default: the latest job)")
    watch.add_argument("configuration", nargs="?", help="overrides [run].configuration (or the sweep's latest)")
    watch.add_argument("--plain", action="store_true", help="plain lines instead of the live view")
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
    plot.validate(run)
    return Planned(run, configuration, plans, [p for p in plans if p.point.index in chosen],
                   post.plan(run, configuration, master, plans), pre_plan,
                   post.plan_combined(run, configuration, master, plans))


def journal_path(run, configuration) -> Path:
    """output/<P>/<run>/<cfg>/status.jsonl: a run's journal, which hep watch follows."""
    return (output_root() / run.project / tools.location(run.serial, run.name)
            / tools.location(configuration.serial, configuration.name) / "status.jsonl")


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


def catch_signals(stopper: execute.Stopper) -> None:
    """Ctrl-C (SIGINT) and SIGTERM ask the run to stop; a second one is the default behaviour."""
    def on_signal(signum, frame):
        if stopper.requested:
            signal.signal(signum, signal.SIG_DFL)
        stopper.requested = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)


def cmd_run(args) -> int:
    """One run; or, under [run].sweep, every swept configuration as a run of its own, one after
    another (V38). Each is exactly `hep run CONFIG <cfg>`, after a `run NN - <title> -` line. All are
    planned before the first starts, so a config error anywhere exits 2 with nothing run; each is
    planned again at its turn, so edits made meanwhile count. A failed run leaves the next to
    start; a stop starts no more."""
    run = configmod.load(args.config, sets=args.set)
    keys = run.runs(args.configuration)
    stopper = execute.Stopper()
    if len(keys) == 1:
        return run_one(args, keys[0], stopper)
    if args.points:
        raise HepError("--points picks points of one configuration, and this sweep runs several",
                       where=f"{run.path}: [run].sweep", hint=f"name it: hep run {args.config} <configuration> --points …")
    skipped = {}
    for key in keys:
        try:
            planned = build_plans(args, key)
        except HepError as error:
            error.message = f"configuration '{key}': {error.message}"
            raise
        if args.only in ("pre", "post") and getattr(planned, args.only) is None:
            skipped[key] = f"   no {args.only} tools: skipped"
    if len(skipped) == len(keys):
        raise HepError(f"no configuration of this sweep has {args.only} tools", where=f"{run.path}: [run].sweep")
    failed = False
    for number, key in enumerate(keys, 1):
        if stopper.requested:
            return 6
        following = next((journal_path(run, run.configurations[k]) for k in keys[number:] if k not in skipped), None)
        if key in skipped:
            print(("\n" if number > 1 else "") + header(number, run.configurations[key]))
            print(skipped[key])
            continue
        try:
            code = run_one(args, key, stopper, number=number, following=following)
        except HepError as error:            # the TOML was edited since the check: this run fails alone
            print(("\n" if number > 1 else "") + header(number, run.configurations[key]))
            print(error.render(), file=sys.stderr)
            not_run(journal_path(run, run.configurations[key]), header(number, run.configurations[key]),
                    error.message, following)
            code = 2
        if code == 6:
            return 6
        failed = failed or code != 0
    return 1 if failed else 0


def not_run(path: Path, title: str, message: str, following: Path | None) -> None:
    """A run that could not be planned at its turn still says so in its journal, so hep watch moves on."""
    journal = Journal(path)
    journal.write("", "", {"k": "run", "state": "started", "points": 0, "title": title, "header": title})
    journal.write("", "", {"k": "run", "state": "finished", "verdict": f"not run: {message}",
                           **({"next": str(following)} if following else {})})
    journal.close()


def run_one(args, key: str, stopper: execute.Stopper, *, number: int = 0, following: Path | None = None) -> int:
    """One run: the pre stage, every point not complete, the combined groups, the post stage and the
    plots. In a sweep of runs, `number` is its place (a `run NN - <title> -` line first), and
    `following` is the next run's journal, named in this one's `run finished` record so that hep
    watch follows on."""
    planned = build_plans(args, key)
    run, configuration, every, plans = planned.run, planned.configuration, planned.every, planned.plans
    post_plan, pre_plan, combined = planned.post, planned.pre, planned.combined
    title_line = header(number, configuration) if number else ""
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

    shown = view(args.plain)
    catch_signals(stopper)

    base = plans[0].out.parent if plans else None
    journal = Journal(base / "status.jsonl") if base else None
    title = (f"{run.name} · {configuration.key}: {len(plans)} point(s), {configuration.event_count} events, "
             f"{configuration.threads} threads" + parallel_note(configuration, plans))
    if number > 1:
        shown.say("")
    shown.begin(len(plans), title, header=title_line)
    if crowded(configuration, plans):
        shown.say(f"   note: {crowded(configuration, plans)}")
    if journal:
        journal.write("", "", {"k": "run", "state": "started", "points": len(plans), "title": title,
                               **({"header": title_line} if title_line else {})})
    def manifest() -> None:
        if base:
            record.write_atomic(base / "points.json",
                                json.dumps(record.points_manifest(every, run, configuration), indent=1, default=str) + "\n")
    manifest()
    failed = done = 0
    verdict = "stopped"
    try:
        if args.only in (None, "pre"):
            if not post.run_pre(pre_plan, run, configuration, sink=shown, journal=journal, stopper=stopper,
                                rerun=args.rerun or args.only == "pre"):
                verdict = "pre failed: no point ran"
                return 6 if stopper.requested else 1
            if args.only == "pre":
                verdict = "pre done"
                return 0
        if args.only != "post":
            done, failed, stopped = execute.run_points(plans, run, configuration, sink=shown, journal=journal,
                                                       stopper=stopper, rerun=args.rerun)
            if stopped:
                return 6
        verdict = f"{done} done, {failed} failed, {len(plans) - done - failed} skipped" if args.only != "post" else ""
        manifest()                           # post tools read it: it must say which points are complete
        if combined and args.only != "post":
            bad = post.run_combined(combined, every, run, configuration, sink=shown, journal=journal, stopper=stopper,
                                    rerun=args.rerun, say=shown.say)
            if stopper.requested:
                return 6
            if bad:
                failed += bad
                verdict = f"{verdict}, {bad} combined group(s) failed"
        if not post.run(post_plan, every, run, configuration, sink=shown, journal=journal, stopper=stopper,
                        rerun=args.rerun or args.only == "post", say=shown.say):
            if stopper.requested:
                return 6
            failed += 1
            verdict = ", ".join(v for v in (verdict, "post failed") if v)
        elif post_plan is not None and args.only == "post":
            verdict = "post done"
        if args.only != "post":
            failed += plot.draw(run, configuration, combined or every, shown.say) > 0   # the groups, when combined
        shown.say(verdict)                   # before end(): the view's thread prints it (V32)
    finally:
        shown.end()
        manifest()
        if journal:
            onward = {"next": str(following)} if following and not stopper.requested else {}
            journal.write("", "", {"k": "run", "state": "finished", "verdict": verdict, **onward})
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
    for number, key in enumerate(keys, 1):   # under [run].sweep, every swept configuration's pages (V38)
        planned = build_plans(args, key)
        if len(keys) > 1:
            print(("\n" if number > 1 else "") + header(number, planned.configuration))
        failed = plot.draw(planned.run, planned.configuration, planned.combined or planned.every, print) or failed
    return 1 if failed else 0


def cmd_watch(args) -> int:
    """Follow a job from another terminal: its status.jsonl, or the most recent one under output/."""
    if args.config:                          # under [run].sweep: the swept run written to last (V38)
        run = configmod.load(args.config)
        journals = [journal_path(run, run.configurations[key]) for key in run.runs(args.configuration)]
        present = [j for j in journals if j.exists()]
        journal = max(present, key=lambda j: j.stat().st_mtime) if present else journals[0]
    else:
        found = sorted(output_root().glob("*/*/*/status.jsonl"), key=lambda p: p.stat().st_mtime)
        if not found:
            raise HepError("no job to watch", where=str(output_root()), hint="start one with hep run")
        journal = found[-1]
    if not journal.exists():
        raise HepError("that configuration has no status yet", where=str(journal),
                       hint="it has not been run, or is about to start")
    return follow(journal, plain=args.plain)


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "run":
            return cmd_run(args)
        if args.command == "plot":
            return cmd_plot(args)
        return cmd_watch(args)
    except HepError as error:
        print(error.render(), file=sys.stderr)
        return 2
