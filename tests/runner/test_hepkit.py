"""utils/hepkit.py (V74): the kit for a custom tool in Python — the status protocol, the report, the
exit codes (the same table as utils/Kit.hh's), and a tool that uses it under the runner's Reader."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "utils"))
import hepkit  # noqa: E402


def test_the_exit_table_is_kit_hh_s():
    text = (REPO / "utils" / "Kit.hh").read_text(encoding="utf-8")
    table = dict(re.findall(r"(\w+) = (\d+)", re.search(r"enum Exit : int \{([^}]*)\}", text).group(1)))
    assert {name.upper(): int(code) for name, code in table.items()} == {e.name: e.value for e in hepkit.Exit}


def test_status_writes_the_standard_protocol(monkeypatch):
    read, write = os.pipe()
    monkeypatch.setenv("HEP_STATUS_FD", str(write))
    status = hepkit.Status(beat=0, signals=False)
    status.phase("reading", "x.root")
    status.progress(5, 10, 2.5, force=True)
    status.progress(6, 10, 2.5)                                   # rate-limited: dropped quietly
    status.summary(events=10)
    os.close(write)
    lines = [json.loads(line) for line in os.read(read, 65536).decode().splitlines()]
    os.close(read)
    assert [m["k"] for m in lines] == ["phase", "progress", "summary"]
    assert lines[0]["detail"] == "x.root" and lines[1]["done"] == 5 and lines[2]["events"] == 10


def test_without_the_fd_it_prints_plain_lines(monkeypatch, capsys):
    monkeypatch.delenv("HEP_STATUS_FD", raising=False)
    status = hepkit.Status(beat=0, signals=False)
    status.log("warn", "careful")
    assert not status.structured and "warn: careful" in capsys.readouterr().err


def test_a_report_is_written_whole(scratch):
    path = hepkit.report(scratch / "jets.json", events=3)
    assert path.name == "jets.json.json" and json.loads(path.read_text())["events"] == 3
    assert not list(scratch.glob("*.part"))


def test_usage_exits_two(capsys):
    with pytest.raises(SystemExit) as stop:
        hepkit.usage("usage: x")
    assert stop.value.code == hepkit.Exit.USAGE == 2
