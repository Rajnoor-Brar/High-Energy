"""V36, the gate (slow: real runs): `parallelism = 4` gives every point the result it gets one at a
time; a failing point leaves the others to finish; Ctrl-C stops the running points (exit 6, no
.complete) and starts no more."""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HEP = REPO / "utils" / "Env" / "hep"
yoda = pytest.importorskip("yoda")

pytestmark = pytest.mark.slow

PHYSICS = """\
[run]
name          = "par"
project       = "PhotoProduction"
configuration = "one"
event_count   = 2000
threads       = 2

[run.one]
sweeps = ["pdf", "replica"]
tools  = [["pythia", "rivet"]]

[prelim]
fifo = ["events.hepmc"]

[tools.pythia]
tool        = "pythia"
baseconfig  = "photo_ep.cmnd"
output_file = "events.hepmc"

[tools.rivet]
tool        = "rivet"
input       = "events.hepmc"
analyses    = ["photo_eic"]
output_file = "photo.yoda"

[quantities.pdf]
values = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_nlo_as_0119_qed"]
tags   = ["MSTW08lo", "NNPDF23nlo"]

[quantities.replica]
target = "pythia/seed"
values = [1, 2]
tags   = ["s1", "s2"]
"""

CHECK = """#!/usr/bin/env python3
import sys, time, tomllib
config = tomllib.load(open(sys.argv[1], "rb"))
time.sleep(config.get("sleep", 0))
sys.exit(config.get("quantities", {}).get("fail", 0))       # consumed quantities go under [quantities]
"""


def run(config: Path, where: Path, *args: str, wait: bool = True):
    env = dict(os.environ, HEKIT_OUTPUT=str(where / "output"), HEKIT_RESULTS=str(where / "results"))
    argv = [str(HEP), "run", str(config), "--plain", *args]
    if not wait:
        return subprocess.Popen(argv, cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8")
    return subprocess.run(argv, cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=1800)


def checker(scratch: Path, sweep: str, extra: str = "") -> Path:
    script = scratch / "check.py"
    script.write_text(CHECK, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    config = scratch / "check.toml"
    config.write_text(f"""\
[run]
name          = "chk"
project       = "PhotoProduction"
configuration = "one"
event_count   = 1
parallelism   = 3

[run.one]
sweeps = ["{sweep}"]
tools  = ["check"]

[tools.check]
tool       = "custom"
executable = "{script}"
consumes   = ["fail"]
{extra}
[quantities.fail]
values = [0, 1, 0, 0]
tags   = ["a", "b", "c", "d"]
""", encoding="utf-8")
    return config


def test_four_at_once_give_every_point_its_one_at_a_time_result(scratch):
    config = scratch / "par.toml"
    config.write_text(PHYSICS, encoding="utf-8")
    one = run(config, scratch / "one")
    four = run(config, scratch / "four", "--set", "run.parallelism=4")
    assert one.returncode == 0 and four.returncode == 0, four.stdout[-2000:]
    assert "4 at once" in four.stdout and four.stdout.count(" ── ok after ") == 4
    for point in ("MSTW08lo_s1", "MSTW08lo_s2", "NNPDF23nlo_s1", "NNPDF23nlo_s2"):
        a, b = (yoda.read(str(where / "results" / "PhotoProduction" / "par" / "one" / point / "photo.yoda"))
                for where in (scratch / "one", scratch / "four"))
        assert a["/_XSEC"].val() == b["/_XSEC"].val(), point
        for path, histo in a.items():
            if path.startswith("/RAW/") and hasattr(histo, "sumW"):
                assert b[path].sumW() == pytest.approx(histo.sumW(), rel=1e-12), (point, path)


def test_a_failing_point_leaves_the_others_to_finish(scratch):
    done = run(checker(scratch, "fail"), scratch)
    assert done.returncode == 1, done.stdout[-2000:]
    assert "3 done, 1 failed" in done.stdout and "FAILED [check]" in done.stdout
    base = scratch / "output" / "PhotoProduction" / "chk" / "one"
    assert sorted(p.name for p in base.glob("*/.complete") for p in [p.parent]) == ["a", "c", "d"]


def test_ctrl_c_stops_the_running_points_and_starts_no_more(scratch):
    runner = run(checker(scratch, "fail", extra="[tools.check.config]\nsleep = 60\n"), scratch, wait=False)
    journal = scratch / "output" / "PhotoProduction" / "chk" / "one" / "status.jsonl"
    deadline = time.monotonic() + 60
    started: list[str] = []
    while time.monotonic() < deadline and len(started) < 3:
        if journal.exists():
            started = [m["point"] for m in map(json.loads, journal.read_text(encoding="utf-8").splitlines())
                       if m.get("k") == "point" and m.get("state") == "started"]
        time.sleep(0.2)
    assert len(started) == 3, started                         # parallelism 3 of 4 points
    time.sleep(1.0)
    runner.send_signal(signal.SIGINT)
    stopped = time.monotonic()
    text, _ = runner.communicate(timeout=60)
    assert runner.returncode == 6, text
    assert time.monotonic() - stopped < 20
    assert text.count(" ── stopped after ") == 3
    base = scratch / "output" / "PhotoProduction" / "chk" / "one"
    assert not list(base.glob("*/.complete"))
    assert "d" not in started                                 # the fourth never started
