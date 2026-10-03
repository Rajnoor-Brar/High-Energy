"""What the user sees while points run (rank 4).

docs/02_Architecture.md §10, V72. A view hears the run's events (events.py) and nothing else: one
reducer, `State`, turns them into points and their tools, and the views render it, the same whether the
events come from the run in this process, from its watch socket (`hep watch`), or from a --journal file.

* `LiveView` (rich, on a terminal): each running point under its heading and time so far, one line
  per running tool — tool, phase, a bar, the count, rate and ETA, and the last warning — with each
  finished point printed above it.
* `PlainView` (a pipe, a log file, or `--plain`): one block per point when it ends, and a progress line
  every few seconds while it runs.

**A view never blocks the run.** Everything a view prints goes through `_Screen`, one background thread:
an event only queues a line, and the screen's own clock redraws, so a terminal that stops reading
(paused, Ctrl-S) stops the display, never the run (V32).
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


# ── the reducer ───────────────────────────────────────────────────────────────────────────────

class _Point:
    """One running point: its heading (prefix and name, so a view can embolden the name), when it
    started, the lines its block will carry, and its tools."""

    def __init__(self, prefix: str, name: str, started: float):
        self.prefix, self.name, self.started = prefix, name, started
        self.notes: list[str] = []
        self.failed: list[str] = []
        self.states: list[ToolState] = []
        self.last = 0.0                              # the plain view's last progress line

    @property
    def heading(self) -> str:
        return self.prefix + self.name


class State:
    """Events in, what to print out: `apply` returns ("title", header, title), ("say", text) and
    ("block", point, verdict, seconds, lines) items. Points are numbered in the order they start."""

    def __init__(self):
        self.total = 0
        self.number = 0
        self.points: dict[str, _Point] = {}

    def _heading(self, event: dict) -> tuple[str, str]:
        name, index = event["point"], event.get("index", 1)
        if event.get("stage") == "combined":
            return "── combined: ", name
        if index == 0:
            return "── post (after every point)", ""
        if index < 0:
            return "── pre (before every point)", ""
        self.number += 1
        return f"── point {self.number}/{self.total or '?'}: ", name

    def _state(self, point: str, tag: str) -> ToolState | None:
        part = self.points.get(point)
        if part is None:
            return None
        found = next((s for s in part.states if s.tag == tag), None)
        if found is None:
            found = ToolState(point=point, tag=tag)
            part.states.append(found)
        return found

    def apply(self, event: dict) -> list[tuple]:
        kind, point, tag = event.get("k"), event.get("point", ""), event.get("tool", "")
        if kind == "run":
            if event.get("state") == "started":
                self.total, self.number, self.points = event.get("points", 0), 0, {}
                return [("title", event.get("header", ""), event.get("title", ""))]
            return []
        if kind == "say":
            return [("say", event.get("msg", ""))]
        if kind == "point":
            state = event.get("state")
            if state == "started":
                prefix, name = self._heading(event)
                self.points[point] = _Point(prefix, name, event.get("t", time.time()))
                return []
            if state == "skipped":
                prefix, name = self._heading(event)
                return [("say", f"{prefix}{name}: complete, skipped (--rerun to run it again)")]
            part = self.points.pop(point, None) or _Point("── ", point, event.get("t", time.time()))
            seconds = event.get("t", time.time()) - part.started
            if state == "done":
                return [("block", part, "ok", seconds, [*part.notes, f"   done → {event.get('res', '')}"])]
            if state == "stopped":
                return [("block", part, "stopped", seconds, [*part.notes, *part.failed,
                                                             "   partial outputs keep their .partial names"])]
            blame = f" [{event['cause']}]" if event.get("cause") else ""
            return [("block", part, f"FAILED{blame}", seconds, [*part.notes, *part.failed, f"   {event.get('msg', '')}"])]
        part = self.points.get(point)
        if kind == "note":
            if part is not None:
                part.notes.append(event.get("msg", ""))
            return []
        if kind == "tool":
            self._state(point, tag)
            return []
        tool = self._state(point, tag)
        if tool is None:
            return []
        if kind == "exit":
            tool.running, tool.exit = False, event.get("code")
            verdict = "ok" if event.get("code") == 0 else f"exit {event.get('code')}"
            if tag.endswith(":prepare"):
                part.notes.append(f"   {tag}: {verdict} after {duration(event.get('seconds', 0))}")
            elif event.get("code") != 0:
                extra = f"  ({tool.error})" if tool.error else ""
                part.failed.append(f"   {tag}: {verdict} after {duration(event.get('seconds', 0))}{extra}")
            return []
        apply(tool, event)
        return []

    def running(self) -> list[_Point]:
        return list(self.points.values())


# ── the screen ────────────────────────────────────────────────────────────────────────────────

class _Screen:
    """The one thread that talks to the terminal. `line()` queues a line and `frame()` replaces the
    latest live frame; neither waits. `tick`, if given, is called on the thread every half second.
    `close()` flushes for at most `timeout` seconds: a terminal that has stopped reading cannot keep the
    process from ending."""

    def __init__(self, write, update=None, start=None, stop=None, tick=None):
        self._write, self._update, self._start, self._stop_live, self._tick = write, update, start, stop, tick
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
            if self._tick is not None and not self._closing:
                try:
                    self._tick()
                except Exception:                # a drawing error never stops the screen
                    pass
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


# ── the views ─────────────────────────────────────────────────────────────────────────────────

class PlainView:
    """One block per point, printed when it ends: its heading with the verdict and wall time, then
    only what needs saying (a failed tool, a prepare step) and where the results are:

        ── point 2/4: NNPDF23lo ── ok after 1min 12s
           done → results/PhotoProduction/zeus/default/NNPDF23lo

    While a point runs, a progress line every few seconds (the live view draws a table instead)."""

    bold = False

    def __init__(self, stream=None, every: float = 5.0):
        self.stream = stream or sys.stdout
        self.every = every
        self.state = State()
        self._lock = threading.RLock()
        self.screen = self._screen()

    def _screen(self) -> _Screen:
        def write(text: str) -> None:
            print(text, file=self.stream, flush=True)
        return _Screen(write, tick=self._tick)

    def event(self, event: dict) -> None:
        """A bus subscriber: never blocks (the screen thread prints)."""
        with self._lock:
            for item in self.state.apply(event):
                self._show(item)

    def say(self, text: str) -> None:
        self.screen.line(text)

    def flush(self) -> None:
        self.screen.drain()

    def end(self) -> None:
        self.screen.close()

    def _show(self, item: tuple) -> None:
        if item[0] == "title":
            for line in item[1:]:
                if line:
                    self.say(self._title(line))
        elif item[0] == "say":
            self.say(item[1])
        else:
            _, part, verdict, seconds, lines = item
            for line in self._block(part, verdict, seconds, lines):
                self.say(line)

    def _title(self, line: str) -> str:
        return line

    def _block(self, part: _Point, verdict: str, seconds: float, lines: list[str]) -> list[str]:
        return [f"{part.heading} ── {verdict} after {duration(seconds)}", *lines]

    def _tick(self) -> None:
        now = time.monotonic()
        with self._lock:
            for part in self.state.running():
                running = [s for s in part.states if s.running]
                if not running or now - part.last < self.every:
                    continue
                part.last = now
                line = " | ".join(progress_text(s) if (s.phase or s.done is not None) else f"{s.tag} … {s.last_line[:60]}"
                                  for s in running)
                self.say(f"   [{part.name or part.prefix.strip('─ ')}] {line}")


class LiveView(PlainView):
    """The rich version: the same blocks, and under them each running point: a blank line, its
    heading and time so far, then its running tools, one line each:

        ── point 3/4: MSTW08lo ── ok after 9h 12min 4s
           done → results/PhotoProduction/zeus/default/MSTW08lo

        point 4/4: PDF4LHC21 · 01:03:17
           pythia   generating ━━━━━━━━━━━━━━━━━━━━━━━━ 1.70M/10.00M 2,812/s 49:11
           rivet.12 analysing  ⠸                        1.70M

    The columns line up across points."""

    SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    BAR = 24
    bold = True

    def __init__(self):
        from rich.console import Console
        from rich.live import Live
        self.console = Console()
        self.live = Live(console=self.console, refresh_per_second=4, transient=True)
        self.frame = 0
        super().__init__()

    def _screen(self) -> _Screen:            # rich's Live starts, prints, redraws and stops on the thread
        return _Screen(lambda text: self.console.print(text, highlight=False),
                       update=self.live.update, start=self.live.start, stop=self.live.stop, tick=self._tick)

    def _title(self, line: str) -> str:
        from rich.markup import escape
        return f"[bold]{escape(line)}[/bold]"

    def _block(self, part: _Point, verdict: str, seconds: float, lines: list[str]) -> list[str]:
        colour = "green" if verdict == "ok" else "yellow" if verdict == "stopped" else "red"
        heading = part.prefix + (f"[bold]{part.name}[/bold]" if part.name else "")
        return [f"{heading} ── [{colour}]{verdict}[/{colour}] after {duration(seconds)}", *lines]

    def _tick(self) -> None:
        with self._lock:
            self.frame += 1
            self.screen.frame(self.render())

    def _rows(self, states) -> list[list]:
        """A line per running tool: tool, phase, bar, count, rate and ETA, the last warning."""
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
            rows.append([f"[bold]{s.tag}[/bold]", s.phase or "", bar, count, f"{rate} {_eta(s)}".strip(), note])
        return rows

    def _width(self, cell) -> int:
        from rich.text import Text
        if not isinstance(cell, str):
            return self.BAR
        try:
            return Text.from_markup(cell).cell_len
        except Exception:                        # a tool's text that looks like markup
            return len(cell)

    def render(self):
        from rich.console import Group
        from rich.table import Table
        from rich.text import Text
        now = time.time()
        sections = [(f"{part.prefix.replace('── ', '')}{f'[bold]{part.name}[/bold]' if part.name else ''} · "
                     f"{clock(now - part.started)}", self._rows(part.states)) for part in self.state.running()]
        widths: list[int] = []
        for _, rows in sections:
            for row in rows:
                for i, cell in enumerate(row[:-1]):      # the last column needs no width
                    if i == len(widths):
                        widths.append(0)
                    widths[i] = max(widths[i], self._width(cell))
        shown = []
        for heading, rows in sections:
            shown.append(Text(""))               # a line between the finished blocks and this point
            shown.append(Text.from_markup(heading))
            if rows:
                table = Table.grid(padding=(0, 1))
                for row in rows:                 # padded here: rich counts padding into min_width
                    cells = [cell + " " * (width - self._width(cell)) if isinstance(cell, str) else cell
                             for cell, width in zip(row, widths)] + row[len(widths):]
                    cells[0] = "   " + cells[0]  # the tools sit under their point, like a block's lines
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


# ── hep watch ─────────────────────────────────────────────────────────────────────────────────

def follow_events(events, *, plain: bool = False) -> int:
    """Drive a view from an iterator of events (a watch socket's) until it ends."""
    shown = view(plain)
    try:
        for event in events:
            if event.get("k") != "hello":
                shown.event(event)
    except KeyboardInterrupt:
        pass
    except OSError as error:
        shown.say(f"the run's watch socket went away ({error})")
    finally:
        shown.end()
    return 0


def follow_file(journal: Path, *, plain: bool = False, idle_exit: float = 0.0) -> int:
    """`hep watch --file`: a --journal run's status.jsonl, followed until the run says it finished (or
    `idle_exit` seconds of silence). A run of a sweep of runs names the next one's journal when it
    finishes: follow on to it."""
    shown = view(plain)
    offset, last = 0, time.monotonic()
    try:
        while True:
            size = journal.stat().st_size if journal.exists() else 0
            if size < offset:                     # the next run began the file afresh
                offset = 0
            if size > offset:
                with open(journal, encoding="utf-8") as handle:
                    handle.seek(offset)
                    chunk = handle.read()
                complete = chunk[:chunk.rfind("\n") + 1]
                offset += len(complete.encode("utf-8"))
                last = time.monotonic()
                for line in complete.splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    shown.event(event)
                    if event.get("k") == "run" and event.get("state") == "finished":
                        if not event.get("next"):
                            return 0
                        journal, offset = Path(event["next"]), 0
                        break
            if idle_exit and time.monotonic() - last > idle_exit:
                shown.say(f"no status for {idle_exit:.0f} s; leaving")
                return 0
            time.sleep(0.25)
    except KeyboardInterrupt:
        return 0
    finally:
        shown.end()
