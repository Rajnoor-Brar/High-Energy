"""`status.jsonl` and `run.pid`: a run that can be watched from somewhere else (06 §6).

The dashboard on the terminal that started a run is not the only audience. A run started over SSH, in
a batch job, or with `--detach` still has to be watchable — from a second terminal, from another
machine, from a session that attaches an hour later. So every status message is also appended to a
file, and `hep watch` renders that file with the same code that renders the live run.

The format is the status protocol of 06 §3.2 with two fields added, `point` and `stage`, because a
journal covers a whole run rather than one process; plus three run-level kinds that only the
supervisor's side knows:

| Kind | Meaning |
|---|---|
| `run` | the header: command, project, git state, the points to expect |
| `point` | a point changed state (running, done, failed, skipped, stopped) |
| `done` | the run ended, with its exit code |

Appending is line-buffered and never fatal: a full disk or a deleted directory costs the journal, not
the run.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

NAME = "status.jsonl"
PID = "run.pid"


class Journal:
    """An append-only record of one run, plus the pid file `hep runs` looks for."""

    def __init__(self, directory: Path | None, *, name: str = NAME, write_pid: bool = True) -> None:
        self.directory = Path(directory) if directory is not None else None
        self.path = self.directory / name if self.directory is not None else None
        self.pid_path = self.directory / PID if (self.directory and write_pid) else None
        self._handle = None
        self.dropped = 0
        if self.path is not None:
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                self._handle = open(self.path, "a", encoding="utf-8", buffering=1)
                if self.pid_path is not None:
                    self.pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
            except OSError:
                self._handle = None                  # a journal is a convenience, never a dependency

    # ── writing ──────────────────────────────────────────────────────────────

    def write(self, payload: dict[str, Any]) -> None:
        if self._handle is None:
            return
        payload.setdefault("t", time.time())
        try:
            self._handle.write(json.dumps(payload) + "\n")
        except (OSError, ValueError, TypeError):
            self.dropped += 1

    def raw(self, line: str, *, point: str = "", stage: str = "") -> None:
        """Append a status line a stage produced, tagged with where it came from.

        A line that cannot be parsed is still kept — verbatim, under `k: "garbled"` — because the one
        time a reader needs the journal is when something went wrong.
        """
        line = line.strip()
        if not line or self._handle is None:
            return
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("not an object")
        except (ValueError, TypeError):
            payload = {"k": "garbled", "raw": line[:2000]}
        if point:
            payload["point"] = point
        if stage:
            payload["stage"] = stage
        self.write(payload)

    def header(self, *, cli: str = "", project: str = "", git: str = "", study: str = "",
               points: Iterable[str] = ()) -> None:
        self.write({"k": "run", "cli": cli, "project": project, "git": git, "study": study,
                    "points": list(points), "pid": os.getpid()})

    def point(self, name: str, state: str, *, exit_code: int | None = None, reason: str = "",
              outputs: Iterable[str] = ()) -> None:
        self.write({"k": "point", "point": name, "state": state, "exit": exit_code,
                    "reason": reason, "outputs": list(outputs)})

    def done(self, exit_code: int = 0) -> None:
        self.write({"k": "done", "exit": exit_code})

    # ── lifetime ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            except OSError:                          # pragma: no cover - already gone
                pass
            self._handle = None
        if self.pid_path is not None:
            try:
                self.pid_path.unlink(missing_ok=True)
            except OSError:                          # pragma: no cover
                pass

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *_exception) -> None:
        self.close()


# ── reading, for `hep watch` and `hep runs` ──────────────────────────────────

def read(path: Path) -> list[str]:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def running_pid(directory: Path) -> int | None:
    """The pid of a live run in this directory, or None. A stale pid file is not a running run."""
    path = Path(directory) / PID
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)                              # signal 0: "does this process exist and is it ours"
    except ProcessLookupError:
        return None
    except PermissionError:
        return pid                                   # alive, someone else's
    return pid
