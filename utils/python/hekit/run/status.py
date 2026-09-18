"""Reading the status stream `hep-run` writes on fd 3 (06 §3).

The stream is JSON lines. This reader is deliberately forgiving in one direction and strict in the
other: a message kind it does not know is **kept and flagged**, so a newer `hep-run` can talk to an
older `hep` without losing information, while a line that is not JSON at all is reported as garbled
rather than silently dropped — that difference is what makes a protocol debuggable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Iterable, Iterator

#: The kinds of 06 §3.2. Anything else is carried through as unknown.
KINDS = frozenset({"phase", "init", "progress", "xsec", "log", "checkpoint", "event", "summary",
                   "heartbeat"})


@dataclass
class Message:
    """One status line."""

    kind: str
    time: float = 0.0
    fields: dict[str, Any] = dataclass_field(default_factory=dict)
    raw: str = ""
    known: bool = True
    error: str = ""

    def __getitem__(self, key: str) -> Any:
        return self.fields[key]

    def get(self, key: str, fallback: Any = None) -> Any:
        return self.fields.get(key, fallback)

    @property
    def ok(self) -> bool:
        return not self.error


def parse_line(line: str) -> Message | None:
    """One line into a `Message`; None for a blank line."""
    text = line.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        return Message(kind="garbled", raw=text, known=False, error=str(error))
    if not isinstance(payload, dict):
        return Message(kind="garbled", raw=text, known=False, error="not a JSON object")
    kind = str(payload.pop("k", ""))
    time = payload.pop("t", 0.0)
    return Message(kind=kind or "unknown", time=float(time) if isinstance(time, (int, float)) else 0.0,
                   fields=payload, raw=text, known=kind in KINDS,
                   error="" if kind else "no 'k' field")


def read(lines: Iterable[str]) -> Iterator[Message]:
    """Every message of a stream, in order."""
    for line in lines:
        message = parse_line(line)
        if message is not None:
            yield message


@dataclass
class StatusReader:
    """The state a dashboard needs, folded from the stream as it arrives (P3-S04 renders it)."""

    phase: str = ""
    detail: str = ""
    done: int = 0
    total: int = 0
    rate: float = 0.0
    workers: list[int] = dataclass_field(default_factory=list)
    xsec_pb: float | None = None
    xsec_error_pb: float | None = None
    xsec_final: bool = False
    beams: dict[str, Any] = dataclass_field(default_factory=dict)
    threads: int = 0
    mode: str = ""
    sinks: list[str] = dataclass_field(default_factory=list)
    logs: list[dict[str, str]] = dataclass_field(default_factory=list)
    checkpoints: list[dict[str, Any]] = dataclass_field(default_factory=list)
    summary: dict[str, Any] = dataclass_field(default_factory=dict)
    events: list[dict[str, Any]] = dataclass_field(default_factory=list)
    unknown: list[Message] = dataclass_field(default_factory=list)
    garbled: list[Message] = dataclass_field(default_factory=list)
    last_time: float = 0.0
    heartbeats: int = 0

    def feed(self, message: Message) -> None:
        """Fold one message in."""
        self.last_time = message.time or self.last_time
        if message.error:
            self.garbled.append(message)
            return
        if not message.known:
            self.unknown.append(message)
            return
        handler = getattr(self, f"_on_{message.kind}", None)
        if handler is not None:
            handler(message)

    def feed_lines(self, lines: Iterable[str]) -> "StatusReader":
        for message in read(lines):
            self.feed(message)
        return self

    def feed_file(self, path: str | Path) -> "StatusReader":
        with Path(path).open(encoding="utf-8", errors="replace") as handle:
            return self.feed_lines(handle)

    # one handler per kind, so an unknown kind cannot reach the wrong one -----
    def _on_phase(self, message: Message) -> None:
        self.phase = message.get("phase", "")
        self.detail = message.get("detail", "")

    def _on_init(self, message: Message) -> None:
        self.beams = {"ids": message.get("beam_ids", []), "energies": message.get("beam_energies", []),
                      "sqrt_s": message.get("sqrt_s")}
        self.threads = int(message.get("threads", 0) or 0)
        self.mode = message.get("mode", "")
        self.sinks = list(message.get("sinks", []))

    def _on_progress(self, message: Message) -> None:
        self.done = int(message.get("done", 0) or 0)
        self.total = int(message.get("total", 0) or 0)
        self.rate = float(message.get("rate", 0.0) or 0.0)
        self.workers = [int(count) for count in message.get("workers", [])]

    def _on_xsec(self, message: Message) -> None:
        self.xsec_pb = message.get("value_pb")
        self.xsec_error_pb = message.get("err_pb")
        self.xsec_final = bool(message.get("final", False))

    def _on_log(self, message: Message) -> None:
        self.logs.append({"level": message.get("level", "info"), "source": message.get("source", ""),
                          "msg": message.get("msg", "")})

    def _on_checkpoint(self, message: Message) -> None:
        self.checkpoints.append({"done": message.get("done", 0), "outputs": message.get("outputs", [])})

    def _on_event(self, message: Message) -> None:
        self.events.append(dict(message.fields))

    def _on_summary(self, message: Message) -> None:
        self.summary = dict(message.fields)

    def _on_heartbeat(self, message: Message) -> None:
        self.heartbeats += 1

    # what a dashboard asks ---------------------------------------------------
    @property
    def fraction(self) -> float:
        return self.done / self.total if self.total > 0 else 0.0

    @property
    def stopped(self) -> bool:
        return bool(self.summary.get("stopped", False))

    @property
    def warnings(self) -> list[dict[str, str]]:
        return [entry for entry in self.logs if entry["level"] in {"warn", "error"}]

    def eta_seconds(self) -> float | None:
        if self.rate <= 0.0 or self.total <= self.done:
            return None
        return (self.total - self.done) / self.rate
