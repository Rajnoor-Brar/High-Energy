"""V31, the gate: a point whose Rivet is sharded gives the same result as the same point unsharded
(slow: real Pythia and Rivet).

The two configurations share the generator set-up, so the same seeds and events (V22); the sharded
one deals them among four Rivet processes and merges with `rivet-merge -e`. The raw histograms must
be the same sums, and the cross section the same: every shard ends on the σ of the last event
App_Pythia stamped, the one the unsharded Rivet read (L28).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from support import hep_ok
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
    return hep_ok(scratch, *args)


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
    assert xs_four == pytest.approx(xs_one, rel=1e-9)                        # was 2e-4 off before L28
    for path, histo in one.items():
        if not path.startswith("/RAW/photo_eic/") or not hasattr(histo, "sumW"):
            continue
        assert histo.sumW() == pytest.approx(four[path].sumW(), rel=1e-9), path    # the same events, summed
    shards = sorted((scratch / "output/PhotoProduction/shards/four/point/shards").glob("photo.s*.yoda"))
    assert len(shards) == 4
