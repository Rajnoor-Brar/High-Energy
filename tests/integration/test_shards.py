"""V31, the gate: a point whose Rivet is sharded gives the same result as the same point unsharded
(slow: real Pythia and Rivet).

The two configurations share the generator set-up, so the same seeds and events (V22); the sharded
one deals them among four Rivet processes and merges with `rivet-merge -e`. The raw histograms must
be the same sums, the finalised ones the same up to the cross section each run normalised to, and
that cross section the same to the precision the last events carry.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
yoda = pytest.importorskip("yoda")

pytestmark = pytest.mark.slow

RUN = """\
[run]
name          = "shards"
project       = "PhotoProduction"
configuration = "one"
event_count   = 4000
threads       = 4

[run.one]
tools = [["pythia", "rivet"]]

[run.four]
tools = [["pythia", "rivet4"]]

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

[tools.rivet4]
tool        = "rivet"
input       = "events.hepmc"
analyses    = ["photo_eic"]
output_file = "photo.yoda"
shards      = 4
"""


def hep_run(scratch: Path, *args: str) -> str:
    env = dict(os.environ, HEKIT_OUTPUT=str(scratch / "output"), HEKIT_RESULTS=str(scratch / "results"))
    done = subprocess.run(["python3", str(REPO / "utils" / "Env" / "run"), "run", *args, "--plain"], env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    return done.stdout


def test_a_sharded_point_equals_the_same_point_unsharded(scratch):
    config = scratch / "shards.toml"
    config.write_text(RUN, encoding="utf-8")
    hep_run(scratch, str(config), "one")
    hep_run(scratch, str(config), "four")
    one = yoda.read(str(scratch / "results/PhotoProduction/shards/one/point/photo.yoda"))
    four = yoda.read(str(scratch / "results/PhotoProduction/shards/four/point/photo.yoda"))
    assert set(one) == set(four)
    raw_one, raw_four = one["/RAW/_EVTCOUNT"], four["/RAW/_EVTCOUNT"]
    assert raw_one.numEntries() == raw_four.numEntries() and raw_one.sumW() == pytest.approx(raw_four.sumW(), rel=1e-12)
    xs_one, xs_four = one["/_XSEC"].val(), four["/_XSEC"].val()
    assert xs_four == pytest.approx(xs_one, rel=1e-3)
    for path, histo in one.items():
        if not path.startswith("/RAW/photo_eic/") or not hasattr(histo, "sumW"):
            continue
        assert histo.sumW() == pytest.approx(four[path].sumW(), rel=1e-9), path    # the same events, summed
    shards = sorted((scratch / "output/PhotoProduction/shards/four/point/shards").glob("photo.s*.yoda"))
    assert len(shards) == 4
