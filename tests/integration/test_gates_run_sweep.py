"""V38, the gate (slow: real `hep run` processes): under `[run].sweep_runs = true` the swept
configurations run one after another, each exactly the run `hep run CONFIG <cfg>` makes, after a
`run NN - <title> -` line; `swept = false` leaves one out; a failed run leaves the next to start; a
config error anywhere stops everything before it starts; Ctrl-C starts no more runs."""

from __future__ import annotations

import json
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest

import support
from support import HEP, REPO, env

pytestmark = pytest.mark.slow

CHECK = """#!/usr/bin/env python3
import sys, time, tomllib
wanted = tomllib.load(open(sys.argv[1], "rb")).get("quantities", {})
time.sleep(wanted.get("nap", 0))
sys.exit(wanted.get("fail", 0))
"""


def sweep_config(scratch: Path, d_static: str = "{}", b_nap: str = "no") -> Path:
    script = scratch / "check.py"
    script.write_text(CHECK, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    config = scratch / "sw.toml"
    config.write_text(f"""\
[run]
name        = "sw"
project     = "PhotoProduction"
sweep_runs  = true
event_count = 1

[run.a]
tools = ["check"]

[run.b]
title  = "Bee"
tools  = ["check"]
static = {{ fail = "bad", nap = "{b_nap}" }}

[run.c]
swept = false
tools = ["check"]

[run.d]
tools  = ["check"]
static = {d_static}

[static]
fail = "ok"
nap  = "no"

[tools.check]
tool       = "custom"
executable = "{script}"
consumes   = ["fail", "nap"]

[quantities.fail]
values = [0, 1]
tags   = ["ok", "bad"]

[quantities.nap]
values = [0, 60]
tags   = ["no", "yes"]
""", encoding="utf-8")
    return config


def hep(config: Path, where: Path, *args: str) -> subprocess.CompletedProcess:
    return support.hep(where, config, "--journal", *args, timeout=600)       # the tests read its events (V72)


def base(where: Path) -> Path:
    return where / "output" / "PhotoProduction" / "sw"


def records(journal: Path) -> list[dict]:
    return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]


def test_the_swept_configurations_run_one_after_another(scratch):
    config = sweep_config(scratch)
    done = hep(config, scratch)
    assert done.returncode == 1, done.stdout[-2000:] + done.stderr[-2000:]
    out = done.stdout
    assert out.index("run 01 - a -") < out.index("run 02 - Bee -") < out.index("run 03 - d -")
    assert "FAILED [check]" in out and "run 04" not in out
    assert not (base(scratch) / "c").exists()                          # swept = false
    assert [p.parent.parent.name for p in sorted(base(scratch).glob("*/*/.complete"))] == ["a", "d"]
    first = records(base(scratch) / "a" / "status.jsonl")
    assert first[-1]["k"] == "run" and first[-1]["next"] == str(base(scratch) / "b" / "status.jsonl")
    assert records(base(scratch) / "b" / "status.jsonl")[-1]["next"] == str(base(scratch) / "d" / "status.jsonl")
    assert "next" not in records(base(scratch) / "d" / "status.jsonl")[-1]
    alone = hep(config, scratch, "d")                                  # the very run `hep run sw d` makes
    assert alone.returncode == 0 and "complete, skipped" in alone.stdout and "run 0" not in alone.stdout


def test_a_config_error_anywhere_runs_nothing(scratch):
    done = hep(sweep_config(scratch, d_static='{ fail = "nosuch" }'), scratch)
    assert done.returncode == 2, done.stdout[-2000:]
    assert "configuration 'd'" in done.stderr
    assert not base(scratch).exists() or not list(base(scratch).glob("*/*/.complete"))


def test_points_belong_to_one_configuration(scratch):
    done = hep(sweep_config(scratch), scratch, "--points", "1")
    assert done.returncode == 2 and "--points picks points of one configuration" in done.stderr


def test_ctrl_c_starts_no_more_runs(scratch):
    config = sweep_config(scratch, b_nap="yes")                        # b sleeps a minute …
    text = config.read_text(encoding="utf-8")                          # … on the first of two points, one at a
    text = text.replace('title  = "Bee"\n', 'title  = "Bee"\nsweeps = ["twice"]\n')   # time: its run has not
    text = text.replace('consumes   = ["fail", "nap"]', 'consumes   = ["fail", "nap", "twice"]')   # started all its
    config.write_text(text + '\n[quantities.twice]\nvalues = [1, 2]\n', encoding="utf-8")       # points (V75)
    runner = subprocess.Popen([str(HEP), "run", str(config), "--plain", "--journal"], cwd=REPO, env=env(scratch),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    journal = base(scratch) / "b" / "status.jsonl"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and not (journal.exists() and any(
            m.get("k") == "point" and m.get("state") == "started" for m in records(journal))):
        time.sleep(0.2)
    time.sleep(1.0)
    runner.send_signal(signal.SIGINT)
    text, _ = runner.communicate(timeout=60)
    assert runner.returncode == 6, text
    assert "run 02 - Bee -" in text and "run 03" not in text
    assert not (base(scratch) / "d").exists()
    assert "next" not in records(journal)[-1]


PIPE = """\
[run]
name        = "pipe"
project     = "PhotoProduction"
sweep_runs  = true
event_count = 1
parallelism = 2

[run.x]
sweeps = ["slot"]
tools  = ["check"]

[run.y]
sweeps = ["slot"]
tools  = ["check"]

[static]
fail = "ok"
nap  = "two"

[tools.check]
tool       = "custom"
executable = "{script}"
consumes   = ["fail", "nap", "slot"]

[quantities.slot]
values = [1, 2, 3]

[quantities.fail]
values = [0]
tags   = ["ok"]

[quantities.nap]
values = [2]
tags   = ["two"]
"""


def test_a_sweep_of_runs_is_pipelined(scratch):
    """V75 (B8, option B): run y starts its points once run x has started all of its own, in the slot
    x's last wave leaves free: three 2 s points a run, two at once, overlap across the runs."""
    script = scratch / "check.py"
    script.write_text(CHECK, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    config = scratch / "pipe.toml"
    config.write_text(PIPE.format(script=script), encoding="utf-8")
    done = hep(config, scratch)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    root = scratch / "output" / "PhotoProduction" / "pipe"
    x, y = (records(next(root.glob(f"*{k}/status.jsonl"))) for k in ("x", "y"))
    assert all(r.get("run") == "x" for r in x) and all(r.get("run") == "y" for r in y)   # each journal its own run's
    x_last_end = max(r["t"] for r in x if r.get("k") == "point" and r.get("state") == "done")
    y_first_start = min(r["t"] for r in y if r.get("k") == "point" and r.get("state") == "started")
    assert y_first_start < x_last_end - 1.0, (y_first_start, x_last_end)
    assert "── point 1/3 (y): " in done.stdout and "run 02 - y -" in done.stdout
