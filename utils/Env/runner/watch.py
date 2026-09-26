"""What the user sees while points run (rank 4).

docs/rework_v2/02_Architecture.md §8. The views are fed only by status: ToolState objects that
`execute` updates from the tools' status pipes and log filters. They never look at a process, so
`hep watch` can drive the same views from output/…/status.jsonl in another terminal.

* `LiveView` (rich, on a terminal): one line per running tool — point, tool, phase, a bar, the
  count, rate and ETA, and the last warning — with each finished point printed above it.
* `PlainView` (a pipe, a log file, or `--plain`): one line per event of note, and a progress line
  every few seconds.
"""

from __future__ import annotations

import json
import sys
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


class PlainView:
    def __init__(self, stream=None, every: float = 5.0):
        self.stream = stream or sys.stdout
        self.every = every
        self.last = 0.0
        self.total = 0
        self.number = 0

    def say(self, text: str) -> None:
        print(text, file=self.stream, flush=True)

    def begin(self, count: int, title: str = "") -> None:
        self.total = count
        if title:
            self.say(title)

    def end(self) -> None:
        pass

    def point_started(self, plan) -> None:
        self.number += 1
        self.say(f"── point {self.number}/{self.total}: {plan.point.name}")

    def tool_started(self, state) -> None:
        pass

    def tick(self, states) -> None:
        now = time.monotonic()
        if now - self.last < self.every:
            return
        self.last = now
        line = " | ".join(progress_text(s) if (s.phase or s.done is not None) else f"{s.tag} … {s.last_line[:60]}"
                          for s in states if s.running)
        if line:
            self.say(f"   {line}")

    def tool_finished(self, state, result) -> None:
        verdict = "ok" if result.exit == 0 else f"exit {result.exit}"
        extra = f"  ({state.error})" if state.error and result.exit else ""
        self.say(f"   {state.tag}: {verdict} after {result.seconds:.1f} s{extra}")

    def point_finished(self, plan, result) -> None:
        if result.ok:
            self.say(f"   done → {plan.res}")
        elif result.stopped:
            self.say("   stopped: partial outputs keep their .partial names")
        else:
            blame = f" [{result.cause}]" if result.cause else ""
            self.say(f"   FAILED{blame}: {result.message}")

    def skipped(self, plan) -> None:
        self.number += 1
        self.say(f"── point {self.number}/{self.total}: {plan.point.name}: complete, skipped (--rerun to run it again)")


class LiveView(PlainView):
    """The rich version: the same events, and a live table of the running tools."""

    SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self):
        super().__init__()
        from rich.console import Console
        from rich.live import Live
        self.console = Console()
        self.live = Live(console=self.console, refresh_per_second=4, transient=True)
        self.states: list[ToolState] = []
        self.point_name = ""
        self.started = time.monotonic()
        self.frame = 0

    def say(self, text: str) -> None:
        self.console.print(text, highlight=False)

    def begin(self, count: int, title: str = "") -> None:
        self.total = count
        if title:
            self.say(f"[bold]{title}[/bold]")
        self.live.start()

    def end(self) -> None:
        self.live.stop()

    def point_started(self, plan) -> None:
        self.number += 1
        self.point_name = plan.point.name
        self.states = []
        self.say(f"── point {self.number}/{self.total}: [bold]{plan.point.name}[/bold]")

    def tool_started(self, state) -> None:
        self.states.append(state)

    def tick(self, states) -> None:
        self.frame += 1
        self.live.update(self.render(states or self.states))

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
        table.add_row("", f"[dim]point {self.number}/{self.total} · {int(elapsed // 60)}:{int(elapsed % 60):02d}[/dim]",
                      "", "", "", "", "")
        return table

    def tool_finished(self, state, result) -> None:
        colour = "green" if result.exit == 0 else "red"
        extra = f"  ({state.error})" if state.error and result.exit else ""
        self.say(f"   [{colour}]{state.tag}[/{colour}]: {'ok' if result.exit == 0 else f'exit {result.exit}'} "
                 f"after {result.seconds:.1f} s{extra}")

    def point_finished(self, plan, result) -> None:
        if result.ok:
            self.say(f"   [green]done[/green] → {plan.res}")
        elif result.stopped:
            self.say("   [yellow]stopped[/yellow]: partial outputs keep their .partial names")
        else:
            blame = f" [{result.cause}]" if result.cause else ""
            self.say(f"   [red]FAILED{blame}[/red]: {result.message}")


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
                            shown.number += 1
                            shown.say(f"── point {message.get('index', shown.number)}: {point}")
                        else:
                            shown.say(f"   {point}: {message.get('state')} {message.get('msg') or ''}".rstrip())
                        continue
                    state = states.setdefault((point, tag), ToolState(point=point, tag=tag))
                    if kind == "exit":
                        state.running, state.exit = False, message.get("code")
                        verdict = "ok" if message.get("code") == 0 else f"exit {message.get('code')}"
                        shown.say(f"   {tag}: {verdict} after {message.get('seconds', 0):.1f} s")
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
