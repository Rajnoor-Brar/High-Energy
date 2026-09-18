"""The status stream, read by the Python half (P2-S03).

The interesting test is the round trip: `test_status_roundtrip --emit` writes one message of every kind
on fd 3, and this parses that exact stream. Two copies of the same assumption would agree with each
other; the binary and the reader agreeing means the protocol works.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

import pytest

from hekit.run.status import KINDS, Message, StatusReader, parse_line, read

REPO = Path(__file__).resolve().parents[3]
WRITER = REPO / "build" / "bin" / "test_status_roundtrip"


# ── parsing ──────────────────────────────────────────────────────────────────

def test_a_line_becomes_a_message():
    message = parse_line('{"t":1758103203.1,"k":"phase","phase":"init","detail":"reading 2 cards"}')
    assert message is not None
    assert message.kind == "phase" and message.known and message.ok
    assert message.time == 1758103203.1
    assert message["phase"] == "init" and message.get("detail") == "reading 2 cards"


def test_a_blank_line_is_nothing():
    assert parse_line("") is None and parse_line("   \n") is None


def test_an_unknown_kind_is_kept_and_flagged():
    """A newer hep-run must be able to say something an older hep does not know."""
    message = parse_line('{"t":1.0,"k":"quark","flavour":"charm"}')
    assert message.kind == "quark" and not message.known and message.ok
    assert message["flavour"] == "charm"


def test_garbled_lines_are_reported_not_dropped():
    for text in ("{not json", "[1, 2, 3]", "null"):
        message = parse_line(text)
        assert message.error and message.kind == "garbled"
        assert message.raw == text


def test_a_message_without_a_kind_is_an_error():
    assert parse_line('{"t":1.0}').error == "no 'k' field"


def test_reading_a_stream_keeps_the_order():
    lines = ['{"t":1,"k":"phase","phase":"a"}', "", '{"t":2,"k":"heartbeat"}']
    assert [message.kind for message in read(lines)] == ["phase", "heartbeat"]


# ── folding into state ───────────────────────────────────────────────────────

def test_the_reader_folds_a_run(tmp_path):
    lines = [
        '{"t":1.0,"k":"phase","phase":"init","detail":"reading 2 cards"}',
        '{"t":1.1,"k":"init","beam_ids":[2212,11],"beam_energies":[41,5],"sqrt_s":28.64,'
        '"threads":2,"mode":"serial","sinks":["rivet"]}',
        '{"t":2.0,"k":"progress","done":500,"total":1000,"rate":250.0,"workers":[250,250]}',
        '{"t":2.5,"k":"xsec","value_pb":71422.16,"err_pb":95.0,"final":false}',
        '{"t":2.6,"k":"log","level":"warn","source":"pythia","msg":"stuck in loop"}',
        '{"t":2.7,"k":"log","level":"info","source":"rivet","msg":"loaded photo_eic"}',
        '{"t":2.8,"k":"checkpoint","done":500,"outputs":["analysis.partial.yoda"]}',
        '{"t":2.9,"k":"heartbeat"}',
        '{"t":3.0,"k":"summary","events":1000,"xsec_pb":71422.16,"err_pb":55,"stopped":false}',
    ]
    reader = StatusReader().feed_lines(lines)
    assert reader.phase == "init" and reader.detail == "reading 2 cards"
    assert reader.beams == {"ids": [2212, 11], "energies": [41, 5], "sqrt_s": 28.64}
    assert (reader.threads, reader.mode, reader.sinks) == (2, "serial", ["rivet"])
    assert (reader.done, reader.total, reader.rate) == (500, 1000, 250.0)
    assert reader.workers == [250, 250]
    assert reader.fraction == 0.5 and reader.eta_seconds() == 2.0
    assert reader.xsec_pb == 71422.16 and not reader.xsec_final
    assert len(reader.logs) == 2 and len(reader.warnings) == 1
    assert reader.checkpoints == [{"done": 500, "outputs": ["analysis.partial.yoda"]}]
    assert reader.heartbeats == 1
    assert reader.summary["events"] == 1000 and not reader.stopped
    assert reader.last_time == 3.0


def test_unknown_and_garbled_are_collected_separately():
    reader = StatusReader().feed_lines(['{"t":1,"k":"quark"}', "{oops", '{"t":2,"k":"heartbeat"}'])
    assert [message.kind for message in reader.unknown] == ["quark"]
    assert len(reader.garbled) == 1
    assert reader.heartbeats == 1, "the stream keeps working after a bad line"


def test_eta_is_none_when_it_cannot_be_known():
    reader = StatusReader()
    assert reader.eta_seconds() is None                      # nothing started
    reader.feed_lines(['{"t":1,"k":"progress","done":10,"total":10,"rate":5}'])
    assert reader.eta_seconds() is None                      # already done


def test_a_stopped_run_says_so():
    reader = StatusReader().feed_lines(['{"t":1,"k":"summary","events":5,"stopped":true}'])
    assert reader.stopped


def test_every_kind_has_a_handler():
    reader = StatusReader()
    for kind in KINDS:
        assert hasattr(reader, f"_on_{kind}"), kind


# ── the round trip with the C++ writer ───────────────────────────────────────

@pytest.mark.skipif(not WRITER.is_file(), reason="build the C++ tests first (cmake --build build)")
def test_the_cpp_writer_and_the_python_reader_agree(tmp_path):
    stream = tmp_path / "status.jsonl"
    # fd 3 has to *be* fd 3 in the child, which pass_fds does not promise; a shell redirect does.
    # The supervisor (P3-S02) will instead tell the child which descriptor to use via [status].fd.
    done = subprocess.run(["sh", "-c", f'exec 3>{shlex.quote(str(stream))}; exec "$0" --emit',
                           str(WRITER)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    lines = stream.read_text(encoding="utf-8").splitlines()
    assert lines, "the writer wrote nothing to fd 3"

    messages = list(read(lines))
    assert all(message.ok for message in messages), [m.error for m in messages if m.error]
    assert all(message.known for message in messages), [m.kind for m in messages if not m.known]
    kinds = [message.kind for message in messages]
    assert kinds == ["phase", "init", "progress", "xsec", "log", "log", "checkpoint", "heartbeat",
                     "summary"]
    assert all(message.time > 0 for message in messages), "every message carries a timestamp"

    reader = StatusReader().feed_lines(lines)
    assert reader.phase == "init"
    assert reader.beams["ids"] == [2212, 11] and reader.beams["energies"] == [41.0, 5.0]
    assert reader.threads == 2 and reader.sinks == ["rivet", "store"]
    assert (reader.done, reader.total) == (500, 1000)
    assert reader.workers == [250, 250]
    assert reader.xsec_pb == 71422.16
    assert reader.summary["events"] == 1000
    assert reader.heartbeats == 1

    # the escaping survives a tool's message verbatim
    error = next(entry for entry in reader.logs if entry["level"] == "error")
    assert error["msg"] == 'quote " backslash \\ newline\nend'


@pytest.mark.skipif(not WRITER.is_file(), reason="build the C++ tests first")
def test_without_fd_3_the_writer_falls_back_to_stderr():
    """Running hep-run by hand has to stay readable: plain lines, no JSON."""
    done = subprocess.run([str(WRITER), "--emit"], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0
    assert "init: reading 2 cards" in done.stderr
    assert "[ 50%] 500/1000" in done.stderr
    assert "{" not in done.stderr, "plain mode must not emit JSON"
