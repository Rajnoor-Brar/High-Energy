"""Status from running tools: the standard protocol and the stdout filter rules (rank 3).

docs/rework_v2/05_Tools.md §3 and 02_Architecture.md §8.

* A tool with status = "standard" writes JSON lines to $HEP_STATUS_FD (utils/Status.hh). The runner
  reads a pipe per process and keeps unknown kinds, ignored.
* Every other tool only prints. Its log is tailed and matched against its filters.toml rules
  (progress, phase, warn, error, ignore). A rule never fails a run: the exit code does that.
* Every message goes to output/…/status.jsonl, tagged with its point and tool, for `hep watch`.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path


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


class Journal:
    """Appends every status message to status.jsonl, so `hep watch` can follow from elsewhere."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.handle = open(path, "a", encoding="utf-8")

    def write(self, point: str, tag: str, message: dict) -> None:
        self.handle.write(json.dumps({"point": point, "tool": tag, **message}) + "\n")
        self.handle.flush()

    def close(self) -> None:
        self.handle.close()


class Reader:
    """One process's status: its fd pipe (standard) or its log tail (filters)."""

    def __init__(self, state: ToolState, *, fd: int | None, log: Path, rules: list[dict], journal: Journal | None):
        self.state = state
        self.fd = fd
        self.log = log
        self.offset = 0
        self.partial = b""
        self.fd_partial = b""
        self.rules = [(re.compile(r["match"]), r) for r in rules]
        self.journal = journal
        if fd is not None:
            os.set_blocking(fd, False)

    def _emit(self, message: dict) -> None:
        apply(self.state, message)
        if self.journal is not None:
            self.journal.write(self.state.point, self.state.tag, message)

    def poll(self) -> None:
        if self.fd is not None:
            while True:
                try:
                    chunk = os.read(self.fd, 65536)
                except BlockingIOError:
                    break
                if not chunk:
                    break
                self.fd_partial += chunk
            *lines, self.fd_partial = self.fd_partial.split(b"\n")
            for line in lines:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if isinstance(message, dict) and "k" in message:
                    self._emit(message)
        try:
            size = self.log.stat().st_size
        except FileNotFoundError:
            return
        if size > self.offset:
            with open(self.log, "rb") as handle:
                handle.seek(self.offset)
                data = handle.read(size - self.offset)
            self.offset = size
            self.state.last_activity = time.monotonic()
            *lines, self.partial = re.split(rb"\r\n|\r|\n", self.partial + data)   # \r: a progress counter
            for raw in lines:
                text = raw.decode("utf-8", "replace").rstrip("\r")
                if text.strip():
                    self.state.last_line = text.strip()[:200]
                for pattern, rule in self.rules:
                    match = pattern.search(text)
                    if match is None:
                        continue
                    self._rule(rule, match, text)
                    break

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
