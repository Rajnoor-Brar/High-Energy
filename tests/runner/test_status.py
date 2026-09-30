"""Status: the fd protocol, the filter rules, the journal, and `hep watch` following it."""

from __future__ import annotations

import io
import json
import os

from runner.status import Journal, Reader, ToolState
from runner.watch import PlainView, follow

RIVET_RULES = [
    {"match": r"^Event (?P<done>\d+) \(", "emit": "progress"},
    {"match": r"^Reading events from", "emit": "phase", "phase": "analysing"},
    {"match": r"WARN .*unvalidated", "emit": "ignore"},
    {"match": r"\bWARN\b", "emit": "warn"},
    {"match": r"^Broken (?P<done>x)", "emit": "progress"},        # a rule whose group is not a number
]


def test_filter_rules_turn_lines_into_status(scratch):
    log = scratch / "rivet.log"
    state = ToolState("p", "rivet")
    reader = Reader(state, fd=None, log=log, rules=RIVET_RULES, journal=None)
    log.write_text("Reading events from 'x'\nRivet: WARN Analysis 'a' is unvalidated\nEvent 100 (0:00:01)\n",
                   encoding="utf-8")
    reader.poll()
    assert (state.phase, state.done, state.warning) == ("analysing", 100, "")
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("Rivet: WARN something real\nEvent 2")               # an unfinished line waits
    reader.poll()
    assert state.warning.endswith("something real") and state.done == 100
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("00 (0:00:02)\nBroken x\n")
    reader.poll()                                                        # a bad rule never raises
    assert state.done == 200 and state.last_line == "Broken x"


def test_the_fd_protocol_keeps_unknown_kinds_and_journals_everything(scratch):
    read, write = os.pipe()
    journal = Journal(scratch / "status.jsonl")
    state = ToolState("p", "pythia")
    reader = Reader(state, fd=read, log=scratch / "none.log", rules=[], journal=journal)
    os.write(write, b'{"t": 1, "k": "phase", "phase": "generating"}\n{"t": 2, "k": "progress", "done": 5, '
                    b'"total": 10, "rate": 2.5}\n{"t": 3, "k": "novel", "x": 1}\nnot json\n{"t": 4, "k": "xs')
    reader.poll()
    assert (state.phase, state.done, state.total, state.rate) == ("generating", 5, 10, 2.5)
    os.write(write, b'ec", "value_pb": 7.0, "err_pb": 0.5, "final": true}\n')
    reader.poll()
    assert state.xsec == (7.0, 0.5)
    journal.close()
    kinds = [json.loads(line)["k"] for line in (scratch / "status.jsonl").read_text(encoding="utf-8").splitlines()]
    assert kinds == ["phase", "progress", "novel", "xsec"]
    os.close(read)
    os.close(write)


def test_watch_follows_the_latest_run_and_stops_when_it_finishes(scratch, monkeypatch):
    journal = scratch / "status.jsonl"
    lines = [
        {"point": "", "tool": "", "k": "run", "state": "started", "points": 1, "title": "old"},
        {"point": "", "tool": "", "k": "run", "state": "finished", "verdict": "old verdict"},
        {"point": "", "tool": "", "k": "run", "state": "started", "points": 1, "title": "new"},
        {"point": "a", "tool": "", "k": "point", "state": "started", "index": 1, "t": 100.0},
        {"point": "a", "tool": "pythia", "k": "progress", "done": 3, "total": 4},
        {"point": "a", "tool": "pythia", "k": "exit", "code": 0, "seconds": 1.5},
        {"point": "a", "tool": "", "k": "point", "state": "done", "t": 171.8},
        {"point": "", "tool": "", "k": "run", "state": "finished", "verdict": "1 done"},
    ]
    journal.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    captured = io.StringIO()
    monkeypatch.setattr("runner.watch.view", lambda plain=False: PlainView(stream=captured))
    assert follow(journal, plain=True) == 0
    text = captured.getvalue()
    assert "watching new" in text and "old" not in text
    assert "── point 1/1: a ── ok after 71.8 s" in text and "run finished: 1 done" in text
    assert "pythia: ok" not in text                                     # a tool that did its job says nothing


def test_a_point_is_one_block_when_it_ends():
    """── point 2/4: NNPDF23lo ── ok after 71.8 s, then where the results are (the user's layout)."""
    from types import SimpleNamespace
    from runner.execute import PointResult, ToolResult
    from runner.status import ToolState
    out = io.StringIO()
    view = PlainView(stream=out)
    view.begin(4)
    view.number = 1
    from runner.sweep import Point
    plan = SimpleNamespace(point=Point(index=2, name="NNPDF23lo"), res="results/x/NNPDF23lo")   # a real Point (L26)
    view.point_started(plan)
    view.tool_finished(ToolState(point="NNPDF23lo", tag="pythia"), ToolResult("pythia", exit=0, seconds=71.6))
    view.tool_finished(ToolState(point="NNPDF23lo", tag="sherpa:prepare"), ToolResult("sherpa:prepare", exit=0, seconds=3.0))
    view.point_finished(plan, PointResult(True))
    view.flush()                                                       # the view writes on its own thread (V32)
    lines = out.getvalue().splitlines()
    assert lines[0].startswith("── point 2/4: NNPDF23lo ── ok after ") and lines[0].endswith(" s")
    assert lines[1:] == ["   sherpa:prepare: ok after 3.0 s", "   done → results/x/NNPDF23lo"]
    view.point_started(plan)
    view.tool_finished(ToolState(point="NNPDF23lo", tag="rivet", error="boom"), ToolResult("rivet", exit=1, seconds=2.0))
    view.point_finished(plan, PointResult(False, cause="rivet", message="rivet exited 1"))
    view.flush()
    tail = out.getvalue().splitlines()[3:]
    assert "── FAILED [rivet] after" in tail[0] and tail[1:] == ["   rivet: exit 1 after 2.0 s  (boom)", "   rivet exited 1"]


def test_a_terminal_that_stops_reading_never_stops_the_run():
    """V32: the supervisor calls the view from its poll loop. A stream nobody reads (a paused terminal
    tab, Ctrl-S) fills after 64 kB; the view's calls must still return at once, and end() must not
    wait on it for more than its timeout."""
    import os
    import time
    read_end, write_end = os.pipe()
    stream = os.fdopen(write_end, "w")
    view = PlainView(stream=stream)
    started = time.monotonic()
    for i in range(5000):                                            # ~1 MB: far past the pipe's buffer
        view.say(f"line {i:05d} " + "x" * 200)
    assert time.monotonic() - started < 1.0
    started = time.monotonic()
    view.end()                                                        # gives up after its timeout
    assert time.monotonic() - started < 5.0
    os.close(read_end)                                                # the writer thread gets EPIPE and stops
