"""`hep run` and `hep watch` (rank 5): argument parsing, and nothing else.

docs/rework_v2/03_Layout_Build.md §6. `hep build` is handled by the shell dispatcher
(utils/Env/hep), which runs make.
"""

from __future__ import annotations

import argparse
import sys

from .errors import HepError


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

    watch = commands.add_parser("watch", help="attach the live view to a running job")
    watch.add_argument("config", nargs="?", help="the run config whose job to watch")
    return top


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command in ("run", "watch"):
            raise HepError(f"`hep {args.command}` is not built yet",
                           hint="it arrives in P1 (docs/rework_v2/phases/P1_one-chain.md)")
    except HepError as error:
        print(error.render(), file=sys.stderr)
        return 2
    return 0
