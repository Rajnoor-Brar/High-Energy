"""utils/hepkit.py — the C++ kit (utils/Kit.hh, Status.hh) for a custom tool written in Python (V74).

A custom tool is any program; this module gives one written in Python what the apps have:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "utils"))   # from modules/<P>/
    import hepkit

    status = hepkit.Status()                 # JSON lines on $HEP_STATUS_FD (status = "standard"), else stderr
    status.phase("reading", source)
    status.progress(done, total, rate)
    hepkit.report(output, events=n, …)       # <output>.json, written whole (.part, then renamed)
    sys.exit(hepkit.Exit.OK)

* `Exit`: the one exit-code table (0 ok, 1 config, 2 usage, 3 init, 4 input, 5 output, 6 stopped,
  70 internal), Kit::Exit's.
* `Status`: the standard protocol (docs/05_Tools_Reference.md §19): phase, progress (at most 4 a second
  unless forced), xsec, log, summary, and a heartbeat every half second, so the runner's stall check
  sees a quiet tool alive. Writes never block: a line that does not fit the pipe is dropped and counted.
* `stopping()`: SIGINT or SIGTERM was received (after `Status()` installs the handlers): finish what
  is written, exit `Exit.STOPPED`.
* `usage(text)`: print it and exit `Exit.USAGE`.

Standard library only; utils/ (not utils/Env, whose tool folders would shadow the yoda and rivet
packages) is what a tool puts on its path.
"""

from __future__ import annotations

import enum
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path


class Exit(enum.IntEnum):
    OK = 0
    CONFIG = 1
    USAGE = 2
    INIT = 3
    INPUT = 4
    OUTPUT = 5
    STOPPED = 6
    INTERNAL = 70


_stop = threading.Event()


def _on_signal(signum, frame):
    if _stop.is_set():                                   # a second one is the default behaviour
        signal.signal(signum, signal.SIG_DFL)
    _stop.set()


def stopping() -> bool:
    return _stop.is_set()


def usage(text: str) -> None:
    print(text, file=sys.stderr)
    sys.exit(Exit.USAGE)


class Status:
    """The standard status protocol, as utils/Status.hh writes it."""

    def __init__(self, beat: float = 0.5, signals: bool = True):
        value = os.environ.get("HEP_STATUS_FD")
        self.fd = int(value) if value and value.lstrip("-").isdigit() and int(value) >= 0 else -1
        if self.fd >= 0:
            os.set_blocking(self.fd, False)
        self.dropped = 0
        self._last_progress = 0.0
        self._last_send = 0.0
        self._lock = threading.Lock()
        self._closed = threading.Event()
        if signals:
            signal.signal(signal.SIGINT, _on_signal)
            signal.signal(signal.SIGTERM, _on_signal)
        if beat > 0 and self.fd >= 0:
            threading.Thread(target=self._beat, args=(beat,), name="hepkit-heartbeat", daemon=True).start()

    @property
    def structured(self) -> bool:
        return self.fd >= 0

    def phase(self, name: str, detail: str = "") -> None:
        self._send("phase", {"phase": name, **({"detail": detail} if detail else {})},
                   f"[{name}]" + (f" {detail}" if detail else ""))

    def progress(self, done: int, total: int, rate: float = 0.0, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_progress < 0.25:
            return
        self._last_progress = now
        self._send("progress", {"done": done, "total": total, "rate": rate}, f"{done}/{total} ({rate:g}/s)")

    def xsec(self, value_pb: float, err_pb: float, final: bool = False) -> None:
        self._send("xsec", {"value_pb": value_pb, "err_pb": err_pb, "final": final},
                   f"sigma = {value_pb:g} +- {err_pb:g} pb" + (" (final)" if final else ""))

    def log(self, level: str, message: str) -> None:
        self._send("log", {"level": level, "msg": message}, f"{level}: {message}")

    def summary(self, **fields) -> None:
        self._send("summary", fields, "summary: " + json.dumps(fields))

    def close(self) -> None:
        self._closed.set()

    def _send(self, kind: str, fields: dict, plain: str) -> None:
        if self.fd < 0:
            if plain:
                print(plain, file=sys.stderr, flush=True)
            return
        line = (json.dumps({"t": round(time.time(), 6), "k": kind, **fields}) + "\n").encode()
        with self._lock:
            try:
                written = os.write(self.fd, line)            # up to PIPE_BUF: whole or not at all
            except (BlockingIOError, BrokenPipeError):
                written = 0
            if written != len(line):
                self.dropped += 1
            self._last_send = time.time()

    def _beat(self, period: float) -> None:
        while not self._closed.wait(period):
            if time.time() - self._last_send >= period:
                self._send("heartbeat", {}, "")


def report(output: str | Path, **fields) -> Path:
    """<output>.json beside a product, written whole: what the runner's `json:` count check and the
    plots read. Returns its path."""
    path = Path(str(output) + ".json")
    partial = path.with_name(path.name + ".part")
    partial.write_text(json.dumps(fields, indent=1) + "\n", encoding="utf-8")
    partial.replace(path)
    return path
