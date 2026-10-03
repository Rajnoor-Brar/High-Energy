"""Status from running tools: the standard protocol and the stdout filter rules (rank 3).

docs/05_Tools_Reference.md §19 and docs/02_Architecture.md §10.

* A tool with status = "standard" writes JSON lines to $HEP_STATUS_FD (utils/Status.hh); a tool's
  output is matched against its filters.toml rules (progress, phase, warn, error, ignore). A rule never
  fails a run: the exit code does that.
* Both are read from pipes by one thread per tool (V72), so a tool that prints fast never waits on a
  full pipe, and nothing of it is on disk unless asked: the last TAIL lines are kept in memory and
  written to logs/<tag>.log only when the tool fails; `--logs` writes every line as it comes.
* Every message goes onto the run's event bus (events.py), tagged with its point and tool.
"""

from __future__ import annotations

import collections
import json
import os
import re
import selectors
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

TAIL = 200                       # a failed tool's last lines, written beside its point (V72)
LINE_EVERY = 0.5                 # seconds between a tool's `line` events


@dataclass
class ToolState:
    """What the watch view shows for one tool of one point."""
    point: str
    tag: str
    phase: str = ""
    done: int | None = None
    total: int | None = None
    rate: float | None = None
    xsec: tuple[float, float] | None = None
    warning: str = ""
    error: str = ""
    last_line: str = ""
    last_activity: float = field(default_factory=time.monotonic)
    running: bool = True
    exit: int | None = None


class Reader:
    """One process's status pipe (standard) and output pipe, read on a thread of its own until both end."""

    def __init__(self, state: ToolState, *, fd: int | None, out: int | None, rules: list[dict], bus,
                 log: Path | None = None, keep: bool = False):
        self.state = state
        self.rules = [(re.compile(r["match"]), r) for r in rules]
        self.bus = bus
        self.log, self.keep = log, keep
        self.tail: collections.deque = collections.deque(maxlen=TAIL)
        self._fds = [f for f in (fd, out) if f is not None]
        self._status_fd, self._out_fd = fd, out
        self._partial = {f: b"" for f in self._fds}
        self._line_at = 0.0
        self._handle = open(log, "ab") if keep and log is not None else None
        self._thread = threading.Thread(target=self._loop, name=f"hep-read-{state.tag}", daemon=True)
        if self._fds:
            self._thread.start()

    def _emit(self, message: dict) -> None:
        apply(self.state, message)
        if self.bus is not None:
            self.bus.emit(self.state.point, self.state.tag, message)

    def _loop(self) -> None:
        selector = selectors.DefaultSelector()
        for fd in self._fds:
            selector.register(fd, selectors.EVENT_READ)
        open_fds = set(self._fds)
        while open_fds:
            for key, _ in selector.select(timeout=1.0):
                try:
                    chunk = os.read(key.fd, 65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    selector.unregister(key.fd)
                    open_fds.discard(key.fd)
                    self._lines(key.fd, b"", final=True)
                    continue
                self.state.last_activity = time.monotonic()
                self._lines(key.fd, chunk)
        selector.close()
        for fd in self._fds:
            try:
                os.close(fd)
            except OSError:
                pass
        if self._handle is not None:
            self._handle.close()

    def _lines(self, fd: int, chunk: bytes, final: bool = False) -> None:
        data = self._partial[fd] + chunk
        if fd == self._status_fd:
            *lines, self._partial[fd] = data.split(b"\n")
            for line in lines:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if isinstance(message, dict) and "k" in message:
                    self._emit(message)
            return
        if self._handle is not None and chunk:
            self._handle.write(chunk)
            self._handle.flush()
        *lines, self._partial[fd] = re.split(rb"\r\n|\r|\n", data)     # \r: a progress counter
        if final and self._partial[fd]:
            lines.append(self._partial[fd])
            self._partial[fd] = b""
        for raw in lines:
            self.output(raw.decode("utf-8", "replace").rstrip("\r"))

    def output(self, text: str) -> None:
        """One line the tool printed: the tail, the latest line, and its filter rules."""
        if text.strip():
            self.tail.append(text)
            self.state.last_line = text.strip()[:200]
            now = time.monotonic()
            if self.bus is not None and now - self._line_at >= LINE_EVERY:
                self._line_at = now
                self.bus.emit(self.state.point, self.state.tag, {"k": "line", "msg": self.state.last_line})
        for pattern, rule in self.rules:
            match = pattern.search(text)
            if match is None:
                continue
            self._rule(rule, match, text)
            break

    def join(self, timeout: float = 2.0) -> None:
        """Wait for the pipes to end (a child that keeps the tool's stdout open is not waited for)."""
        if self._thread.is_alive():
            self._thread.join(timeout)

    def keep_tail(self) -> Path | None:
        """A failed tool: its last lines to logs/<tag>.log (unless --logs wrote them all already)."""
        if self.log is None or self.keep:
            return self.log
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text("".join(f"{line}\n" for line in self.tail), encoding="utf-8")
        return self.log

    def _rule(self, rule: dict, match: re.Match, text: str) -> None:
        emit = rule.get("emit", "ignore")
        try:
            if emit == "progress":
                groups = match.groupdict()
                message = {"k": "progress", "done": int(groups["done"].replace(",", "").replace(" ", ""))}
                if groups.get("total"):
                    message["total"] = int(groups["total"].replace(",", ""))
                self._emit(message)
            elif emit == "phase":
                self._emit({"k": "phase", "phase": rule.get("phase") or match.groupdict().get("phase") or match.group(0)})
            elif emit in ("warn", "error"):
                self._emit({"k": "log", "level": emit, "msg": text.strip()[:300]})
        except (KeyError, ValueError, AttributeError, TypeError):
            pass                                                     # a rule never fails a run


def apply(state: ToolState, message: dict) -> None:
    state.last_activity = time.monotonic()
    kind = message.get("k")
    if kind == "phase":
        state.phase = str(message.get("phase", ""))
    elif kind == "progress":
        state.done = message.get("done", state.done)
        state.total = message.get("total", state.total)
        state.rate = message.get("rate", state.rate)
    elif kind == "xsec":
        state.xsec = (message.get("value_pb"), message.get("err_pb"))
    elif kind == "log":
        if message.get("level") == "error":
            state.error = str(message.get("msg", ""))
        elif message.get("level") in ("warn", "warning"):
            state.warning = str(message.get("msg", ""))
    elif kind == "line":
        state.last_line = str(message.get("msg", ""))
