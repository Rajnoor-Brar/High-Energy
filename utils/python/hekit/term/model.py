"""What a run looks like, as data (06 §1).

One view model feeds three things: the live dashboard, the plain lines, and `hep watch` reading a
`status.jsonl` from another terminal. They must agree, so none of them owns the state — this does.

The model is fed by messages, never by reaching into the supervisor: a message from a live stage and
the same message replayed from a journal produce the same view. That is what makes `hep watch` a
read-only copy of the dashboard rather than a second implementation of it.

The curated log pane is here too, because de-duplication is state: 06 §1 shows warnings collapsed with
a count (`SpaceShower::pT2nearThreshold: stuck in loop ×2`), and a thousand copies of one Pythia
warning must cost one line and one integer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import theme

QUEUED, RUNNING, DONE, FAILED, STOPPED, SKIPPED = (
    "queued", "running", "done", "failed", "stopped", "skipped")
FINISHED = {DONE, FAILED, STOPPED, SKIPPED}


@dataclass
class LogEntry:
    """One curated log line: the first time it was seen, and how often."""

    time: float
    source: str
    level: str
    message: str
    count: int = 1

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source, self.level, self.message)


@dataclass
class StageView:
    """One process of one point, as the terminal shows it."""

    name: str
    role: str = ""
    done: int = 0
    total: int = 0
    rate: float = 0.0
    workers: list[int] = field(default_factory=list)
    mode: str = ""
    threads: int = 0
    phase: str = ""
    detail: str = ""
    last_line: str = ""
    started: float = field(default_factory=time.time)
    finished: float = 0.0
    status: int | None = None

    @property
    def running(self) -> bool:
        return self.finished == 0.0

    @property
    def fraction(self) -> float:
        return (self.done / self.total) if self.total else 0.0

    def eta_seconds(self) -> float | None:
        return theme.eta(self.done, self.total, self.rate)

    def elapsed(self, now: float | None = None) -> float:
        return (self.finished or (now or time.time())) - self.started


@dataclass
class PointView:
    """One point of a run: its stages, its numbers and how it ended."""

    name: str
    index: int = 0
    total_points: int = 0
    state: str = QUEUED
    stages: dict[str, StageView] = field(default_factory=dict)
    events: int = 0
    events_wanted: int = 0
    xsec_pb: float | None = None
    xsec_err_pb: float | None = None
    xsec_final: bool = False
    warnings: dict[str, int] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)
    exit_code: int | None = None
    reason: str = ""
    started: float = 0.0
    finished: float = 0.0
    logs: list[LogEntry] = field(default_factory=list)

    @property
    def running(self) -> bool:
        return self.state == RUNNING

    @property
    def glyph(self) -> str:
        return theme.GLYPH.get(self.state, "·")

    @property
    def colour(self) -> str:
        return theme.COLOUR.get(self.state, "dim")

    @property
    def warning_count(self) -> int:
        return sum(self.warnings.values())

    def stage(self, name: str, role: str = "") -> StageView:
        if name not in self.stages:
            self.stages[name] = StageView(name=name, role=role)
        return self.stages[name]

    def elapsed(self, now: float | None = None) -> float:
        if not self.started:
            return 0.0
        return (self.finished or (now or time.time())) - self.started


@dataclass
class RunView:
    """Everything on screen: the header, the points, and the curated log."""

    command: str = ""
    project: str = ""
    git: str = ""
    study: str = ""
    started: float = field(default_factory=time.time)
    finished: float = 0.0
    points: list[PointView] = field(default_factory=list)
    log_tail: int = 6
    exit_code: int | None = None
    _by_name: dict[str, PointView] = field(default_factory=dict, repr=False)

    # ── points ───────────────────────────────────────────────────────────────

    def add_point(self, name: str, **rest) -> PointView:
        if name in self._by_name:
            return self._by_name[name]
        point = PointView(name=name, index=len(self.points) + 1, **rest)
        self.points.append(point)
        self._by_name[name] = point
        for entry in self.points:
            entry.total_points = len(self.points)
        return point

    def point(self, name: str) -> PointView:
        return self._by_name.get(name) or self.add_point(name)

    @property
    def current(self) -> PointView | None:
        for point in self.points:
            if point.running:
                return point
        return None

    @property
    def done_points(self) -> int:
        return sum(1 for point in self.points if point.state in FINISHED)

    @property
    def failed_points(self) -> list[PointView]:
        return [point for point in self.points if point.state == FAILED]

    def elapsed(self, now: float | None = None) -> float:
        return (self.finished or (now or time.time())) - self.started

    def eta_seconds(self, now: float | None = None) -> float | None:
        """Extrapolated from the points already finished, not from the events of this one.

        A point's own bar knows its events; the *run's* estimate is "how long have the finished ones
        taken", which is the only honest answer while later points have not started.
        """
        finished = [point for point in self.points if point.state in FINISHED and point.finished]
        if not finished or len(finished) >= len(self.points):
            return None
        average = sum(point.elapsed() for point in finished) / len(finished)
        return average * (len(self.points) - len(finished))

    # ── the curated log ──────────────────────────────────────────────────────

    def log(self, point: PointView | None, level: str, source: str, message: str,
            when: float | None = None) -> None:
        """Warnings and errors only, de-duplicated with a count (06 §1)."""
        if level not in {"warn", "error"}:
            return
        target = point.logs if point is not None else self._run_logs
        entry = LogEntry(time=when or time.time(), source=source, level=level, message=message)
        for existing in target:
            if existing.key == entry.key:
                existing.count += 1
                return
        target.append(entry)

    _run_logs: list[LogEntry] = field(default_factory=list, repr=False)

    def recent_logs(self, limit: int | None = None) -> list[LogEntry]:
        """The last `log_tail` curated lines across the run, newest last."""
        entries = list(self._run_logs)
        for point in self.points:
            entries.extend(point.logs)
        entries.sort(key=lambda entry: entry.time)
        limit = self.log_tail if limit is None else limit
        return entries[-limit:] if limit else []

    # ── folding status messages ──────────────────────────────────────────────

    def feed(self, message: Any, *, point: str = "", stage: str = "") -> None:
        """Fold one status message (a `hekit.run.status.Message`, or a plain dict) into the view."""
        fields = getattr(message, "fields", None)
        if fields is None:
            fields = dict(message)
        kind = fields.get("k") or getattr(message, "kind", "")
        when = fields.get("t") or getattr(message, "time", 0.0) or time.time()
        name = point or fields.get("point", "")
        stage_name = stage or fields.get("stage", "") or "hep-run"
        target = self.point(name) if name else None
        if target is None:
            return
        # Only a message that is *about* a process creates one: an `xsec` or a `log` with no stage
        # named would otherwise conjure an empty "hep-run" row onto the screen.
        stage_kinds = {"phase", "init", "progress"}
        view = (target.stage(stage_name) if kind in stage_kinds or stage_name in target.stages
                else StageView(name=stage_name))

        if kind == "phase":
            view.phase = fields.get("phase", "")
            view.detail = fields.get("detail", "")
            if target.state == QUEUED:
                self.start_point(target, when)
        elif kind == "init":
            view.threads = int(fields.get("threads", 0) or 0)
            view.mode = fields.get("mode", "")
            target.events_wanted = target.events_wanted or int(fields.get("events", 0) or 0)
        elif kind == "progress":
            view.done = int(fields.get("done", 0) or 0)
            view.total = int(fields.get("total", 0) or 0)
            view.rate = float(fields.get("rate", 0.0) or 0.0)
            view.workers = [int(entry) for entry in fields.get("workers", []) or []]
            target.events = view.done
            target.events_wanted = target.events_wanted or view.total
        elif kind == "xsec":
            target.xsec_pb = fields.get("value_pb")
            target.xsec_err_pb = fields.get("err_pb")
            target.xsec_final = bool(fields.get("final", False))
        elif kind == "log":
            level = fields.get("level", "info")
            source = fields.get("source", "")
            self.log(target, level, source, fields.get("msg", ""), when)
            if level in {"warn", "error"}:
                target.warnings[source] = target.warnings.get(source, 0) + 1
        elif kind == "checkpoint":
            for output in fields.get("outputs", []) or []:
                if output not in target.outputs:
                    target.outputs.append(output)
        elif kind == "summary":
            target.events = int(fields.get("events", 0) or 0)
            if fields.get("xsec_pb") is not None:
                target.xsec_pb = fields.get("xsec_pb")
                target.xsec_err_pb = fields.get("err_pb")
                target.xsec_final = True
            view.done = view.done or target.events
            view.total = view.total or target.events
        elif kind == "event":
            pass                                  # `hep events` renders these; the dashboard does not

    # ── run-level transitions ────────────────────────────────────────────────

    def start_point(self, point: PointView, when: float | None = None) -> None:
        point.state = RUNNING
        point.started = point.started or (when or time.time())

    def finish_point(self, point: PointView, *, state: str, exit_code: int | None = None,
                     reason: str = "", when: float | None = None,
                     outputs: Iterable[str] = ()) -> None:
        point.state = state
        point.exit_code = exit_code
        point.reason = reason
        point.finished = when or time.time()
        for stage in point.stages.values():
            stage.finished = stage.finished or point.finished
        for output in outputs:
            if output not in point.outputs:
                point.outputs.append(output)

    def finish(self, exit_code: int = 0, when: float | None = None) -> None:
        self.exit_code = exit_code
        self.finished = when or time.time()


def from_journal(lines: Iterable[str], *, log_tail: int = 6) -> RunView:
    """Rebuild a view from a `status.jsonl` — what `hep watch` does (06 §6)."""
    import json

    view = RunView(log_tail=log_tail)
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        kind = payload.get("k")
        if kind == "run":
            view.command = payload.get("cli", view.command)
            view.project = payload.get("project", view.project)
            view.git = payload.get("git", view.git)
            view.study = payload.get("study", view.study)
            view.started = payload.get("t", view.started)
            for name in payload.get("points", []) or []:
                view.add_point(name)
        elif kind == "point":
            point = view.point(payload.get("point", ""))
            state = payload.get("state", QUEUED)
            if state == RUNNING:
                view.start_point(point, payload.get("t"))
            elif state in FINISHED:
                view.finish_point(point, state=state, exit_code=payload.get("exit"),
                                  reason=payload.get("reason", ""), when=payload.get("t"),
                                  outputs=payload.get("outputs", []) or [])
            else:
                point.state = state
        elif kind == "done":
            view.finish(int(payload.get("exit", 0) or 0), payload.get("t"))
        else:
            view.feed(payload)
    return view
