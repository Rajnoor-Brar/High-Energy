"""Reading progress out of a tool's own chatter (06 §4).

`hep-run` reports on its status descriptor and needs nothing here. Everything else — Sherpa, Whizard,
Herwig, MadGraph, `DelphesHepMC3` — only prints, so the supervisor scrapes their output for the two
numbers a dashboard needs: how many events, and what the tool is doing.

Two rules keep this honest:

* **A parser never fails a run.** A regex that stops matching after an upstream release costs a
  progress bar, never a result; every parser is wrapped so a bad match is ignored.
* **The tables here are a starting point, not a measurement.** 06 §4 says to calibrate them against
  real logs, and each generator's own step (P7-S03…S06) does that with the tool installed. Until then
  the fallback applies: a spinner, elapsed time and the last line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Progress:
    """What a parser could tell from the output so far."""

    events: int | None = None
    total: int | None = None
    stage: str = ""                  # a named phase, for tools that have them (MadGraph)
    last_line: str = ""

    def update(self, other: "Progress") -> None:
        if other.events is not None:
            self.events = other.events
        if other.total is not None:
            self.total = other.total
        if other.stage:
            self.stage = other.stage
        if other.last_line:
            self.last_line = other.last_line


@dataclass
class Parser:
    """A tool's progress patterns. `events`/`stage` groups are read when they match."""

    tool: str
    events: list[re.Pattern] = field(default_factory=list)
    stages: list[re.Pattern] = field(default_factory=list)
    note: str = ""

    def feed(self, line: str) -> Progress:
        found = Progress(last_line=line.strip()[:200])
        for pattern in self.events:
            match = pattern.search(line)
            if match is None:
                continue
            try:
                found.events = int(match.group("events").replace(" ", "").replace(",", ""))
                if "total" in (match.groupdict() or {}) and match.group("total"):
                    found.total = int(match.group("total").replace(" ", "").replace(",", ""))
            except (ValueError, IndexError):             # pragma: no cover - a pattern that lied
                pass
            break
        for pattern in self.stages:
            match = pattern.search(line)
            if match is not None:
                found.stage = (match.group("stage") if "stage" in (match.groupdict() or {})
                               else match.group(0)).strip()
                break
        return found


def _compile(*patterns: str) -> list[re.Pattern]:
    return [re.compile(pattern) for pattern in patterns]


#: 06 §4's table. Calibrated per tool in P7; `hep-run` is absent on purpose — it has a status stream.
PARSERS = {
    "sherpa": Parser("sherpa",
                     events=_compile(r"Event\s+(?P<events>[\d ,]+)\s*\("),
                     note="Sherpa prints 'Event <n> ( ... )' during generation"),
    "whizard": Parser("whizard",
                      events=_compile(r"Events:\s*generated\s+(?P<events>[\d ,]+)",
                                      r"\|\s*Events:\s*(?P<events>[\d ,]+)"),
                      stages=_compile(r"(?P<stage>Integrat\w+|Simulat\w+)"),
                      note="integration iterations show as stages during prepare"),
    "herwig": Parser("herwig",
                     events=_compile(r"event>\s*(?P<events>[\d ,]+)"),
                     note="Herwig's 'event> <n>' progress"),
    "madgraph": Parser("madgraph",
                       stages=_compile(r"^\s*(?P<stage>Survey|Refine|Combining|Running Pythia|"
                                       r"Storing files|Generating Events)"),
                       note="stage names only; MadGraph has no usable event counter in the log"),
    "delphes": Parser("delphes",
                      events=_compile(r"\*\*\s*(?P<events>[\d ,]+)\s+events? processed",
                                      r"Processing\s+event\s+(?P<events>[\d ,]+)"),
                      note="DelphesHepMC3 progress output"),
}


def parser_for(tool: str) -> Parser | None:
    """The parser for a tool, or None when it has no known progress output (then: spinner + last line)."""
    return PARSERS.get(tool.lower())
