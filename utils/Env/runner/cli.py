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
from .quantities import load_master
from .status import Journal
from .watch import PlainView


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
    watch.add_argument("config", nargs="?", help="the run config whose job to watch")
    return top


def build_plans(args):
    run = configmod.load(args.config, sets=args.set)
    configuration = run.configuration(args.configuration)
    master = load_master(run.project, run.master_toml)
    points = sweep.select_points(run, configuration, sweep.points(run, configuration), args.points)
    plans = []
    for point in points:
        plan = tools.plan_point(run, configuration, point, master)
        plan.identity = record.identity(plan)
        plans.append(plan)
    record.assign_seeds(plans)
    for plan in plans:
        tools.finalise(plan, plan.seed)
    return run, configuration, plans


def print_plan(run, configuration, plans) -> None:
    print(f"run {run.name} ({run.path}) · configuration {configuration.key}: {len(plans)} point(s), "
          f"{configuration.event_count} events, {configuration.threads} threads")
    for plan in plans:
        state = "complete" if record.is_complete(plan) else "to run"
        for line in tools.describe(plan, run):
            print(line)
        print(f"  output  {plan.out}\n  results {plan.res}   ({state})")


def cmd_run(args) -> int:
    run, configuration, plans = build_plans(args)
    if args.only:
        raise HepError(f"--only {args.only} arrives with the plot and post stages (P3)")
    if args.plan:
        print_plan(run, configuration, plans)
        return 0

    view = PlainView()
    view.begin(len(plans))
    stopper = execute.Stopper()

    def on_signal(signum, frame):
        if stopper.requested:                # a second Ctrl-C: the default behaviour
            signal.signal(signum, signal.SIG_DFL)
        stopper.requested = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    base = plans[0].out.parent if plans else None
    journal = Journal(base / "status.jsonl") if base else None
    if base:
        record.write_atomic(base / "plan.json", json.dumps({
            "run": run.name, "configuration": configuration.key, "config_file": str(run.path),
            "points": [{"name": p.point.name, "identity": p.identity, "seed": p.seed, "results": str(p.res)}
                       for p in plans]}, indent=1) + "\n")
    failed = 0
    try:
        for plan in plans:
            if not args.rerun and record.is_complete(plan):
                view.skipped(plan)
                continue
            result = execute.run_point(plan, run, configuration, sink=view, journal=journal, stopper=stopper)
            if result.stopped or stopper.requested:
                return 6
            failed += not result.ok
    finally:
        if journal:
            journal.close()
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "run":
            return cmd_run(args)
        raise HepError("`hep watch` arrives in P1 S3")
    except HepError as error:
        print(error.render(), file=sys.stderr)
        return 2
