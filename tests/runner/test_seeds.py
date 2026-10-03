"""`seed_type` (V39): "identity" (the default: the seeds follow the generator, as every identity said
before), "manual" (exactly `manual_seed`, or the value of a quantity targeting <tool>/seed) and
"random" (drawn when the point runs, kept once it is complete)."""

from __future__ import annotations

import json
import re

import pytest

from runner import config, quantities, record, sweep, tools
from runner.errors import HepError

from helpers import parse, raw

SEEDS = {"target": "pythia/seed", "values": [1, 101, 201], "tags": ["s1", "s101", "s201"]}


def build(data, scratch, configuration=None):
    run = config.parse(data, scratch / "t.toml")
    conf = run.configuration(configuration)
    master = quantities.load_master(run.project, run.master_toml)
    plans = []
    for point in sweep.points(run, conf):
        plan = tools.plan_point(run, conf, point, master)
        plan.identity = record.identity(plan)
        plans.append(plan)
    record.assign_seeds(plans)
    for plan in plans:
        tools.finalise(plan, plan.seed)
    return plans


def card(plan) -> str:
    return plan.writes[plan.rendered["pythia"].card_combined]


def test_the_keys_and_where_they_win(scratch):
    conf = parse(raw(), scratch).configuration(None)
    assert (conf.seed_type, conf.manual_seed) == ("identity", None)
    conf = parse(raw(run__seed_type="manual", run__manual_seed=5, run__one__manual_seed=7), scratch).configuration(None)
    assert (conf.seed_type, conf.manual_seed) == ("manual", 7)
    assert parse(raw(run__manual_seed=5), scratch).configuration(None).manual_seed == 5     # unused: allowed


@pytest.mark.parametrize("changes, message", [
    ({"run__seed_type": "fixed"}, "one of identity, manual, random"),
    ({"run__manual_seed": 0}, "out of range"),
    ({"run__seed_type": 3}, "must be a string"),
])
def test_what_is_refused_when_read(scratch, changes, message):
    with pytest.raises(HepError, match=message):
        parse(raw(**changes), scratch)


def test_the_default_rule_is_what_every_identity_said_before(scratch):
    """No complete point reruns because V39 exists: the default rule is still "generator", and an
    unused manual_seed changes nothing."""
    plain, = build(raw(run__threads=4), scratch)
    assert record.seed_rule(plain) == "generator"
    unused, = build(raw(run__threads=4, run__manual_seed=12345, run__seed_type="identity"), scratch)
    assert (unused.identity, unused.seed) == (plain.identity, plain.seed)
    assert plain.seed == record.seed_of(record.seed_basis(plain), 4)


def test_one_manual_point_is_exactly_its_seed(scratch):
    plan, = build(raw(run__seed_type="manual", run__manual_seed=3245364), scratch)
    assert plan.seed == 3245364
    assert "Random:seed = 3245364" in card(plan) and "Parallelism:seeds" not in card(plan)


def test_every_point_shares_the_manual_seed_and_its_threads_follow(scratch):
    plans = build(raw(run__threads=4, run__seed_type="manual", run__manual_seed=1000,
                      run__one__sweeps=["pdf"]), scratch)
    assert [p.seed for p in plans] == [1000, 1000]                 # two PDFs: one seed, different physics
    for plan in plans:
        seeds = re.search(r"Parallelism:seeds = \{([^}]*)\}", card(plan)).group(1)
        assert [int(s) for s in seeds.split(",")] == [1000, 1001, 1002, 1003]


def test_a_swept_seed_quantity_gives_each_point_its_seed(scratch):
    plans = build(raw(run__threads=4, run__seed_type="manual", quantities__replica=SEEDS,
                      run__one__sweeps=["replica"]), scratch)
    assert [p.seed for p in plans] == [1, 101, 201]
    assert "Random:seed = 101" in card(plans[1])


def test_overlapping_seeds_on_one_setup_are_refused(scratch):
    close = {**SEEDS, "values": [1, 2], "tags": ["s1", "s2"]}
    with pytest.raises(HepError, match="overlapping seed blocks at threads = 4"):
        build(raw(run__threads=4, run__seed_type="manual", quantities__replica=close,
                  run__one__sweeps=["replica"]), scratch)
    assert [p.seed for p in build(raw(run__seed_type="manual", quantities__replica=close,     # one thread each
                                      run__one__sweeps=["replica"]), scratch)] == [1, 2]


