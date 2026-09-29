"""What the user sees while points run (rank 4).

docs/02_Architecture.md §10. The views are fed only by status: ToolState objects that
`execute` updates from the tools' status pipes and log filters. They never look at a process, so
`hep watch` can drive the same views from output/…/status.jsonl in another terminal.

* `LiveView` (rich, on a terminal): one line per running tool — point, tool, phase, a bar, the
  count, rate and ETA, and the last warning — with each finished point printed above it.
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


def _eta(state) -> str:
    if state.done and state.total and state.rate:
        left = max(0.0, (state.total - state.done) / state.rate)
        return f"{int(left // 60)}:{int(left % 60):02d}"
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


class PlainView:
    """One block per point, printed when it ends: its heading with the verdict and wall time, then
    only what needs saying (a failed tool, a prepare step) and where the results are:

        ── point 2/4: NNPDF23lo ── ok after 71.8 s
           done → results/PhotoProduction/zeus/default/NNPDF23lo

    While a point runs, a progress line every few seconds (the live view draws a table instead)."""

    def __init__(self, stream=None, every: float = 5.0):
        self.stream = stream or sys.stdout
        self.every = every
        self.screen = self._screen()
        self.last = 0.0
        self.total = 0
        self.number = 0
        self._heading = ""
        self._started = time.monotonic()
        self._notes: list[str] = []
        self._failed: list[str] = []

    def _screen(self) -> _Screen:
        def write(text: str) -> None:
            print(text, file=self.stream, flush=True)
        return _Screen(write)

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
        every point)' for the post stage (index 0)."""
        if plan.point.stage == "combined":
            return f"── combined: {f'[bold]{plan.point.name}[/bold]' if bold else plan.point.name}"
        if plan.point.index == 0:
            return "── post (after every point)"
        if plan.point.index < 0:
            return "── pre (before every point)"
        self.number += 1
        name = f"[bold]{plan.point.name}[/bold]" if bold else plan.point.name
        return f"── point {self.number}/{self.total}: {name}"

    def point_started(self, plan) -> None:
        self._heading = self.heading(plan, bold=isinstance(self, LiveView))
        self._started = time.monotonic()
        self._notes, self._failed = [], []

    def tool_started(self, state) -> None:
        pass

    def note(self, text: str) -> None:
        """A line for the point's block (a prepare step's verdict), printed when it ends."""
        self._notes.append(text)

    def tick(self, states) -> None:
        now = time.monotonic()
        if now - self.last < self.every:
            return
        self.last = now
        line = " | ".join(progress_text(s) if (s.phase or s.done is not None) else f"{s.tag} … {s.last_line[:60]}"
                          for s in states if s.running)
        if line:
            point = next((s.point for s in states if s.running), "")
            self.say(f"   [{point}] {line}" if point else f"   {line}")

    def tool_finished(self, state, result) -> None:
        verdict = "ok" if result.exit == 0 else f"exit {result.exit}"
        if state.tag.endswith(":prepare"):
            self.note(f"   {state.tag}: {verdict} after {result.seconds:.1f} s")
        elif result.exit != 0:
            extra = f"  ({state.error})" if state.error else ""
            self._failed.append(f"   {state.tag}: {verdict} after {result.seconds:.1f} s{extra}")

    def block(self, heading: str, verdict: str, seconds: float, lines: list[str]) -> None:
        self.say(f"{heading} ── {verdict} after {seconds:.1f} s")
        for line in lines:
            self.say(line)

    def point_finished(self, plan, result) -> None:
        seconds = time.monotonic() - self._started
        if result.ok:
            self.block(self._heading, "ok", seconds, [*self._notes, f"   done → {plan.res}"])
        elif result.stopped:
            self.block(self._heading, "stopped", seconds,
                       [*self._notes, *self._failed, "   partial outputs keep their .partial names"])
        else:
            blame = f" [{result.cause}]" if result.cause else ""
            self.block(self._heading, f"FAILED{blame}", seconds, [*self._notes, *self._failed, f"   {result.message}"])

    def skipped(self, plan) -> None:
        self.say(f"{self.heading(plan)}: complete, skipped (--rerun to run it again)")


class LiveView(PlainView):
    """The rich version: the same blocks, and a live table of the running tools."""

    SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self):
        from rich.console import Console
        from rich.live import Live
        self.console = Console()
        self.live = Live(console=self.console, refresh_per_second=4, transient=True)
        super().__init__()
        self.states: list[ToolState] = []
        self.point_name = ""
        self.started = time.monotonic()
        self.frame = 0

    def _screen(self) -> _Screen:            # rich's Live starts, prints, redraws and stops on the thread
        return _Screen(lambda text: self.console.print(text, highlight=False),
                       update=self.live.update, start=self.live.start, stop=self.live.stop)

    def begin(self, count: int, title: str = "") -> None:
        self.total = count
        if title:
            self.say(f"[bold]{title}[/bold]")

    def point_started(self, plan) -> None:
        super().point_started(plan)
        self.point_name = plan.point.name
        self.states = []

    def block(self, heading: str, verdict: str, seconds: float, lines: list[str]) -> None:
        colour = "green" if verdict == "ok" else "yellow" if verdict == "stopped" else "red"
        self.say(f"{heading} ── [{colour}]{verdict}[/{colour}] after {seconds:.1f} s")
        for line in lines:
            self.say(line)

    def tool_started(self, state) -> None:
        self.states.append(state)

    def tick(self, states) -> None:
        self.frame += 1
        self.screen.frame(self.render(states or self.states))

    def render(self, states):
        from rich.progress_bar import ProgressBar
        from rich.table import Table
        table = Table.grid(padding=(0, 1))
        for _ in range(7):
            table.add_column()
        for s in states:
            if not s.running:
                continue
            spinner = self.SPIN[self.frame % len(self.SPIN)]
            if s.done is not None and s.total:
                bar = ProgressBar(total=s.total, completed=min(s.done, s.total), width=24)
                count = f"{_count(s.done)}/{_count(s.total)}"
            elif s.done is not None:
                bar, count = spinner, _count(s.done)
            else:
                bar, count = spinner, ""
            rate = f"{s.rate:,.0f}/s" if s.rate else ""
            note = f"[yellow]{s.warning[:50]}[/yellow]" if s.warning else f"[dim]{(s.last_line if s.done is None else '')[:50]}[/dim]"
            table.add_row(f"[cyan]{s.point}[/cyan]", f"[bold]{s.tag}[/bold]", s.phase or "", bar, count,
                          f"{rate} {_eta(s)}".strip(), note)
        elapsed = time.monotonic() - self.started
        table.add_row("", f"[dim]{self._heading.replace('── ', '')} · {int(elapsed // 60)}:{int(elapsed % 60):02d}[/dim]",
                      "", "", "", "", "")
        return table


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
                                f"   {tag}: {verdict} after {message.get('seconds', 0):.1f} s")
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
