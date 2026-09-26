"""The `hep` command: groups and global options only, no logic.

Subcommands are loaded lazily. `hep --help` must stay fast, so nothing here imports rich, yoda, ROOT or
any other heavy dependency at start-up; a command's module is imported only when that command runs.
The command tree is docs/rework/08_CLI.md §2; each entry records the step that implements it, so an
unimplemented command says so instead of failing obscurely.
"""

from __future__ import annotations

import sys

import click

from . import __version__
from .errors import HepError, NotImplementedYet, did_you_mean

#: command -> (module:attribute, implementing step, one-line help)
COMMANDS: dict[str, tuple[str, str, str]] = {
    "run":      ("hekit.run.cli:run",          "P3-S05", "generate and analyse the points of a config"),
    "plan":     ("hekit.plan.cli:plan",        "P1-S05", "show what a config expands to, without running it"),
    "plot":     ("hekit.plot.cli:plot",        "P4-S02", "draw pages or single points from existing results"),
    "compare":  ("hekit.results.cli:compare",  "P4-S04", "compare curves or points (chi2/ndf, pulls)"),
    "watch":    ("hekit.term.cli:watch",       "P3-S04", "attach to a running job"),
    "runs":     ("hekit.results.cli:runs",     "P3-S04", "list runs"),
    "show":     ("hekit.results.cli:show",     "P3-S04", "provenance and settings of a point or run"),
    "events":   ("hekit.term.cli:events",      "P5-S03", "inspect events from a config, point or store"),
    "store":    ("hekit.store.cli:store",      "P5-S01", "HepMC3 event stores: ls, info, verify"),
    "proc":     ("hekit.proc.cli:proc",        "P9-S01", "fits and derived histograms (ROOT processing)"),
    "analyses": ("hekit.env.cli:analyses",     "P1-S07", "list Rivet analyses with their options"),
    "studies":  ("hekit.config.cli:studies",   "P1-S05", "list the studies a config declares"),
    "config":   ("hekit.config.cli:config",    "P1-S06", "init, validate, migrate, reference"),
    "pdf":      ("hekit.env.cli:pdf",          "P1-S07", "check, list and install LHAPDF sets"),
    "build":    ("hekit.env.cli:build",        "P2-S01", "build analyses, modules and hep-run (wraps cmake)"),
    "bench":    ("hekit.run.cli:bench",        "P6-S03", "measure analyzer cost and recommend a concurrency mode"),
    "doctor":   ("hekit.env.cli:doctor",       "P1-S07", "toolchain versions, imports, capabilities, env sanity"),
    "clean":    ("hekit.results.cli:clean",    "P10-S01", "remove caches, old events, orphaned outputs"),
    "new":      ("hekit.env.cli:new",          "P10-S01", "scaffold an analysis, module or project"),
}


def _show_version(context: click.Context, parameter: click.Parameter, value: bool) -> None:
    if not value or context.resilient_parsing:
        return
    click.echo(version_text())
    context.exit()


class LazyGroup(click.Group):
    """A group whose subcommands are imported on demand."""

    def list_commands(self, context: click.Context) -> list[str]:
        return sorted(COMMANDS)

    def get_command(self, context: click.Context, name: str) -> click.Command:
        if name not in COMMANDS:
            hint = did_you_mean(name, COMMANDS)
            raise HepError(f"unknown command '{name}'", hint=hint or "try: hep --help")
        command, _ = self._resolve(name)
        return command

    @staticmethod
    def _resolve(name: str) -> tuple[click.Command, bool]:
        """(command, implemented). An unimplemented command becomes a placeholder that says which step adds it."""
        target, step, summary = COMMANDS[name]
        module_name, _, attribute = target.partition(":")
        try:
            module = __import__(module_name, fromlist=[attribute])
            command = getattr(module, attribute)
        except (ImportError, AttributeError):
            @click.command(name=name, short_help=f"{summary}  (step {step})",
                           context_settings={"ignore_unknown_options": True})
            @click.argument("ignored", nargs=-1, type=click.UNPROCESSED)
            def placeholder(ignored: tuple[str, ...]) -> None:
                raise NotImplementedYet(name, step)

            return placeholder, False
        command.short_help = summary
        return command, True

    def format_commands(self, context: click.Context, formatter: click.HelpFormatter) -> None:
        rows = [(name, self._resolve(name)[0].short_help or "") for name in self.list_commands(context)]
        with formatter.section("Commands"):
            formatter.write_dl(rows)


@click.group(cls=LazyGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--project-root", type=click.Path(file_okay=False), envvar="HEKIT_ROOT",
              help="repository root (default: found from the package or the current directory)")
@click.option("-v", "--verbose", count=True, help="more detail; repeat for more")
@click.option("-q", "--quiet", is_flag=True, help="only warnings and errors")
@click.option("--plain", is_flag=True, envvar="HEKIT_PLAIN",
              help="no live rendering: plain lines, for logs, pipes and remote sessions")
@click.option("--version", is_flag=True, is_eager=True, expose_value=False, callback=_show_version,
              help="show the version, the git state and the repository root")
@click.pass_context
def hep(context: click.Context, project_root: str | None, verbose: int, quiet: bool, plain: bool) -> None:
    """Run, inspect and plot high-energy physics studies."""
    import os

    if project_root:
        os.environ["HEKIT_ROOT"] = project_root
    context.obj = {"verbose": verbose, "quiet": quiet, "plain": plain or not sys.stdout.isatty()}


def version_text() -> str:
    from .env import paths
    from .prov import git_state

    state = git_state()
    sha = state["sha"] or "no git"
    dirty = "+dirty" if state["dirty"] else ""
    try:
        root = paths.repo_root()
    except HepError:
        root = "not found"
    return f"hep {__version__} ({sha}{dirty}) root: {root}"


def main(arguments: list[str] | None = None) -> int:
    """Entry point: turns HepError into a message and an exit code."""
    try:
        # standalone_mode=False so that click returns instead of calling sys.exit itself
        hep.main(args=arguments, standalone_mode=False)
    except HepError as error:
        click.echo(f"hep: {error.render()}", err=True)
        return error.exit_code
    except click.ClickException as error:
        error.show()
        return error.exit_code
    except click.exceptions.Abort:
        click.echo("hep: interrupted", err=True)
        return 130
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
