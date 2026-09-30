"""What the user sees while points run (rank 4).

docs/02_Architecture.md §10. The views are fed only by status: ToolState objects that
`execute` updates from the tools' status pipes and log filters. They never look at a process, so
`hep watch` can drive the same views from output/…/status.jsonl in another terminal.

* `LiveView` (rich, on a terminal): each running point under its heading and time so far, one line
  per running tool — tool, phase, a bar, the count, rate and ETA, and the last warning — with each
  finished point printed above it.
* `PlainView` (a pipe, a log file, or `--plain`): one line per event of note, and a progress line
  every few seconds.

**A view never blocks the run.** The supervisor calls the view from its poll loop, so a view that
waits on the terminal stops the supervision: on 2026-09-29 a terminal tab that stopped reading
(paused, or Ctrl-S) held rich's refresh thread in a tty write, the supervisor waited on the
console's lock, and the run froze for hours with its tools already exited (V32). So everything a
view prints goes through `_Screen`, one background thread: the calls the supervisor makes only
queue a line or replace the latest frame, and a blocked terminal stops the display, never the run.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import time
from pathlib import Path

from .status import ToolState, apply


def _count(value) -> str:
    if value is None:
        return "?"
    return f"{value / 1e6:.2f}M" if value >= 1e6 else f"{value / 1e3:.1f}k" if value >= 1e4 else str(value)


def duration(seconds: float) -> str:
    """'42.3s', '4min 12s', '2h 58min 7s': how long a point or a tool took."""
    if seconds < 59.95:
        return f"{seconds:.1f}s"
    hours, rest = divmod(round(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}h {minutes}min {secs}s" if hours else f"{minutes}min {secs}s"


def clock(seconds: float) -> str:
    """'00:42', '49:11', '09:47:17', '103:02:09': a running point's time so far, or an ETA; the hours
    only once there are some."""
    hours, rest = divmod(int(max(0.0, seconds)), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _eta(state) -> str:
    if state.done and state.total and state.rate:
        return clock((state.total - state.done) / state.rate)
    return ""


def progress_text(state) -> str:
    parts = [f"{state.tag}"]
    if state.phase:
        parts.append(state.phase)
    if state.done is not None:
        parts.append(f"{_count(state.done)}/{_count(state.total)}" if state.total else _count(state.done))
    if state.rate:
        parts.append(f"{state.rate:,.0f}/s")
    if _eta(state):
        parts.append(f"ETA {_eta(state)}")
    return " ".join(parts)


class _Screen:
    """The one thread that talks to the terminal. `line()` queues a line and `frame()` replaces the
    latest live frame; neither waits. `close()` flushes for at most `timeout` seconds: a terminal
    that has stopped reading cannot keep the process from ending (the journal has everything)."""

    def __init__(self, write, update=None, start=None, stop=None):
        self._write, self._update, self._start, self._stop_live = write, update, start, stop
        self._lines: queue.SimpleQueue = queue.SimpleQueue()
        self._frame = None
        self._wake = threading.Event()
        self._closing = False
        self._broken = False                     # the stream went away (a closed pipe): stop writing
        self._queued = self._done = 0            # lines queued (the caller) and written (the thread)
        self._thread = threading.Thread(target=self._loop, name="hep-view", daemon=True)
        self._thread.start()

    def line(self, text: str) -> None:
        self._queued += 1
        self._lines.put(text)
        self._wake.set()

    def drain(self, timeout: float = 3.0) -> bool:
        """Wait until every queued line is written (tests, and anything reading the stream after)."""
        until = time.monotonic() + timeout
        while self._done < self._queued and time.monotonic() < until and self._thread.is_alive():
            self._wake.set()
            time.sleep(0.01)
        return self._done >= self._queued

    def frame(self, renderable) -> None:
        self._frame = renderable
        self._wake.set()

    def _call(self, function, *args) -> None:
        if function is None or self._broken:
            return
        try:
            function(*args)
        except (OSError, ValueError):
            self._broken = True

    def _loop(self) -> None:
        self._call(self._start)
        while True:
            self._wake.wait(0.5)
            self._wake.clear()
            while True:
                try:
                    text = self._lines.get_nowait()
                except queue.Empty:
                    break
                self._call(self._write, text)
                self._done += 1
            latest, self._frame = self._frame, None
            if latest is not None:
                self._call(self._update, latest)
            if self._closing and self._lines.empty():
                self._call(self._stop_live)
                return

    def close(self, timeout: float = 3.0) -> None:
        self._closing = True
        self._wake.set()
        self._thread.join(timeout)


class _Point:
    """One running point's part of a view: its heading, when it started, the lines its block will
    carry, and its tools (for the live table)."""

    def __init__(self, heading: str):
        self.heading = heading
        self.started = time.monotonic()
        self.notes: list[str] = []
        self.failed: list[str] = []
        self.states: list[ToolState] = []
        self.last = 0.0                              # the plain view's last progress line


class _PointSink:
    """A view as one point's executor sees it (V36): every call goes to the view, and a note
    carries the point it is about, since several points may be running at once."""

    def __init__(self, view, name: str):
        self._view, self._name = view, name

    def note(self, text: str) -> None:
        self._view.note(text, point=self._name)

    def __getattr__(self, attribute):
        return getattr(self._view, attribute)


class PlainView:
    """One block per point, printed when it ends: its heading with the verdict and wall time, then
    only what needs saying (a failed tool, a prepare step) and where the results are:

        ── point 2/4: NNPDF23lo ── ok after 1min 12s
           done → results/PhotoProduction/zeus/default/NNPDF23lo

    While a point runs, a progress line every few seconds (the live view draws a table instead).
    Several points may run at once (parallelism, V36): each keeps its own part of the view, a block
    is printed whole when its point ends, and the executors of the points call in from their own
    threads, so the parts are kept under one lock."""

    def __init__(self, stream=None, every: float = 5.0):
        self.stream = stream or sys.stdout
        self.every = every
        self.screen = self._screen()
        self.total = 0
        self.number = 0
        self.points: dict[str, _Point] = {}
        self._lock = threading.RLock()
        self._watch_last = 0.0

    def _screen(self) -> _Screen:
        def write(text: str) -> None:
            print(text, file=self.stream, flush=True)
        return _Screen(write)

    def for_point(self, plan) -> _PointSink:
        """The sink one point's executor is given."""
        return _PointSink(self, plan.point.name)

    def say(self, text: str) -> None:
        self.screen.line(text)

    def flush(self) -> None:
        self.screen.drain()

    def begin(self, count: int, title: str = "") -> None:
        self.total = count
        if title:
            self.say(title)

    def end(self) -> None:
        self.screen.close()

    def heading(self, plan, bold: bool = False) -> str:
        """'── point 3/16: <name>', '── combined: <name>' for a merged group (V35), or '── post (after
        every point)' for the post stage (index 0). Points are numbered in the order they start."""
        if plan.point.stage == "combined":
            return f"── combined: {f'[bold]{plan.point.name}[/bold]' if bold else plan.point.name}"
        if plan.point.index == 0:
            return "── post (after every point)"
        if plan.point.index < 0:
            return "── pre (before every point)"
        with self._lock:
            self.number += 1
            number = self.number
        name = f"[bold]{plan.point.name}[/bold]" if bold else plan.point.name
        return f"── point {number}/{self.total}: {name}"

    def _part(self, name: str | None) -> _Point | None:
        """A point's part; with no name, the one point running (a sequential caller's note)."""
        if name is not None:
            return self.points.get(name)
        return next(reversed(self.points.values()), None)

    def point_started(self, plan) -> None:
        heading = self.heading(plan, bold=isinstance(self, LiveView))
        with self._lock:
            self.points[plan.point.name] = _Point(heading)

    def tool_started(self, state) -> None:
        with self._lock:
            part = self._part(state.point)
            if part is not None:
                part.states.append(state)

    def note(self, text: str, point: str | None = None) -> None:
        """A line for the point's block (a prepare step's verdict), printed when it ends."""
        with self._lock:
            part = self._part(point)
            if part is not None:
                part.notes.append(text)

    def tick(self, states) -> None:
        now = time.monotonic()
        by_point: dict[str, list] = {}
        for s in states:
            if s.running:
                by_point.setdefault(s.point, []).append(s)
        watch_due = None                                 # hep watch has no parts: one clock for all
        for point, running in by_point.items():
            with self._lock:
                part = self.points.get(point)
                if part is not None:
                    if now - part.last < self.every:
                        continue
                    part.last = now
                else:
                    if watch_due is None:
                        watch_due = now - self._watch_last >= self.every
                        if watch_due:
                            self._watch_last = now
                    if not watch_due:
                        continue
            line = " | ".join(progress_text(s) if (s.phase or s.done is not None) else f"{s.tag} … {s.last_line[:60]}"
                              for s in running)
            self.say(f"   [{point}] {line}" if point else f"   {line}")

    def tool_finished(self, state, result) -> None:
        verdict = "ok" if result.exit == 0 else f"exit {result.exit}"
        if state.tag.endswith(":prepare"):
            self.note(f"   {state.tag}: {verdict} after {duration(result.seconds)}", point=state.point)
        elif result.exit != 0:
            extra = f"  ({state.error})" if state.error else ""
            with self._lock:
                part = self._part(state.point)
                if part is not None:
                    part.failed.append(f"   {state.tag}: {verdict} after {duration(result.seconds)}{extra}")

    def block(self, heading: str, verdict: str, seconds: float, lines: list[str]) -> None:
        text = [f"{heading} ── {verdict} after {duration(seconds)}", *lines]
        with self._lock:                            # a block's lines stay together
            for line in text:
                self.say(line)

    def point_finished(self, plan, result) -> None:
        with self._lock:
            part = self.points.pop(plan.point.name, None) or _Point(self.heading(plan))
        seconds = time.monotonic() - part.started
        if result.ok:
            self.block(part.heading, "ok", seconds, [*part.notes, f"   done → {plan.res}"])
        elif result.stopped:
            self.block(part.heading, "stopped", seconds,
                       [*part.notes, *part.failed, "   partial outputs keep their .partial names"])
        else:
            blame = f" [{result.cause}]" if result.cause else ""
            self.block(part.heading, f"FAILED{blame}", seconds, [*part.notes, *part.failed, f"   {result.message}"])

    def skipped(self, plan) -> None:
        self.say(f"{self.heading(plan)}: complete, skipped (--rerun to run it again)")


