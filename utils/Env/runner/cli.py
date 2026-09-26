"""`hep run` and `hep watch` (rank 5): argument parsing and the order of events.

docs/rework_v2/03_Layout_Build.md §6. `hep build` is handled by the shell dispatcher
(utils/Env/hep), which runs make.

Exit codes: 0 every point done (or skipped), 1 a point failed, 2 a config error before anything ran,
6 stopped by the user.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys

from . import config as configmod
from . import execute, record, sweep, tools
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
    run.add_argument("configuration", nargs="?", help="overrides [run].configuration")
    run.add_argument("--plan", action="store_true", help="print the plan; run nothing")
    run.add_argument("--points", metavar="SEL", help="run a subset: tags, indices or quantity=tag")
    run.add_argument("--set", metavar="KEY=VALUE", action="append", default=[],
                     help="override one value for this invocation (repeatable)")
    run.add_argument("--rerun", action="store_true", help="ignore skip-unchanged")
    run.add_argument("--only", choices=["post", "plot"], help="rerun only the post tools or plots")
    run.add_argument("--plain", action="store_true", help="plain lines instead of the live view")

    watch = commands.add_parser("watch", help="attach the live view to a running job")
    watch.add_argument("config", nargs="?", help="the run config whose job to watch (default: the latest job)")
    watch.add_argument("configuration", nargs="?", help="overrides [run].configuration")
    watch.add_argument("--plain", action="store_true", help="plain lines instead of the live view")
    return top


def build_plans(args):
    run = configmod.load(args.config, sets=args.set)
    configuration = run.configuration(args.configuration)
    master = load_master(run.project, run.master_toml)
    points = sweep.points(run, configuration)
    chosen = {p.index for p in sweep.select_points(run, configuration, points, args.points)}
    plans = []
    for point in points:
        plan = tools.plan_point(run, configuration, point, master)
        plan.identity = record.identity(plan)
        plans.append(plan)
    record.assign_seeds(plans)
    for plan in plans:
        tools.finalise(plan, plan.seed)
    return run, configuration, plans, [p for p in plans if p.point.index in chosen]


def print_plan(run, configuration, plans) -> None:
    print(f"run {run.name} ({run.path}) · configuration {configuration.key}: {len(plans)} point(s), "
          f"{configuration.event_count} events, {configuration.threads} threads")
    for plan in plans:
        state = "complete" if record.is_complete(plan) else "to run"
        for line in tools.describe(plan, run):
            print(line)
        print(f"  output  {plan.out}\n  results {plan.res}   ({state})")


def cmd_run(args) -> int:
    run, configuration, every, plans = build_plans(args)
    if args.only:
        raise HepError(f"--only {args.only} arrives with the plot and post stages (P3)")
    if args.plan:
        print_plan(run, configuration, plans)
        return 0

    shown = view(args.plain)
    stopper = execute.Stopper()

    def on_signal(signum, frame):
        if stopper.requested:                # a second Ctrl-C: the default behaviour
            signal.signal(signum, signal.SIG_DFL)
        stopper.requested = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    base = plans[0].out.parent if plans else None
    journal = Journal(base / "status.jsonl") if base else None
    title = f"{run.name} · {configuration.key}: {len(plans)} point(s), {configuration.event_count} events, {configuration.threads} threads"
    shown.begin(len(plans), title)
    if journal:
        journal.write("", "", {"k": "run", "state": "started", "points": len(plans), "title": title})
    def manifest() -> None:
        if base:
            record.write_atomic(base / "points.json",
                                json.dumps(record.points_manifest(every, run, configuration), indent=1, default=str) + "\n")
    manifest()
    failed = done = 0
    verdict = "stopped"
    try:
        for plan in plans:
            if not args.rerun and record.is_complete(plan):
                shown.skipped(plan)
                continue
            result = execute.run_point(plan, run, configuration, sink=shown, journal=journal, stopper=stopper)
            if result.stopped or stopper.requested:
                return 6
            failed += not result.ok
            done += result.ok
        verdict = f"{done} done, {failed} failed, {len(plans) - done - failed} skipped"
    finally:
        shown.end()
        manifest()
        if journal:
            journal.write("", "", {"k": "run", "state": "finished", "verdict": verdict})
            journal.close()
    shown.say(verdict)
    return 1 if failed else 0


def cmd_watch(args) -> int:
    """Follow a job from another terminal: its status.jsonl, or the most recent one under output/."""
    if args.config:
        run = configmod.load(args.config)
        configuration = run.configuration(args.configuration)
        journal = (output_root() / run.project / tools.location(run.serial, run.name)
                   / tools.location(configuration.serial, configuration.name) / "status.jsonl")
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
        return cmd_watch(args)
    except HepError as error:
        print(error.render(), file=sys.stderr)
        return 2
