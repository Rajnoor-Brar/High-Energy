"""`combine = ["replica"]` (V35), at plan time: the points that differ only in a combined quantity are
one group, planned as a stage in <cfg>/<group>/ that merges their YODA product (rivet-merge -e) into
a file of the same name; the plot stage then draws the groups. C14: a combined quantity is an axis
of its own and not a page axis."""

from __future__ import annotations

import pytest

from runner import config, post, quantities, record, sweep, tools
from runner.errors import HepError

from helpers import raw

REPLICA = {"target": "pythia/seed", "values": [1, 2, 3], "tags": ["s1", "s2", "s3"]}


def seeded(**changes):
    return raw(**{"quantities__replica": REPLICA, "run__one__sweeps": ["pdf", "replica"],
                  "run__one__combine": ["replica"], **changes})


def build(data, scratch):
    run = config.parse(data, scratch / "t.toml")
    conf = run.configuration(None)
    master = quantities.load_master(run.project, run.master_toml)
    plans = []
    for point in sweep.points(run, conf):
        plan = tools.plan_point(run, conf, point, master)
        plan.identity = record.identity(plan)
        plans.append(plan)
    record.assign_seeds(plans)
    for plan in plans:
        tools.finalise(plan, plan.seed)
    return run, conf, plans, post.plan_combined(run, conf, master, plans)


def test_the_replicas_of_each_pdf_are_one_group(scratch):
    _, _, plans, groups = build(seeded(), scratch)
    assert [p.point.name for p in plans] == ["MSTW08lo_s1", "MSTW08lo_s2", "MSTW08lo_s3",
                                             "NNPDF23lo_s1", "NNPDF23lo_s2", "NNPDF23lo_s3"]
    assert [g.point.name for g in groups] == ["MSTW08lo", "NNPDF23lo"]
    first = groups[0]
    assert first.point.stage == "combined" and first.point.choice == {"pdf": 0}     # the plot stage's labels
    assert first.upstream == [p.identity for p in plans[:3]]
    merge = first.rendered["combine"]
    assert merge.argv[1:4] == ["-e", "-o", str(first.res / "photo.partial.yoda")]
    assert merge.argv[4:] == [str(p.res / "photo.yoda") for p in plans[:3]]
    assert first.res.parent == plans[0].res.parent                                     # beside the points


def test_a_group_reruns_when_one_of_its_points_changes(scratch):
    _, _, _, before = build(seeded(), scratch)
    _, _, _, after = build(seeded(quantities__replica={**REPLICA, "values": [1, 2, 4]}), scratch)
    assert before[0].identity != after[0].identity


def test_seeds_differ_across_replicas_and_the_groups_have_their_own(scratch):
    _, _, plans, groups = build(seeded(), scratch)
    assert len({p.seed for p in plans}) == len(plans)
    assert all(g.identity not in {p.identity for p in plans} for g in groups)


def test_combining_everything_is_one_group_named_combined(scratch):
    _, _, _, groups = build(raw(quantities__replica=REPLICA, run__one__sweeps=["replica"], run__one__combine=["replica"]),
                            scratch)
    assert [g.point.name for g in groups] == ["combined"]


@pytest.mark.parametrize("changes, message", [
    ({"run__one__combine": ["pdf"], "run__one__sweeps": ["replica"]}, "not swept here"),
    ({"run__one__plot_points": ["replica"]}, "both combined and a page axis"),
    ({"run__one__sweeps": [["pdf", "replica"]], "quantities__replica": {**REPLICA, "values": [1, 2],
                                                                       "tags": ["s1", "s2"]}}, "axis of its own"),
])
def test_what_cannot_be_combined_is_refused(scratch, changes, message):
    with pytest.raises(HepError, match=message):
        build(seeded(**changes), scratch)
