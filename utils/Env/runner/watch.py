"""What the user sees while points run (rank 4).

docs/rework_v2/02_Architecture.md §8. The view is fed only by status: ToolState objects that
`execute` updates from the tools' status pipes and log filters. It never looks at a process.

`PlainView` prints one line per event of note and a progress line every few seconds. It is what a
log file or a non-TTY gets.
"""

from __future__ import annotations

import sys
import time


def _count(value) -> str:
    if value is None:
        return "?"
    return f"{value / 1e6:.2f}M" if value >= 1e6 else f"{value / 1e3:.1f}k" if value >= 1e4 else str(value)


def progress_text(state) -> str:
    parts = [f"{state.tag}"]
    if state.phase:
        parts.append(state.phase)
    if state.done is not None:
        parts.append(f"{_count(state.done)}/{_count(state.total)}" if state.total else _count(state.done))
    if state.rate:
        parts.append(f"{state.rate:,.0f}/s")
    if state.done and state.total and state.rate:
        left = (state.total - state.done) / state.rate
        parts.append(f"ETA {int(left // 60)}:{int(left % 60):02d}")
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

    def begin(self, count: int) -> None:
        self.total = count

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
        line = " | ".join(progress_text(s) for s in states if s.running)
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