class LiveView(PlainView):
    """The rich version: the same blocks, and under them each running point: a blank line, its
    heading and time so far, then its running tools, one line each:

        ── point 3/4: MSTW08lo ── ok after 9h 12min 4s
           done → results/PhotoProduction/zeus/default/MSTW08lo

        point 4/4: PDF4LHC21 · 01:03:17
           pythia   generating ━━━━━━━━━━━━━━━━━━━━━━━━ 1.70M/10.00M 2,812/s 49:11
           rivet.12 analysing  ⠸                        1.70M

    The columns line up across points. `hep watch` has no points' parts: its tools, each named by
    its point."""

    SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    BAR = 24

    def __init__(self):
        from rich.console import Console
        from rich.live import Live
        self.console = Console()
        self.live = Live(console=self.console, refresh_per_second=4, transient=True)
        super().__init__()
        self.frame = 0

    def _screen(self) -> _Screen:            # rich's Live starts, prints, redraws and stops on the thread
        return _Screen(lambda text: self.console.print(text, highlight=False),
                       update=self.live.update, start=self.live.start, stop=self.live.stop)

    def begin(self, count: int, title: str = "") -> None:
        self.total = count
        if title:
            self.say(f"[bold]{title}[/bold]")

    def block(self, heading: str, verdict: str, seconds: float, lines: list[str]) -> None:
        colour = "green" if verdict == "ok" else "yellow" if verdict == "stopped" else "red"
        text = [f"{heading} ── [{colour}]{verdict}[/{colour}] after {duration(seconds)}", *lines]
        with self._lock:
            for line in text:
                self.say(line)

    def tick(self, states) -> None:
        with self._lock:
            self.frame += 1
            self.screen.frame(self.render(states))

    def _rows(self, states, named: bool) -> list[list]:
        """A line per running tool: [point,] tool, phase, bar, count, rate and ETA, the last warning."""
        from rich.progress_bar import ProgressBar
        rows = []
        for s in states:
            if not s.running:
                continue
            spinner = self.SPIN[self.frame % len(self.SPIN)]
            if s.done is not None and s.total:
                bar = ProgressBar(total=s.total, completed=min(s.done, s.total), width=self.BAR)
                count = f"{_count(s.done)}/{_count(s.total)}"
            elif s.done is not None:
                bar, count = spinner, _count(s.done)
            else:
                bar, count = spinner, ""
            rate = f"{s.rate:,.0f}/s" if s.rate else ""
            note = f"[yellow]{s.warning[:50]}[/yellow]" if s.warning else f"[dim]{(s.last_line if s.done is None else '')[:50]}[/dim]"
            row = [f"[bold]{s.tag}[/bold]", s.phase or "", bar, count, f"{rate} {_eta(s)}".strip(), note]
            rows.append([f"[cyan]{s.point}[/cyan]", *row] if named else row)
        return rows

    def _width(self, cell) -> int:
        from rich.text import Text
        if not isinstance(cell, str):
            return self.BAR
        try:
            return Text.from_markup(cell).cell_len
        except Exception:                        # a tool's text that looks like markup
            return len(cell)

    def render(self, states):
        from rich.console import Group
        from rich.table import Table
        from rich.text import Text
        now = time.monotonic()
        if self.points:                          # the executors' points: each keeps its own tools
            sections = [(f"{part.heading.replace('── ', '')} · {clock(now - part.started)}",
                         self._rows(part.states, named=False)) for part in list(self.points.values())]
        else:                                    # hep watch: every running tool it has read
            sections = [("", self._rows(states, named=True))]
        widths: list[int] = []
        for _, rows in sections:
            for row in rows:
                for i, cell in enumerate(row[:-1]):      # the last column needs no width
                    if i == len(widths):
                        widths.append(0)
                    widths[i] = max(widths[i], self._width(cell))
        shown = []
        for heading, rows in sections:
            if not heading and not rows:
                continue
            shown.append(Text(""))               # a line between the finished blocks and this point
            if heading:
                shown.append(Text.from_markup(heading))
            if rows:
                table = Table.grid(padding=(0, 1))
                for row in rows:                 # padded here: rich counts padding into min_width
                    cells = [cell + " " * (width - self._width(cell)) if isinstance(cell, str) else cell
                             for cell, width in zip(row, widths)] + row[len(widths):]
                    if heading:                  # the tools sit under their point, like a block's lines
                        cells[0] = "   " + cells[0]
                    table.add_row(*cells)
                shown.append(table)
        return Group(*shown)


