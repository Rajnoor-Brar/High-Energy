"""Plain lines: what a log, a pipe, CI or a remote session sees (06 §2).

```
12:40:03 [2/4 eic_5x41_em_NNLO] generate  start  hep-run (20 threads, serial)
12:40:33 [2/4 eic_5x41_em_NNLO] generate  35211/1000000  3.5%  1.17k/s  eta 13m44s
12:41:07 [2/4 eic_5x41_em_NNLO] WARN pythia SpaceShower::pT2nearThreshold: stuck in loop
12:54:10 [2/4 eic_5x41_em_NNLO] done      σ=1.829e+04 pb ±0.3%  14m07s  → …/analysis.yoda
```

Three rules make these lines readable months later in a CI log:

* **Every line stands alone.** Time, point, stage: no line depends on what came before, because a log
  gets grepped, not read.
* **Progress is rate-limited, and the limit is computed from the totals.** The legacy `Monitor` fixed
  its interval before it knew how long the run was, so a short run printed once and a long one printed
  thousands of times. Here the interval is chosen once the first `progress` message says how many
  events there are: about twenty lines over the run, never more often than `floor`, never quieter than
  `plain_every` (default 30 s).
* **A warning is printed once**, with a count when it repeats — the same de-duplication the dashboard
  does, so the two reports agree.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any, TextIO

from . import theme
from .model import FINISHED, LogEntry, PointView, RunView


@dataclass
class PlainRenderer:
    """Turns view changes into lines. Give it a stream; it never touches a terminal."""

    view: RunView
    stream: TextIO = field(default=None)            # type: ignore[assignment]
    plain_every: float = 30.0
    floor: float = 1.0
    _last_progress: dict[str, float] = field(default_factory=dict, repr=False)
    _interval: dict[str, float] = field(default_factory=dict, repr=False)
    _seen_logs: dict[tuple, int] = field(default_factory=dict, repr=False)
    _started: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if self.stream is None:
            self.stream = sys.stderr

    # ── one line ─────────────────────────────────────────────────────────────

    def line(self, point: PointView | None, text: str, *, when: float | None = None) -> None:
        stamp = theme.clock(when or time.time())
        where = f"[{point.index}/{point.total_points} {point.name}] " if point is not None else ""
        self.stream.write(theme.t(f"{stamp} {where}{text}") + "\n")
        self.stream.flush()

    # ── events worth a line ──────────────────────────────────────────────────

    def run_started(self) -> None:
        parts = [self.view.command or "hep run"]
        if self.view.project:
            parts.append(self.view.project)
        if self.view.git:
            parts.append(self.view.git)
        self.line(None, "start  " + theme.t(" · ").join(parts), when=self.view.started)
        if self.view.points:
            self.line(None, f"points {len(self.view.points)}: "
                            + ", ".join(point.name for point in self.view.points))

    def point_started(self, point: PointView) -> None:
        self._started.add(point.name)
        self.line(point, "start", when=point.started)

    def stage_started(self, point: PointView, stage_name: str) -> None:
        stage = point.stage(stage_name)
        detail = []
        if stage.threads:
            detail.append(f"{stage.threads} threads")
        if stage.mode:
            detail.append(stage.mode)
        suffix = f" ({', '.join(detail)})" if detail else ""
        self.line(point, f"{stage_name}  start{suffix}")

    def progress(self, point: PointView, stage_name: str, *, force: bool = False) -> None:
        """A progress line, if enough time has passed for this stage."""
        stage = point.stage(stage_name)
        key = f"{point.name}/{stage_name}"
        now = time.time()
        # Computed *after* the totals are known — the legacy bar-interval defect (06 §2).
        interval = self._interval.get(key)
        if interval is None or stage.rate:
            interval = theme.progress_interval(stage.total, stage.rate,
                                               ceiling=self.plain_every, floor=self.floor)
            self._interval[key] = interval
        if not force and now - self._last_progress.get(key, 0.0) < interval:
            return
        self._last_progress[key] = now
        remaining = theme.eta(stage.done, stage.total, stage.rate)
        self.line(point, f"{stage_name}  {stage.done}/{stage.total}  "
                         f"{theme.percent(stage.done, stage.total)}  {theme.rate(stage.rate)}  "
                         f"eta {theme.duration(remaining)}")

    def log(self, point: PointView | None, entry: LogEntry) -> None:
        """A warning or an error, once; repeats are counted and only shown as they grow."""
        key = (point.name if point else "", entry.key)
        seen = self._seen_logs.get(key, 0)
        if seen and entry.count <= seen:
            return
        self._seen_logs[key] = entry.count
        repeat = theme.t(f"  ×{entry.count}") if entry.count > 1 else ""
        self.line(point, f"{entry.level.upper()} {entry.source} {entry.message}{repeat}",
                  when=entry.time)

    def point_finished(self, point: PointView) -> None:
        if point.state == "skipped":
            self.line(point, f"skipped  {point.reason or 'name, hash and result all match'}",
                      when=point.finished)
            return
        if point.state == "failed":
            self.line(point, f"FAILED  exit {point.exit_code}  {point.reason}".rstrip(),
                      when=point.finished)
            return
        bits = [theme.sigma(point.xsec_pb, point.xsec_err_pb)] if point.xsec_pb else []
        bits.append(theme.duration(point.elapsed()))
        if point.events:
            bits.insert(0, f"{theme.count(point.events)} ev")
        if point.warning_count:
            bits.append(f"{point.warning_count} warnings")
        head = "stopped" if point.state == "stopped" else "done   "
        tail = f"  → {point.outputs[0]}" if point.outputs else ""
        self.line(point, f"{head}  " + "  ".join(bits) + tail, when=point.finished)

    def run_finished(self) -> None:
        done = sum(1 for point in self.view.points if point.state == "done")
        failed = len(self.view.failed_points)
        skipped = sum(1 for point in self.view.points if point.state == "skipped")
        parts = [f"{done} done"]
        if skipped:
            parts.append(f"{skipped} skipped")
        if failed:
            parts.append(f"{failed} failed")
        parts.append(theme.duration(self.view.elapsed()))
        self.line(None, "end    " + "  ".join(parts), when=self.view.finished)

    # ── the polling entry point ──────────────────────────────────────────────

    def refresh(self) -> None:
        """Print whatever has changed since the last call. Safe to call as often as you like."""
        for point in self.view.points:
            if point.state == "queued":
                continue
            if point.name not in self._started:
                self.point_started(point)
            for name, stage in point.stages.items():
                if f"{point.name}/{name}" not in self._last_progress and (stage.total or stage.phase):
                    self.stage_started(point, name)
                    self._last_progress[f"{point.name}/{name}"] = 0.0
                if stage.total:
                    self.progress(point, name)
            for entry in point.logs:
                self.log(point, entry)
        for entry in self.view._run_logs:
            self.log(None, entry)


def render_lines(view: RunView, *, plain_every: float = 30.0) -> list[str]:
    """Every line a finished run would have printed, for tests and for `hep watch --plain` on a
    journal that has already ended."""
    import io

    stream = io.StringIO()
    renderer = PlainRenderer(view=view, stream=stream, plain_every=plain_every)
    renderer.run_started()
    for point in view.points:
        if point.state == "queued":
            continue
        renderer.point_started(point)
        for name, stage in point.stages.items():
            renderer.stage_started(point, name)
            if stage.total:
                renderer.progress(point, name, force=True)
        for entry in point.logs:
            renderer.log(point, entry)
        if point.state in FINISHED:
            renderer.point_finished(point)
    if view.finished:
        renderer.run_finished()
    return stream.getvalue().splitlines()
