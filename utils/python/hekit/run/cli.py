"""`hep run`: the command everything else in P3 was built for (08 §2).

It is deliberately thin. Planning is `hekit.plan`, running processes is `hekit.run.supervisor`,
rendering is `hekit.term`, deciding what may be skipped is `hekit.results.skip`, and explaining a
result afterwards is `hekit.prov`. What is left here is the *order* — and the order is the thing the
old `rivpyth` main loop got wrong twice, so it is worth stating:

1. **plan everything first.** Every point, every generation, every hash, before a single process
   starts. A run that would collide with an existing result must say so before it burns an hour.
2. **preflight every group** (`hep-run --check`): cards read, analyses loaded, Pythia initialised,
   nothing generated. A typo in point four is found in the first two seconds, not after three points
   have run (the "Preflight" row of this step).
3. **then run them, one at a time**, each with its own journal, its own logs and its own provenance.
4. **stop meaning stop.** The first Ctrl-C lets the current point finish its chunk and write partial
   outputs, and starts no further points; the second and third escalate. Anything else throws away
   work the user has already paid for.

Exit code: the worst point's, so `hep run && hep plot` does the right thing in a script.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

import click

from ..config import load_config
from ..errors import HepError
from ..plan.cli import selectors
from ..results import layout as layout_module
from ..results import manifest as manifest_module
from ..results import skip as skip_module
from ..sweep import select
from ..term import model, theme
from . import journal as journal_module
from . import signals as signal_policy
from .supervisor import StageSpec, Supervisor


@click.command("run")
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@selectors
@click.option("--index", type=int, help="only this 1-based point")
@click.option("--events", type=int, help="override [run].events")
@click.option("--threads", type=int, help="override [run].threads")
@click.option("--rerun", is_flag=True, help="run points that already have results")
@click.option("--check", is_flag=True, help="preflight every generation and stop before generating")
@click.option("--detach", is_flag=True, help="start in the background; watch it with `hep watch`")
@click.option("--plain", "force_plain", is_flag=True, help="plain lines instead of the dashboard")
@click.option("--label", default="", help="free text recorded in the study manifest and its directory")
@click.pass_context
def run(context: click.Context, config_file: Path, study, pins, across, style, overlay, sets,
        index, events, threads, rerun, check, detach, force_plain, label) -> None:
    """Generate and analyse the points of a config."""
    from ..plan import build as builder
    from ..plan import spec as spec_module

    overrides = list(sets)
    if events is not None:
        overrides.append(f"run.events={events}")
    if threads is not None:
        overrides.append(f"run.threads={threads}")

    config = load_config(config_file, sets=tuple(overrides))
    selection = select(config, study=study, pins=tuple(pins), across=across, style=style,
                       overlay=overlay)
    plan = builder.build(config, selection, index=index)

    if detach:
        raise SystemExit(_detach(context, config_file))

    runner = Runner(config=config, plan=plan, label=label or config.run.label, rerun=rerun,
                    plain=force_plain or (context.obj or {}).get("plain", False),
                    cli=_command_line())
    raise SystemExit(runner.go(check_only=check))


def _command_line() -> str:
    return "hep " + " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "hep run"


def _detach(context: click.Context, config_file: Path) -> int:
    """Start the same command under `setsid`, plain, with its output in a log (06 §6)."""
    import subprocess

    arguments = [argument for argument in sys.argv[1:] if argument != "--detach"]
    log = Path(layout_module.Path(os.environ.get("HEKIT_LOG_DIR", ".")))     # cwd unless told
    log.mkdir(parents=True, exist_ok=True)
    handle = open(log / "run.log", "ab", buffering=0)
    child = subprocess.Popen([sys.argv[0] if sys.argv[0].endswith("hep") else sys.executable,
                              *( [] if sys.argv[0].endswith("hep") else ["-m", "hekit"]),
                              *arguments, "--plain"],
                             stdout=handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             start_new_session=True)
    click.echo(f"started in the background (pid {child.pid}); watch it with `hep watch latest`")
    return 0


class Runner:
    """One `hep run`: plan in, results and an exit code out."""

    def __init__(self, *, config: Any, plan: Any, label: str = "", rerun: bool = False,
                 plain: bool = False, cli: str = "") -> None:
        self.config = config
        self.plan = plan
        self.label = label
        self.rerun = rerun
        self.plain = plain or not sys.stdout.isatty()
        self.cli = cli
        self.layout = layout_module.Layout.of(config)
        self.interrupts = 0
        self._consumed: dict[tuple[str, str], int] = {}
        self.view = model.RunView(command=cli, project=config.project,
                                  git=self._git(), study=getattr(plan, "study", "") or "",
                                  log_tail=getattr(config.terminal, "log_tail", 6))

    # ── the run ──────────────────────────────────────────────────────────────

    def go(self, *, check_only: bool = False) -> int:
        from ..plan import spec as spec_module

        theme.autodetect(sys.stdout)
        binary = self._binary()
        decisions = self._decisions()
        for group in self.plan.groups:
            point = self.view.add_point(group.name)
            decision = decisions[group.name]
            if decision.skip and decision.state is skip_module.State.MISMATCH:
                raise HepError(decision.reason, hint=decision.hint)

        # Everything is written before anything runs, so a spec is on disk even for a point that is
        # skipped — that is what makes `hep show` work on a skipped point.
        for group in self.plan.groups:
            directory = self.layout.point(group.name)
            directory.mkdir(parents=True, exist_ok=True)
            group.directory = directory
            spec_module.write_group(group, directory) if hasattr(spec_module, "write_group") else \
                self._write_group(spec_module, group, directory)

        failures = self._preflight(binary, decisions)
        if failures:
            return failures
        if check_only:
            click.echo(f"checked {len(self.plan.groups)} generation(s): cards, analyses and init are "
                       f"all usable")
            return 0

        study_dir = self.layout.new_study(self.view.study or "adhoc", label=self.label,
                                          serial=bool(getattr(self.config.run, "serial", True)))
        record = manifest_module.Manifest.for_run(
            study_dir, self.view.study or "adhoc", project=self.config.project, label=self.label,
            cli=self.cli, config=str(self.config.path))

        worst = 0
        with self._signals(), self._renderer() as renderer:
            for group in self.plan.groups:
                point = self.view.point(group.name)
                decision = decisions[group.name]
                if decision.skip:
                    self.view.finish_point(point, state=model.SKIPPED, reason=decision.reason)
                    renderer.refresh()
                    self._note(point)
                elif self.interrupts:
                    continue                      # stopped: start nothing new (this step's Ctrl-C row)
                else:
                    worst = max(worst, self._run_group(binary, group, point, renderer))
                record.add_point(group.name, point_hash=group.identity.hash,
                                 directory=self.layout.point(group.name), state=point.state,
                                 aliases=list(group.aliases))
            # Inside the renderer, so the last frame the user sees is the finished one rather than a
            # live view with the Ctrl-C hint still on it.
            self.view.finish(worst)
            renderer.refresh()
        record.exit_code = worst
        record.write()
        self._final_report(study_dir)
        return worst

    # ── one generation ───────────────────────────────────────────────────────

    def _run_group(self, binary: str, group: Any, point: model.PointView, renderer) -> int:
        directory = self.layout.point(group.name)
        spec_path = directory / "run.toml"
        logs = self.layout.logs(group.name)

        self.view.start_point(point)
        with journal_module.Journal(directory) as book:
            book.header(cli=self.cli, project=self.config.project, git=self.view.git,
                        study=self.view.study, points=[entry.name for entry in self.view.points])
            book.point(group.name, model.RUNNING)

            supervisor = Supervisor(
                poll=0.1, log_dir=logs,
                stall_after=_seconds(getattr(self.config.terminal, "stall_after", 0)),
                stall_kill=0.0)
            stages = [StageSpec(name=stage.name, role=stage.role, command=list(stage.command),
                                tool="" if stage.name == "hep-run" else self.config.generator.tool,
                                status=(stage.name == "hep-run"), cwd=directory)
                      for stage in group.stages]
            for stage in stages:
                if stage.command and stage.command[0] == "hep-run":
                    stage.command = [binary, str(spec_path)]

            outcome = supervisor.run(
                stages,
                on_status_fd=lambda spec, fd: _point_status_fd(spec_path, fd),
                watch=lambda runs: self._on_poll(point, runs, book, renderer),
                # Every stage has its own session, so the user's Ctrl-C reaches `hep` alone; this is
                # what passes it on (first: finish the chunk and write partial outputs).
                should_stop=lambda: self.interrupts)

            self._finish_point(point, group, outcome, book, directory)
            renderer.refresh()
        return outcome.exit_code

    def _on_poll(self, point: model.PointView, runs, book, renderer) -> None:
        """Move what the supervisor has just read into the view, the journal and the screen."""
        for stage_run in runs:
            reader = stage_run.reader
            if reader is not None:
                self._drain_reader(point, stage_run, reader, book)
            elif stage_run.progress.events is not None:
                stage = point.stage(stage_run.name)
                stage.done = stage_run.progress.events
                stage.total = stage_run.progress.total or point.events_wanted
                stage.last_line = stage_run.progress.last_line
        renderer.refresh()

    def _drain_reader(self, point: model.PointView, stage_run, reader, book) -> None:
        """`StatusReader` folds messages into itself; the view needs the same ones."""
        stage = point.stage(stage_run.name)
        stage.done, stage.total, stage.rate = reader.done, reader.total, reader.rate
        stage.threads, stage.mode = reader.threads, reader.mode
        stage.phase = reader.phase
        stage.workers = list(reader.workers)
        point.events = reader.done or point.events
        point.events_wanted = reader.total or point.events_wanted
        if reader.xsec_pb:
            point.xsec_pb, point.xsec_err_pb = reader.xsec_pb, reader.xsec_error_pb
            point.xsec_final = reader.xsec_final
        seen = self._consumed.get((point.name, stage_run.name), 0)
        self._consumed[(point.name, stage_run.name)] = len(reader.logs)
        for entry in reader.logs[seen:]:
            self.view.log(point, entry["level"], entry["source"], entry["msg"])
            if entry["level"] in {"warn", "error"}:
                point.warnings[entry["source"]] = point.warnings.get(entry["source"], 0) + 1
            book.write({"k": "log", **entry, "point": point.name, "stage": stage_run.name})
        if reader.summary:
            book.write({"k": "summary", **reader.summary, "point": point.name,
                        "stage": stage_run.name})
        book.write({"k": "progress", "done": stage.done, "total": stage.total, "rate": stage.rate,
                    "workers": stage.workers, "point": point.name, "stage": stage_run.name})

    def _finish_point(self, point: model.PointView, group: Any, outcome, book, directory: Path) -> None:
        state = {0: model.DONE, signal_policy.EXIT_STOPPED: model.STOPPED}.get(
            outcome.exit_code, model.FAILED)
        outputs = sorted(str(path) for path in directory.glob("*.yoda"))
        self.view.finish_point(point, state=state, exit_code=outcome.exit_code,
                               reason=outcome.attribution.reason, outputs=outputs)
        book.point(group.name, state, exit_code=outcome.exit_code,
                   reason=outcome.attribution.reason, outputs=outputs)
        book.done(outcome.exit_code)
        self._stamp_and_record(group, point, directory, outcome)

    def _stamp_and_record(self, group: Any, point: model.PointView, directory: Path, outcome) -> None:
        """Stamp the YODA and write provenance (07 §2). Neither may fail the run."""
        from ..prov import provenance as prov
        from ..prov import stamp as stamp_module

        summary = None
        summary_path = directory / "run.summary.json"
        if summary_path.is_file():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                summary = None

        for path in directory.glob("*.yoda"):
            stamp_module.stamp(path, group.name, group.identity.hash)

        try:
            record = prov.assemble(
                spec=group.spec, summary=summary,
                origin={"config": str(self.config.path), "study": self.view.study, "cli": self.cli},
                outputs=sorted(directory.glob("*.yoda")), exit_code=outcome.exit_code,
                pdf_sets=_pdf_sets(group), analysis_paths=[])
            record.write(directory)
        except Exception as error:                      # noqa: BLE001 - provenance is never fatal
            self.view.log(point, "warn", "hekit", f"provenance could not be written: {error}")

    # ── preflight, skipping, signals, rendering ──────────────────────────────

    def _preflight(self, binary: str, decisions) -> int:
        """`hep-run --check` for every generation that would run, before spawning any of them."""
        import subprocess

        for group in self.plan.groups:
            if decisions[group.name].skip:
                continue
            spec_path = self.layout.point(group.name) / "run.toml"
            done = subprocess.run([binary, str(spec_path), "--check", "--plain"],
                                  capture_output=True, text=True, timeout=1800)
            if done.returncode != 0:
                message = next((line for line in done.stderr.splitlines()
                                if line.startswith("hep-run:")), "").replace("hep-run: ", "")
                click.echo(f"hep: {group.name} cannot run: {message or f'exit {done.returncode}'}",
                           err=True)
                click.echo(f"hep: nothing was generated; the log above is from `hep-run --check`",
                           err=True)
                return done.returncode
        return 0

    def _decisions(self):
        pairs = [(group.name, self.layout.point(group.name), group.identity.hash)
                 for group in self.plan.groups]
        if not getattr(self.config.run, "skip_existing", False) and not self.rerun:
            # Without skip_existing every point runs, but a name/hash clash is still refused.
            found = skip_module.decide_all(pairs, rerun=False)
            return {name: (decision if decision.state is skip_module.State.MISMATCH
                           else skip_module.Decision(decision.state, True, "skip_existing is off"))
                    for name, decision in found.items()}
        return skip_module.decide_all(pairs, rerun=self.rerun)

    def _signals(self):
        """Ctrl-C: first stops at the next checkpoint, then SIGTERM, then SIGKILL (06 §4)."""
        import contextlib

        @contextlib.contextmanager
        def handler():
            def on_interrupt(_number, _frame):
                self.interrupts += 1
                if self.interrupts == 1:
                    click.echo("\nhep: stopping at the next checkpoint; Ctrl-C again to abort",
                               err=True)
                elif self.interrupts == 2:
                    click.echo("hep: aborting", err=True)

            previous = signal.signal(signal.SIGINT, on_interrupt)
            try:
                yield
            finally:
                signal.signal(signal.SIGINT, previous)

        return handler()

    def _renderer(self):
        import contextlib

        if self.plain:
            from ..term.plain import PlainRenderer

            renderer = PlainRenderer(view=self.view, stream=sys.stdout)

            @contextlib.contextmanager
            def plain_context():
                renderer.run_started()
                try:
                    yield renderer
                finally:
                    renderer.run_finished()

            return plain_context()

        from ..term.dashboard import Dashboard

        @contextlib.contextmanager
        def live_context():
            with Dashboard(view=self.view) as dashboard:
                yield dashboard

        return live_context()

    def _note(self, point: model.PointView) -> None:
        if self.plain:
            click.echo(f"hep: {point.name}: {point.reason}")

    def _final_report(self, study_dir: Path) -> None:
        done = sum(1 for point in self.view.points if point.state == model.DONE)
        skipped = sum(1 for point in self.view.points if point.state == model.SKIPPED)
        failed = len(self.view.failed_points)
        parts = [f"{done} done"]
        if skipped:
            parts.append(f"{skipped} skipped")
        if failed:
            parts.append(f"{failed} failed")
        click.echo(f"hep: {', '.join(parts)} in {theme.duration(self.view.elapsed())} → {study_dir}")

    # ── small helpers ────────────────────────────────────────────────────────

    def _binary(self) -> str:
        from ..env.doctor import hep_run_path

        found = hep_run_path()
        if not found:
            raise HepError("hep-run is not built",
                           hint="build it with `hep build`, or `cmake --build build`")
        return found

    def _git(self) -> str:
        from ..prov.stamp import git_label

        return git_label()

    def _write_group(self, spec_module, group: Any, directory: Path) -> None:
        """The spec and the card, in the point's own directory (paths are already absolute there)."""
        from ..plan import naming

        card_name = naming.card_path(self.config, group.name, self.config.generator.tool).name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "run.toml").write_text(spec_module.dumps(group.spec), encoding="utf-8")
        if group.card:
            (directory / card_name).write_text(group.card, encoding="utf-8")


def _point_status_fd(spec_path: Path, fd: int) -> None:
    """Tell `hep-run` which descriptor to write status on.

    The number cannot be agreed in advance — `pass_fds` keeps whatever the pipe got — so the spec is
    rewritten with it just before the child starts (P3-S02).
    """
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError:
        return
    import re

    if "[status]" in text:
        text = re.sub(r"(?m)^fd = \d+$", f"fd = {fd}", text)
    else:
        text += f"\n[status]\nfd = {fd}\n"
    spec_path.write_text(text, encoding="utf-8")


def _pdf_sets(group: Any) -> list[str]:
    """The LHAPDF sets a rendered card asks for, for provenance."""
    import re

    return sorted(set(re.findall(r"LHAPDF6:([\w.+-]+)", group.card or "")))


def _seconds(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


@click.command()
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--events", default=10000, show_default=True)
def bench(config_file: Path, events: int) -> None:            # pragma: no cover - P6-S03
    """Measure sink cost and recommend a concurrency mode."""
    from ..errors import NotImplementedYet
    raise NotImplementedYet("bench", "P6-S03")
