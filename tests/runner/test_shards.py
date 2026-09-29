"""`shards = K` on a table (V31), at plan time: the table becomes K copies in its group, each reading
its share of the events from a FIFO the producer deals to, and the folder's merge tool writes the
table's own output in the next group. The events do not change: seeds follow the generator's cards,
not its argv."""

from __future__ import annotations

import pytest

from runner import plot, record
from runner.errors import HepError

from helpers import plan, raw


def sharded(k: int = 4, **changes):
    return raw(tools__rivet__shards=k, **changes)


def test_a_sharded_rivet_is_k_copies_and_a_merge(scratch):
    _, _, p = plan(sharded(4), scratch)
    assert [[s.tag for s in group] for group in p.groups] == [["pythia", "rivet.1", "rivet.2", "rivet.3", "rivet.4"],
                                                            ["rivet.merge"]]
    members = [p.out / f"events.s{i}.hepmc" for i in range(1, 5)]
    assert p.rendered["pythia"].argv[1] == "+".join(map(str, members))       # one deal group: App_Pythia's A+B+C
    assert p.prelim["fifo"] == [f"events.s{i}.hepmc" for i in range(1, 5)]    # the dealt FIFO is gone
    for i, member in enumerate(members, start=1):
        step = p.rendered[f"rivet.{i}"]
        assert step.argv[-1] == str(member)
        assert step.argv[1:3] == ["-o", str(p.out / "shards" / f"photo.s{i}.partial.yoda")]
        assert step.count_check[3] == str(member)                          # its own share of the sidecar
        assert step.count_check[1] == p.out / "events.s1.hepmc.json"        # App_Pythia's: its first output
    merge = p.rendered["rivet.merge"]
    assert merge.argv[1:4] == ["-e", "-o", str(p.res / "photo.partial.yoda")]
    assert merge.argv[4:] == [str(p.out / "shards" / f"photo.s{i}.yoda") for i in range(1, 5)]
    assert merge.env["RIVET_ANALYSIS_PATH"].endswith("build/Rivet")


def test_the_shards_are_technical_and_the_product_is_the_tables(scratch):
    run, conf, p = plan(sharded(3), scratch)
    assert plot.yoda_of(p) == p.res / "photo.yoda"
    manifest = record.points_manifest([p], run, conf)
    assert manifest["points"][0]["products"] == {"photo.yoda": str(p.res / "photo.yoda")}


def test_sharding_does_not_move_the_seeds(scratch):
    _, _, one = plan(raw(run__threads=4), scratch)
    _, _, four = plan(sharded(4, run__threads=4), scratch)
    assert record.seed_basis(one) == record.seed_basis(four)                 # the same events, dealt differently
    assert record.identity(one) != record.identity(four)                     # but not the same point: it reruns


@pytest.mark.parametrize("radius", [{"target": "rivet/photo_eic", "key": "R"},        # eic's radius
                                    {"target": "rivet/photo_eic", "key": {"rivet": "R"}}])
def test_a_quantity_aimed_at_the_table_reaches_every_shard(scratch, radius):
    data = sharded(3, run__one__sweeps=["radius"],
                   quantities__radius={**radius, "values": [0.4, 0.7], "tags": ["r04", "r07"]})
    _, _, p = plan(data, scratch, point=1)
    for i in range(1, 4):
        assert "photo_eic:R=0.7" in p.rendered[f"rivet.{i}"].argv
    assert not any("photo_eic:R" in a for a in p.rendered["rivet.merge"].argv)
    assert p.point.name == "r07"


def test_other_outputs_still_get_every_event(scratch):
    data = sharded(2, prelim__fifo=["events.hepmc", "copy.hepmc"],
                   tools__pythia__output_file=["events.hepmc", "copy.hepmc"],
                   tools__probe={"tool": "custom", "executable": "/bin/cat", "arguments": ["{input}"],
                                 "input": "copy.hepmc", "streamable": True},
                   run__one__tools=[["pythia", "rivet", "probe"]])
    _, _, p = plan(data, scratch)
    groups = p.rendered["pythia"].argv[1].split(",")
    assert groups == [f"{p.out / 'events.s1.hepmc'}+{p.out / 'events.s2.hepmc'}", str(p.out / "copy.hepmc")]


def test_an_output_path_with_a_separator_is_refused(scratch):
    """`+` and `,` separate App_Pythia's outputs: a path holding one would be split into others."""
    with pytest.raises(HepError, match="contains ',' or '\\+'"):
        plan(sharded(2, run__one__sweeps=["q"], quantities__q={"key": {"pythia": "MultipartonInteractions:pT0Ref"},
                                                                 "values": [3.0, 3.2], "tags": ["a+b", "c"]}), scratch)


@pytest.mark.parametrize("changes, message", [
    ({"tools__rivet__shards": 0}, "at least 1"),
    ({"tools__yd2rt": {"tool": "yd2rt", "input": "photo.yoda", "output_file": "photo.root", "shards": 2},
      "run__one__tools": [["pythia", "rivet"], "yd2rt"]}, "cannot be sharded"),
    ({"tools__rivet__shards": 2, "tools__pythia": {"tool": "custom", "executable": "/bin/true",
                                                   "output_file": "events.hepmc"}}, "cannot deal"),
    ({"tools__rivet__shards": 2, "prelim__fifo": [], "tools__rivet__input": "./tests/reference/legacy_run/x.hepmc"},
     "not a \\[prelim\\] FIFO or file"),
])
def test_what_cannot_be_sharded_is_refused(scratch, changes, message):
    with pytest.raises(HepError, match=message):
        plan(raw(**changes), scratch)