def test_the_manual_seed_is_in_the_identity(scratch):
    a, = build(raw(run__seed_type="manual", run__manual_seed=11), scratch)
    b, = build(raw(run__seed_type="manual", run__manual_seed=12), scratch)
    c, = build(raw(run__seed_type="manual", run__manual_seed=11, run__one__threads=1), scratch)
    assert a.identity != b.identity and a.identity == c.identity
    assert record.seed_rule(a) == ["manual", 11]


@pytest.mark.parametrize("changes, message", [
    ({}, "has no seed"),
    ({"run__manual_seed": 899_999_999, "run__threads": 4}, "not an integer from 1 to 899,999,996"),
    ({"quantities__replica": {**SEEDS, "values": ["a", "b", "c"]}, "run__one__sweeps": ["replica"]}, "not an integer"),
])
def test_a_manual_point_without_a_usable_seed_is_refused(scratch, changes, message):
    with pytest.raises(HepError, match=message):
        build(raw(run__seed_type="manual", **changes), scratch)


def test_random_seeds_are_drawn_again_and_disjoint(scratch):
    data = raw(run__threads=4, run__seed_type="random", quantities__replica=SEEDS, run__one__sweeps=["pdf", "replica"])
    first, second = build(data, scratch), build(data, scratch)
    assert [p.identity for p in first] == [p.identity for p in second]      # skip-unchanged still works
    assert [p.seed for p in first] != [p.seed for p in second]
    blocks = sorted((p.seed, p.seed + 4) for p in first)
    assert all(a[1] <= b[0] for a, b in zip(blocks, blocks[1:]))
    assert record.seed_rule(first[0]) == "random" and not first[0].seed_kept
    assert "(random: drawn again by each run)" in tools.describe(first[0], parse(data, scratch))[0]


def test_a_complete_random_point_keeps_the_seed_it_ran_with(scratch, monkeypatch):
    monkeypatch.setenv("HEKIT_OUTPUT", str(scratch / "output"))
    data = raw(run__seed_type="random", run__one__sweeps=["pdf"])
    done = build(data, scratch)[0]
    done.out.mkdir(parents=True)
    (done.out / ".complete").write_text(done.identity + "\n", encoding="utf-8")
    (done.out / "provenance.json").write_text(json.dumps({"seed": 777}), encoding="utf-8")
    again = build(data, scratch)
    assert again[0].seed == 777 and again[0].seed_kept and "Random:seed = 777" in card(again[0])
    assert again[1].seed != 777 and not again[1].seed_kept
    plans = build(data, scratch)
    record.assign_seeds(plans, frozenset({done.point.name}))            # --rerun: it runs again, so it draws anew
    assert plans[0].seed != 777 and not plans[0].seed_kept


def test_stages_keep_the_identity_rule(scratch):
    """A combined group (a stage, V35) merges points; it has no seeds of its own to give."""
    from runner import post
    data = raw(run__seed_type="manual", quantities__replica=SEEDS, run__one__sweeps=["pdf", "replica"],
               run__one__combine=["replica"])
    run = config.parse(data, scratch / "t.toml")
    conf = run.configuration(None)
    groups = post.plan_combined(run, conf, quantities.load_master(run.project, run.master_toml), build(data, scratch))
    assert groups and all(g.seed_type == "identity" and record.seed_rule(g) == "generator" for g in groups)


def test_a_manual_seed_past_the_generators_range_is_refused_when_planned(scratch):
    """The upper bound is the point's generators' [card] seed_range (V54): Pythia's 9·10⁸ here."""
    data = raw(run__seed_type="manual", run__one__manual_seed=900_000_000)
    with pytest.raises(HepError, match="not an integer from 1 to 899,999,999"):
        build(data, scratch)


def test_the_seed_range_is_the_intersection_of_the_seeded_folders(scratch):
    [p] = build(raw(), scratch)
    assert p.seed_range == (1, 900_000_000) == tools.DEFAULT_SEED_RANGE
    fake = lambda spec: type("S", (), {"folder": tools.Folder("x", scratch, spec)})()
    narrow = fake({"card": {"seed": ["s {seed}"], "seed_range": [10, 1000]}})
    unseeded = fake({"card": {"seed_range": [5, 6]}})                      # writes no seed: does not count
    assert tools.seed_range_of([narrow, unseeded]) == (10, 1000)

