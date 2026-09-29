"""Failure injection on a real App_Pythia ══FIFO══► rivet chain (P1 S2 rows 3–5, R2).

A FIFO chain must never hang and never leave a partial result looking complete:
* the producer killed mid-stream → rivet sees EOF, but the point fails and keeps `.partial`;
* the producer failing init while rivet blocks at open → no hang, pythia blamed;
* the consumer killed → pythia gets SIGPIPE, rivet blamed;
* Ctrl-C → exit 6, the point partial, the second run resumes it.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HEP = REPO / "utils" / "Env" / "hep"

pytestmark = [pytest.mark.slow,
              pytest.mark.skipif(not (REPO / "build" / "App_Pythia.exe").exists(), reason="make first")]


def write_config(where: Path, *, events: int, extra_base: str = "") -> str:
    base = '"photo_ep.cmnd"' if not extra_base else f'["photo_ep.cmnd", "{extra_base}"]'
    (where / "f.toml").write_text(f"""
[run]
name = "fail"
project = "PhotoProduction"
configuration = "one"
event_count = {events}
threads = 1
[run.one]
tools = [["pythia", "rivet"]]
[prelim]
fifo = ["events.hepmc"]
[tools.pythia]
tool = "pythia"
baseconfig = {base}
output_file = "events.hepmc"
[tools.rivet]
tool = "rivet"
input = "events.hepmc"
analyses = ["photo_eic"]
output_file = "photo.yoda"
""", encoding="utf-8")
    return "./" + str((where / "f.toml").resolve().relative_to(REPO))


def point_dirs(where: Path) -> tuple[Path, Path]:
    tail = Path("PhotoProduction") / "fail" / "one" / "point"
    return where / "output" / tail, where / "results" / tail


def start(config: str, where: Path) -> subprocess.Popen:
    env = dict(os.environ, HEKIT_RESULTS=str(where / "results"), HEKIT_OUTPUT=str(where / "output"))
    return subprocess.Popen([str(HEP), "run", config], cwd=REPO, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8")


def wait_for_progress(out: Path, tool: str, timeout: float = 120) -> None:
    journal = out.parent / "status.jsonl"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if journal.exists():
            for line in journal.read_text(encoding="utf-8").splitlines():
                message = json.loads(line)
                if message.get("tool") == tool and message.get("k") == "progress" and (message.get("done") or 0) > 200:
                    return
        time.sleep(0.5)
    raise AssertionError(f"no progress from {tool} within {timeout} s")


def pid_of(pattern: str) -> int:
    out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, encoding="utf-8").stdout.split()
    assert out, f"no process matches {pattern}"
    return int(out[0])


def test_the_producer_killed_mid_stream_fails_the_point_and_keeps_partial(scratch):
    runner = start(write_config(scratch, events=40000), scratch)
    out, res = point_dirs(scratch)
    wait_for_progress(out, "pythia")
    os.kill(pid_of(f"App_Pythia.exe {out}"), signal.SIGKILL)
    killed = time.monotonic()
    text, _ = runner.communicate(timeout=120)
    assert runner.returncode == 1, text
    assert time.monotonic() - killed < 30
    assert "FAILED [pythia]" in text and "SIGKILL" in text
    assert not (out / ".complete").exists() and not (res / "photo.yoda").exists()


def test_init_failure_with_the_reader_blocked_at_open_does_not_hang(scratch):
    bad = scratch / "bad.cmnd"
    bad.write_text("PDF:pSet = LHAPDF6:NoSuchPdfSet\n", encoding="utf-8")
    started = time.monotonic()
    runner = start(write_config(scratch, events=1000, extra_base="./" + str(bad.resolve().relative_to(REPO))), scratch)
    text, _ = runner.communicate(timeout=120)
    assert runner.returncode == 1, text
    assert "FAILED [pythia]" in text and "exit code 3" in text
    assert time.monotonic() - started < 60                     # init + grace + SIGTERM, never "for ever"
    out, res = point_dirs(scratch)
    assert not (out / ".complete").exists()


def test_the_consumer_killed_is_blamed_not_the_producer(scratch):
    runner = start(write_config(scratch, events=40000), scratch)
    out, res = point_dirs(scratch)
    wait_for_progress(out, "rivet")
    os.kill(pid_of(f"rivet -o {res}"), signal.SIGKILL)
    text, _ = runner.communicate(timeout=120)
    assert runner.returncode == 1, text
    assert "FAILED [rivet]" in text
    assert not (out / ".complete").exists()


def test_ctrl_c_stops_with_6_and_the_next_run_resumes(scratch):
    config = write_config(scratch, events=40000)
    runner = start(config, scratch)
    out, res = point_dirs(scratch)
    wait_for_progress(out, "pythia")
    runner.send_signal(signal.SIGINT)
    text, _ = runner.communicate(timeout=120)
    assert runner.returncode == 6, text
    assert "stopped" in text
    assert not (out / ".complete").exists() and not (res / "photo.yoda").exists()
