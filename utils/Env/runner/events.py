"""The event stream: what a run says while it runs, and who hears it (rank 1).

docs/02_Architecture.md §10, audit 1 B3 (V72). The executor, the stages and the CLI emit **events** onto
one `Bus`; each is a dict with the stream's version `v`, the point and tool it is about (`""` for the run),
the time `t`, and its kind `k`:

    run    state = started (points, title, header) | finished (verdict)
    point  state = started (index, stage) | done | stopped | failed (cause, msg, res) | skipped
    tool   state = started                     exit   code, seconds, error
    phase, progress, xsec, log                  a tool's own status (utils/Status.hh, or its filters)
    line   a tool's latest output line (at most twice a second per tool)
    note   a line for the point's block        say    a line of the run's

Runtime state stays off disk (the user, 2026-10-03). Who hears the bus:
* the view, always (watch.py);
* the **Hub**, while the process lives: an abstract Unix socket `@hep-watch-<pid>` (no file, no path
  limit). `hep watch` finds it in /proc/net/unix, gets a greeting, the current run's events so far
  (a tool's progress only as its latest), then every event live. A sweep of runs is one process, so
  the stream follows from run to run by itself;
* the **Journal**, only with `--journal`: the same events in output/…/status.jsonl, one file per run,
  for replay (`hep watch --file`) and tests.

A subscriber is called on the emitting thread and must not block; the Hub queues for each client and
drops a client that stops reading. In a sweep of runs, each run emits through a `RunBus`, which adds
`run` (its configuration's key) to every event, since a pipelined sweep's runs overlap (V75).
"""

from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
from pathlib import Path

VERSION = 1
PREFIX = "hep-watch-"                     # the abstract socket's name: PREFIX + pid


class Bus:
    """Stamps events and hands them to every subscriber, in order, under one lock."""

    def __init__(self):
        self._subscribers: list = []
        self._lock = threading.Lock()

    def subscribe(self, subscriber) -> None:
        """`subscriber(event)`, or an object with `event(event)`."""
        with self._lock:
            self._subscribers.append(getattr(subscriber, "event", subscriber))

    def unsubscribe(self, subscriber) -> None:
        with self._lock:
            target = getattr(subscriber, "event", subscriber)
            self._subscribers = [s for s in self._subscribers if s != target]

    def emit(self, point: str, tool: str, message: dict) -> dict:
        event = {"v": VERSION, "point": point, "tool": tool, "t": round(time.time(), 3), **message}
        with self._lock:
            for subscriber in self._subscribers:
                subscriber(event)
        return event

    def say(self, text: str) -> None:
        self.emit("", "", {"k": "say", "msg": text})


class RunBus:
    """One run's voice on a shared bus (V75): every event it emits says which run it is of."""

    def __init__(self, bus: Bus, run: str):
        self.bus, self.run = bus, run

    def emit(self, point: str, tool: str, message: dict) -> dict:
        return self.bus.emit(point, tool, {**message, "run": self.run})

    def say(self, text: str) -> None:
        self.emit("", "", {"k": "say", "msg": text})

    def subscribe(self, subscriber) -> None:
        self.bus.subscribe(subscriber)

    def unsubscribe(self, subscriber) -> None:
        self.bus.unsubscribe(subscriber)


class Journal:
    """--journal: every event of one run in its status.jsonl, the file begun afresh. With `run`, only
    that run's events (a pipelined sweep's runs share one bus, V75)."""

    def __init__(self, path: Path, run: str | None = None):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.run = path, run
        self.handle = open(path, "w", encoding="utf-8")

    def event(self, event: dict) -> None:
        if self.run is not None and event.get("run") != self.run:
            return
        self.handle.write(json.dumps(event) + "\n")
        self.handle.flush()

    def close(self) -> None:
        self.handle.close()


class Hub:
    """The watch socket of this process (V72): a greeting, the current run's events so far, then the live
    events, to every client that connects. A client that falls 10,000 events behind is dropped."""

    def __init__(self, greeting: dict, name: str | None = None):
        self.name = name or f"{PREFIX}{os.getpid()}"
        self.greeting = {"k": "hello", "v": VERSION, "pid": os.getpid(), "started": round(time.time(), 3), **greeting}
        self._kept: list[dict] = []                     # the current run's events …
        self._latest: dict[tuple, dict] = {}            # … with a tool's progress as its latest only
        self._clients: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind("\0" + self.name)
        self._server.listen(8)
        self._closed = False
        threading.Thread(target=self._accept, name="hep-watch-hub", daemon=True).start()

    def event(self, event: dict) -> None:
        with self._lock:
            if event.get("k") == "run" and event.get("state") == "started" and not event.get("run"):
                self._kept, self._latest = [], {}             # a single run: the new run is all a watcher needs
            if event.get("k") in ("progress", "line"):
                self._latest[(event["point"], event["tool"], event["k"])] = event
            else:
                self._kept.append(event)
            for client in list(self._clients):
                try:
                    client.put_nowait(event)
                except queue.Full:
                    self._clients.remove(client)

    def _accept(self) -> None:
        while not self._closed:
            try:
                connection, _ = self._server.accept()
            except OSError:
                return
            with self._lock:
                backlog = [self.greeting, *self._kept, *self._latest.values()]
                client: queue.Queue = queue.Queue(maxsize=10000)
                self._clients.append(client)
            threading.Thread(target=self._serve, args=(connection, backlog, client), daemon=True).start()

    def _serve(self, connection: socket.socket, backlog: list, client: queue.Queue) -> None:
        try:
            with connection:
                for event in backlog:
                    connection.sendall((json.dumps(event) + "\n").encode())
                while True:
                    event = client.get()
                    if event is None:
                        return
                    connection.sendall((json.dumps(event) + "\n").encode())
        except OSError:
            pass
        finally:
            with self._lock:
                if client in self._clients:
                    self._clients.remove(client)

    def close(self) -> None:
        """The process is ending: every client gets the end of the stream."""
        self._closed = True
        with self._lock:
            for client in self._clients:
                try:
                    client.put_nowait(None)
                except queue.Full:
                    pass
        try:                                            # shutdown wakes the accept(); close alone does not
            self._server.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._server.close()
        except OSError:
            pass


def hubs() -> list[str]:
    """The watch sockets on this machine: their abstract names, from /proc/net/unix."""
    found = []
    try:
        with open("/proc/net/unix", encoding="utf-8", errors="replace") as table:
            for line in table:
                path = line.split()[-1] if line.split() else ""
                if path.startswith("@" + PREFIX) and path[1:] not in found:
                    found.append(path[1:])
    except OSError:
        pass
    return found


def connect(name: str, timeout: float = 2.0):
    """A watch socket's events, as they come; the first is its greeting. Ends when the run's process does."""
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect("\0" + name)
    client.settimeout(None)
    with client, client.makefile("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def greeting(name: str) -> dict | None:
    """A watch socket's greeting, or None if it does not answer."""
    try:
        return next(connect(name, timeout=1.0), None)
    except OSError:
        return None
