"""App_Pythia as a process (docs/05_Commands_and_Tools.md §16): what it refuses, the sidecar, codecs.

These run the real program on a small hard-QCD card: about a second each.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "build" / "App_Pythia.exe"

CARD = """\
Beams:eCM = 13000.
HardQCD:all = on
PhaseSpace:pTHatMin = 50.
Main:numberOfEvents = 40
Next:numberCount = 0
Random:setSeed = on
Random:seed = 4711
"""

pytestmark = pytest.mark.skipif(not APP.exists(), reason="build/App_Pythia.exe not built (make)")


def run(*args, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("HEP_STATUS_FD", None)
    return subprocess.run([str(APP), *map(str, args)], cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8", timeout=300)


@pytest.fixture
def card(scratch: Path) -> Path:
    path = scratch / "qcd.cmnd"
    path.write_text(CARD, encoding="utf-8")
    return path


def test_the_sidecar_says_what_was_written(scratch, card):
    result = run("events.hepmc", card, cwd=scratch)
    assert result.returncode == 0, result.stderr
    side = json.loads((scratch / "events.hepmc.json").read_text(encoding="utf-8"))
    assert set(side) >= {"requested", "attempted", "accepted", "written", "sigma_pb", "sigma_err_pb",
                         "sum_w", "threads", "seeds", "random_seed", "outputs", "cards", "stopped"}
    assert side["requested"] == 40 and side["written"] == side["accepted"] <= 40
    assert side["sigma_pb"] > 0 and side["stopped"] is False and side["random_seed"] == 4711
    events = (scratch / "events.hepmc").read_text(encoding="utf-8")
    assert events.count("\nE ") == side["written"]


def test_seeds_must_be_one_per_thread(scratch, card):
    result = run("--threads", 2, "--seeds", "5", "e.hepmc", card, cwd=scratch)
    assert result.returncode == 1
    assert "needs one per thread" in result.stderr
    assert not (scratch / "e.hepmc").exists()


def test_seeds_must_be_in_pythias_range(scratch, card):
    result = run("--threads", 1, "--seeds", "900000001", "e.hepmc", card, cwd=scratch)
    assert result.returncode == 1 and "outside Pythia's range" in result.stderr


def test_a_rejected_setting_writes_nothing(scratch, card):
    bad = scratch / "bad.cmnd"
    bad.write_text("NoSuch:setting = 3\n", encoding="utf-8")
    result = run("e.hepmc", card, bad, cwd=scratch)
    assert result.returncode == 1 and not (scratch / "e.hepmc").exists()


def test_usage_errors_exit_2(scratch):
    assert run("--bogus", "x", cwd=scratch).returncode == 2
    assert run("only-one-arg", cwd=scratch).returncode == 2


@pytest.mark.parametrize(("name", "magic"), [("e.hepmc.gz", b"\x1f\x8b"), ("e.hepmc.zst", b"\x28\xb5\x2f\xfd")])
def test_the_suffix_picks_the_codec(scratch, card, name, magic):
    result = run(name, card, cwd=scratch)
    assert result.returncode == 0, result.stderr
    assert (scratch / name).read_bytes()[:len(magic)] == magic


def events_of(path: Path) -> dict[int, list[str]]:
    """Each event's lines by its number, without its σ line."""
    events: dict[int, list[str]] = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("E "):
            current = int(line.split()[1])
            events[current] = [line]
        elif line.startswith("HepMC::"):
            current = None
        elif current is not None and " GenCrossSection " not in line:
            events[current].append(line)
    return events


def test_fan_out_writes_the_same_events_everywhere(scratch, card):
    """V16: every output gets every event. Not byte for byte: callbacks run in parallel and each output
    has its own writer (V31), so two outputs may take the same events in another order, and each
    output's last event carries the latest σ (L28)."""
    result = run("a.hepmc,b.hepmc", card, cwd=scratch)
    assert result.returncode == 0, result.stderr
    a, b = events_of(scratch / "a.hepmc"), events_of(scratch / "b.hepmc")
    assert a and a == b


def event_numbers(path: Path) -> list[int]:
    return [int(line.split()[1]) for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("E ")]


def test_a_deal_group_splits_the_events_and_counts_each_share(scratch, card):
    """V31: `a+b,c`: every event goes to one of a and b, and to c. The sidecar counts each output, and
    the events are numbered once across the threads, from 0."""
    (scratch / "more.cmnd").write_text("Main:numberOfEvents = 400\n", encoding="utf-8")
    result = run("--threads", 4, "--seeds", "11,12,13,14", "a.hepmc+b.hepmc,c.hepmc", card, scratch / "more.cmnd",
                 cwd=scratch)
    assert result.returncode == 0, result.stderr
    side = json.loads((scratch / "a.hepmc.json").read_text(encoding="utf-8"))
    counts = side["written_per_output"]
    assert counts["a.hepmc"] + counts["b.hepmc"] == side["written"] == counts["c.hepmc"]
    assert counts["a.hepmc"] > 0 and counts["b.hepmc"] > 0
    a, b, c = (event_numbers(scratch / f"{n}.hepmc") for n in "abc")
    assert (len(a), len(b)) == (counts["a.hepmc"], counts["b.hepmc"])
    assert not set(a) & set(b) and sorted(a + b) == sorted(c) == list(range(side["written"]))
    assert side["outputs"] == ["a.hepmc", "b.hepmc", "c.hepmc"]


def last_sigma(path: Path) -> str:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if " GenCrossSection " in line][-1]


def test_every_output_ends_on_the_same_sigma(scratch, card):
    """L2 per output (L28): a CLI Rivet takes σ from the last event it reads, so every member of a deal
    group, and every copy output, ends on the σ of the last event stamped, not on an older running one."""
    (scratch / "more.cmnd").write_text("Main:numberOfEvents = 400\n", encoding="utf-8")
    result = run("--threads", 4, "--seeds", "11,12,13,14", "a.hepmc+b.hepmc+d.hepmc,c.hepmc", card,
                 scratch / "more.cmnd", cwd=scratch)
    assert result.returncode == 0, result.stderr
    ends = {n: last_sigma(scratch / f"{n}.hepmc") for n in "abcd"}
    assert len(set(ends.values())) == 1, ends
