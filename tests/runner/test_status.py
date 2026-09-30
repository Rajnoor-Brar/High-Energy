"""Status: the fd protocol, the filter rules, the journal, and `hep watch` following it."""

from __future__ import annotations

import io
import json
import os

import pytest

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
    assert "── point 1/1: a ── ok after 1min 12s" in text and "run finished: 1 done" in text
    assert "pythia: ok" not in text                                     # a tool that did its job says nothing


def test_a_point_is_one_block_when_it_ends():
    """── point 2/4: NNPDF23lo ── ok after 1min 12s, then where the results are (the user's layout)."""
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
    assert lines[0].startswith("── point 2/4: NNPDF23lo ── ok after ") and lines[0].endswith("s")
    assert lines[1:] == ["   sherpa:prepare: ok after 3.0s", "   done → results/x/NNPDF23lo"]
    view.point_started(plan)
    view.tool_finished(ToolState(point="NNPDF23lo", tag="rivet", error="boom"), ToolResult("rivet", exit=1, seconds=2.0))
    view.point_finished(plan, PointResult(False, cause="rivet", message="rivet exited 1"))
    view.flush()
    tail = out.getvalue().splitlines()[3:]
    assert "── FAILED [rivet] after" in tail[0] and tail[1:] == ["   rivet: exit 1 after 2.0s  (boom)", "   rivet exited 1"]


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


@pytest.mark.parametrize("seconds, shown", [(3.04, "3.0s"), (59.9, "59.9s"), (59.96, "1min 0s"), (71.8, "1min 12s"),
                                            (3599.6, "1h 0min 0s"), (10687.2, "2h 58min 7s")])
def test_durations_are_seconds_then_minutes_then_hours(seconds, shown):
    from runner.watch import duration
    assert duration(seconds) == shown


@pytest.mark.parametrize("seconds, shown", [(3.7, "00:03"), (72, "01:12"), (3599.9, "59:59"), (3600, "01:00:00"),
                                            (35237, "09:47:17"), (370929, "103:02:09"), (-1, "00:00")])
def test_a_running_clock_is_mm_ss_then_hh_mm_ss(seconds, shown):
    from runner.watch import clock
    assert clock(seconds) == shown


def test_the_live_view_puts_each_running_point_over_its_tools():
    """A blank line after the finished blocks, the point's heading and time so far, then its tools
    under it, their columns lined up across points."""
    pytest.importorskip("rich")
    from types import SimpleNamespace
    from rich.console import Console
    from runner.sweep import Point
    from runner.watch import LiveView
    view = LiveView()
    try:
        view.begin(4)
        view.number = 2
        for index, name in ((3, "MSTW08lo"), (4, "PDF4LHC21")):
            view.point_started(SimpleNamespace(point=Point(index=index, name=name), res=f"results/x/{name}"))
        view.points["PDF4LHC21"].started -= 35237
        view.tool_started(ToolState(point="MSTW08lo", tag="pythia", phase="init"))
        view.tool_started(ToolState(point="PDF4LHC21", tag="pythia", phase="generating", done=1_700_000,
                                    total=10_000_000, rate=2812))
        view.tool_started(ToolState(point="PDF4LHC21", tag="rivet.12", phase="analysing", done=1_700_000))
        out = io.StringIO()
        Console(file=out, width=120).print(view.render([]))
    finally:
        view.end()
    lines = [line.rstrip() for line in out.getvalue().splitlines()]
    assert lines[0] == "" and lines[1].startswith("point 3/4: MSTW08lo · 00:0")
    assert lines[2].startswith("   pythia   init ")
    assert lines[3] == "" and lines[4].startswith("point 4/4: PDF4LHC21 · 09:47:1")
    assert lines[5].startswith("   pythia   generating ") and lines[5].endswith("1.70M/10.00M 2,812/s 49:11")
    assert lines[6].startswith("   rivet.12 analysing  ") and lines[6].endswith("1.70M")
    assert lines[5].index("1.70M") == lines[6].index("1.70M") and lines[2].index("init") == lines[5].index("generating")
