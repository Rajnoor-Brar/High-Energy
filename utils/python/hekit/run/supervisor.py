"""Running a point's stages and watching them (02 §3, 06 §4).

The old `rivpyth` had the shape of this right — poll both processes, because Rivet blocks on opening
the FIFO and a generator that dies first would otherwise never be noticed — and three things wrong:
shared `/tmp` paths (00/B19), attribution that reported the generator's SIGPIPE instead of Rivet's real
error (00/B20), and a hang that nothing ever detected. This is that control flow, generalised from two
processes to a chain, with those three fixed.

What a supervised run does, in order:

1. open a private directory for this run's FIFOs (`transport`), which is removed whatever happens;
2. spawn every stage at once, each in its own process group, each with its own log file;
3. poll: reap statuses, drain output into the logs, feed the progress parsers, read `hep-run`'s status
   descriptor, and call the watcher so a terminal can draw;
4. the moment one stage fails, give the others a grace period to finish on their own — their real
   statuses are worth more than a fast exit — then escalate SIGINT → SIGTERM → SIGKILL;
5. if nothing writes anything and no status arrives for `stall_after`, say so; after `stall_kill`,
   stop the run and report exit 7;
6. attribute the failure (`signals.attribute`) and return one outcome.

**Memory is bounded by construction.** Output goes straight into the stage's log file in 64 KiB
chunks; only the last line is kept in memory. A stage that writes a gigabyte to stderr costs a
gigabyte of disk and a few kilobytes of RSS (verification row "Flood").
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from . import signals as signal_policy
from .parsers import Parser, Progress, parser_for
from .status import StatusReader
from .transport import Transport

CHUNK = 64 * 1024
#: A single "line" longer than this is truncated for parsing; the log file still gets every byte.
MAX_LINE = 8 * 1024


@dataclass
class StageSpec:
    """One process to run. Mirrors `hekit.plan.model.Stage` plus what only running needs."""

    name: str
    command: Sequence[str]
    role: str = "generate"
    tool: str = ""                            # picks a progress parser; empty for hep-run
    log: Path | None = None
    cwd: Path | None = None
    env: dict[str, str] | None = None
    status: bool = False                      # give it a status descriptor (hep-run)
    note: str = ""


@dataclass
class StageRun:
    """A spawned stage: its process, its log, and what we have learnt from it."""

    spec: StageSpec
    process: subprocess.Popen | None = None
    status: int | None = None
    progress: Progress = field(default_factory=Progress)
    reader: StatusReader | None = None
    log_bytes: int = 0
    last_activity: float = 0.0
    parser: Parser | None = None
    _stream = None                            # the child's stdout/stderr, merged
    _log_handle = None
    _status_read: int | None = None
    _status_tail: str = ""

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None


@dataclass
class Outcome:
    """What a supervised run came to."""

    exit_code: int = 0
    attribution: signal_policy.Attribution = field(default_factory=signal_policy.Attribution)
    stages: list[StageRun] = field(default_factory=list)
    stalled: str = ""
    wall_seconds: float = 0.0
    signals_sent: set[int] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def status_of(self, name: str) -> int | None:
        for stage in self.stages:
            if stage.name == name:
                return stage.status
        return None

    def summary(self) -> str:
        parts = [f"{stage.name}: {signal_policy.describe(stage.status)}" for stage in self.stages]
        head = "ok" if self.ok else f"exit {self.exit_code}"
        if self.attribution.reason:
            head += f" — {self.attribution.reason}"
        return head + " [" + ", ".join(parts) + "]"


class Supervisor:
    """Runs one chain of stages to completion.

    `watch` is called after every poll with the list of stages, so a dashboard can draw without this
    module knowing anything about terminals (06 §4: rendering is P3-S04).
    """

    def __init__(self, *, poll: float = 0.1, grace: float = 10.0, term_grace: float = 5.0,
                 stall_after: float = 0.0, stall_kill: float = 0.0,
                 log_dir: Path | None = None) -> None:
        self.poll = poll
        self.escalation = signal_policy.Escalation(grace=grace, term_grace=term_grace)
        self.stall_after = stall_after          # 0 = never report a stall
        self.stall_kill = stall_kill            # 0 = report but never kill (06 §4 default)
        self.log_dir = log_dir

    # ── running ──────────────────────────────────────────────────────────────

    def run(self, stages: Iterable[StageSpec], *, transport: Transport | None = None,
            watch: Callable[[list[StageRun]], None] | None = None,
            on_status_fd: Callable[[StageSpec, int], None] | None = None,
            should_stop: Callable[[], int] | None = None) -> Outcome:
        """Spawn every stage, watch them, and return one outcome.

        `on_status_fd` is called before spawning a stage that asked for a status descriptor, with the
        descriptor number it will have in the child. `hep run` uses it to write `[status].fd` into the
        spec: the number cannot be chosen in advance, because `pass_fds` keeps the fd it is given.

        `should_stop` returns how many times the user has asked to stop: 1 → SIGINT (hep-run finishes
        its chunk and writes partial outputs), 2 → SIGTERM, 3 → SIGKILL. It is needed because every
        stage runs in its own session, so a Ctrl-C in the user's terminal reaches `hep` and nothing
        else — the forwarding is deliberate, and it is what makes "stop at the next checkpoint" work.
        """
        specs = list(stages)
        owned_transport = transport is None
        transport = transport or Transport(label="chain")
        if owned_transport:
            transport.open()
        started = time.monotonic()
        runs: list[StageRun] = []
        try:
            for spec in specs:
                runs.append(self._spawn(spec, on_status_fd))
            outcome = self._watch(runs, watch, started, should_stop)
        finally:
            self._close(runs)
            if owned_transport:
                transport.close()
        return outcome

    def _spawn(self, spec: StageSpec, on_status_fd) -> StageRun:
        run = StageRun(spec=spec, parser=parser_for(spec.tool) if spec.tool else None)
        log_path = spec.log or (self.log_dir / f"{spec.name}.log" if self.log_dir else None)
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            run._log_handle = open(log_path, "wb")

        pass_fds: tuple[int, ...] = ()
        write_fd = None
        if spec.status:
            read_fd, write_fd = os.pipe()
            os.set_blocking(read_fd, False)
            run._status_read = read_fd
            run.reader = StatusReader()
            pass_fds = (write_fd,)
            if on_status_fd is not None:
                on_status_fd(spec, write_fd)

        environment = dict(os.environ, **(spec.env or {}))
        try:
            run.process = subprocess.Popen(
                list(spec.command),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=str(spec.cwd) if spec.cwd else None, env=environment,
                pass_fds=pass_fds,
                # Its own process group, so one signal reaches a tool's children too, and so a Ctrl-C
                # in the user's terminal does not race us to the children (06 §4).
                start_new_session=True)
        finally:
            if write_fd is not None:
                os.close(write_fd)              # the child owns it now
        os.set_blocking(run.process.stdout.fileno(), False)
        run._stream = run.process.stdout
        run.last_activity = time.monotonic()
        return run

    def _watch(self, runs: list[StageRun], watch, started: float, should_stop=None) -> Outcome:
        failing_since: float | None = None
        stalled_stage = ""
        killed_for_stall = False
        sent: set[int] = set()
        escalated = 0

        while any(run.running for run in runs):
            for run in runs:
                self._drain(run)
                self._read_status(run)
                if run.process is not None and run.status is None:
                    run.status = run.process.poll()
            if watch is not None:
                watch(runs)

            # The user asked to stop: pass it on, one step per request (06 §4).
            wanted = should_stop() if should_stop is not None else 0
            while wanted > escalated and escalated < len(self.escalation.steps):
                step = self.escalation.steps[escalated]
                escalated += 1
                for run in runs:
                    signal_policy.send(run.process, step)
                sent.add(step)

            # A stage that failed takes the pipeline with it — but not immediately: the others get a
            # grace period to end on their own, because their real statuses explain more than ours.
            failed = [run for run in runs
                      if run.status is not None and run.status != 0
                      and not signal_policy.stopped_by_us(run.status, sent)]
            if failed and failing_since is None:
                failing_since = time.monotonic()
            if failing_since is not None and time.monotonic() - failing_since >= self.escalation.grace:
                sent |= signal_policy.stop([run.process for run in runs], self.escalation)
                break

            found = self._stalled(runs)
            stalled_stage = found or stalled_stage          # remembered once seen
            if found and self.stall_kill and self._idle_for(runs) >= self.stall_kill:
                # Decided here, while the stages are still alive: once they are stopped nothing is
                # idle any more, and the reason for stopping would be lost.
                killed_for_stall = True
                sent |= signal_policy.stop([run.process for run in runs], self.escalation)
                break
            time.sleep(self.poll)

        for run in runs:                        # final drain, then the true statuses
            self._drain(run)
            self._read_status(run)
            if run.process is not None:
                try:
                    run.status = run.process.wait(timeout=10)
                except subprocess.TimeoutExpired:          # pragma: no cover - a truly stuck child
                    sent |= signal_policy.stop([run.process], self.escalation)
                    run.status = run.process.poll()
        if watch is not None:
            watch(runs)

        attribution = signal_policy.attribute(
            [(run.name, run.spec.role, run.status) for run in runs],
            sent=sent, stalled=stalled_stage if killed_for_stall else "")
        return Outcome(exit_code=attribution.exit_code, attribution=attribution, stages=runs,
                       stalled=stalled_stage, wall_seconds=time.monotonic() - started,
                       signals_sent=sent)

    # ── reading what a stage produces ────────────────────────────────────────

    def _drain(self, run: StageRun) -> None:
        """Move whatever is waiting into the log file. Never blocks, never grows with the output."""
        stream = run._stream
        if stream is None:
            return
        while True:
            try:
                chunk = stream.read(CHUNK)
            except (BlockingIOError, InterruptedError):    # pragma: no cover - timing dependent
                return
            except ValueError:                             # closed under us
                return
            if not chunk:
                return
            run.log_bytes += len(chunk)
            run.last_activity = time.monotonic()
            if run._log_handle is not None:
                run._log_handle.write(chunk)
                run._log_handle.flush()
            self._parse(run, chunk)

    def _parse(self, run: StageRun, chunk: bytes) -> None:
        if run.parser is None:
            # Still worth the last line: a stage with no parser shows it instead of a progress bar.
            text = chunk.decode("utf-8", errors="replace").rstrip("\n")
            if text:
                run.progress.last_line = text.rsplit("\n", 1)[-1][:200]
            return
        for line in chunk.decode("utf-8", errors="replace").splitlines():
            run.progress.update(run.parser.feed(line[:MAX_LINE]))

    def _read_status(self, run: StageRun) -> None:
        """Read `hep-run`'s JSON lines from its descriptor, without ever blocking on it."""
        if run._status_read is None or run.reader is None:
            return
        while True:
            try:
                chunk = os.read(run._status_read, CHUNK)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:                                # pragma: no cover - closed under us
                return
            if not chunk:
                return
            run.last_activity = time.monotonic()
            text = run._status_tail + chunk.decode("utf-8", errors="replace")
            lines = text.split("\n")
            run._status_tail = lines.pop()                 # keep the unfinished line
            run.reader.feed_lines(lines)

    # ── stalls ───────────────────────────────────────────────────────────────

    def _idle_for(self, runs: list[StageRun]) -> float:
        alive = [run for run in runs if run.running]
        if not alive:
            return 0.0
        return time.monotonic() - max(run.last_activity for run in alive)

    def _stalled(self, runs: list[StageRun]) -> str:
        """The name of a running stage that has produced nothing for `stall_after` (06 §4).

        "Nothing" means no log growth *and* no status message — a quiet stage that is still reporting
        progress is working, and a chatty one that stopped reporting is not necessarily stuck.
        """
        if not self.stall_after:
            return ""
        now = time.monotonic()
        for run in runs:
            if run.running and now - run.last_activity >= self.stall_after:
                return run.name
        return ""

    # ── cleanup ──────────────────────────────────────────────────────────────

    def _close(self, runs: list[StageRun]) -> None:
        for run in runs:
            if run.process is not None and run.process.poll() is None:
                signal_policy.stop([run.process], self.escalation)
            for handle, closer in ((run._stream, lambda handle: handle.close()),
                                   (run._log_handle, lambda handle: handle.close())):
                if handle is not None:
                    try:
                        closer(handle)
                    except Exception:                      # pragma: no cover - already closed
                        pass
            if run._status_read is not None:
                try:
                    os.close(run._status_read)
                except OSError:                            # pragma: no cover - already closed
                    pass
                run._status_read = None
            run._stream = None
            run._log_handle = None