def view(plain: bool = False) -> PlainView:
    """The live view on a terminal (when rich is there), plain lines otherwise."""
    if not plain and sys.stdout.isatty():
        try:
            return LiveView()
        except ImportError:
            pass
    return PlainView()


# ── hep watch: the same views, driven by status.jsonl ──────────────────────────────────────────

def _latest_run(journal: Path) -> int:
    """The byte offset of the latest run's first record: the journal is appended across runs."""
    offset = start = 0
    if journal.exists():
        with open(journal, "rb") as handle:
            for raw in handle:
                if b'"k": "run"' in raw and b'"state": "started"' in raw:
                    start = offset
                offset += len(raw)
    return start


def follow(journal: Path, *, plain: bool = False, idle_exit: float = 0.0) -> int:
    """Tail a run's status.jsonl until the run says it finished (or `idle_exit` seconds of silence)."""
    shown = view(plain)
    states: dict[tuple[str, str], ToolState] = {}
    blocks: dict[str, list] = {}                    # point → [heading, started, lines]
    offset = _latest_run(journal)
    title_done = False
    last = time.monotonic()
    try:
        while True:
            size = journal.stat().st_size if journal.exists() else 0
            if size > offset:
                with open(journal, encoding="utf-8") as handle:
                    handle.seek(offset)
                    chunk = handle.read()
                offset = size
                last = time.monotonic()
                for line in chunk.splitlines():
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    kind, point, tag = message.get("k"), message.get("point", ""), message.get("tool", "")
                    if kind == "run":
                        if message.get("state") == "started":
                            shown.begin(message.get("points", 0), f"watching {message.get('title', journal.parent)}")
                            title_done = True
                        elif message.get("state") == "finished":
                            shown.say(f"run finished: {message.get('verdict', '')}")
                            return 0
                        continue
                    if not title_done:
                        shown.begin(0, f"watching {journal.parent}")
                        title_done = True
                    if kind == "point":
                        if message.get("state") == "started":
                            index = message.get("index", 0)
                            heading = (f"── combined: {point}" if message.get("stage") == "combined" else
                                       "── post (after every point)" if index == 0 else "── pre (before every point)"
                                       if index < 0 else f"── point {index}/{shown.total or '?'}: {point}")
                            blocks[point] = [heading, message.get("t", time.time()), []]
                        else:
                            heading, started, lines = blocks.pop(point, [f"── {point}", message.get("t", time.time()), []])
                            verdict = {"done": "ok"}.get(message.get("state"), message.get("state", "?"))
                            if verdict == "failed" and message.get("cause"):
                                verdict = f"FAILED [{message['cause']}]"
                            extra = [f"   {message['msg']}"] if message.get("msg") and verdict != "ok" else []
                            shown.block(heading, verdict, message.get("t", time.time()) - started, lines + extra)
                        continue
                    state = states.setdefault((point, tag), ToolState(point=point, tag=tag))
                    if kind == "exit":
                        state.running, state.exit = False, message.get("code")
                        verdict = "ok" if message.get("code") == 0 else f"exit {message.get('code')}"
                        if message.get("code") != 0 or tag.endswith(":prepare"):
                            blocks.get(point, [None, None, []])[2].append(
                                f"   {tag}: {verdict} after {duration(message.get('seconds', 0))}")
                        continue
                    apply(state, message)
            shown.tick([s for s in states.values() if s.running])
            if idle_exit and time.monotonic() - last > idle_exit:
                shown.say(f"no status for {idle_exit:.0f} s; leaving")
                return 0
            time.sleep(0.25)
    except KeyboardInterrupt:
        return 0
    finally:
        shown.end()
