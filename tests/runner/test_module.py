"""Module programs in the chain (P4 S1): the module folder's argv, the producer's sidecar only for a
file chain, the count check through the kit's report, and seeds that follow the generator."""

from __future__ import annotations

import json

from runner import execute, quantities, record, sweep, tools
from runner.tools import Step

from helpers import parse, plan, raw

MODULE = {"tool": "module", "executable": "/bin/true", "output_file": "lambda.root"}


def test_a_module_reading_a_fifo_gets_no_sidecar_and_is_count_checked(scratch):
    data = raw(prelim={"fifo": ["events.hepmc", "to_module.hepmc"]},
               run__one__tools=[["pythia", "rivet", "lambda"]],
               tools__pythia__output_file=["events.hepmc", "to_module.hepmc"],
               tools__lambda={**MODULE, "input": "to_module.hepmc"})
    _, _, p = plan(data, scratch)
    step = p.rendered["lambda"]
    fifo = str(p.interfaces["to_module.hepmc"].path)
    partial = step.products[0][1]
    assert step.argv == ["/bin/true", str(step.config_path), f"--input={fifo}", f"--output={partial}",
                         "--events=10", "--sidecar="]            # a FIFO's sidecar appears only after the stream
    assert step.config_path in p.writes                           # a kit program always gets a config
    assert step.count_check == (partial, p.rendered["pythia"].sidecar, "json:events")


def test_a_module_in_a_later_group_gets_the_producer_sidecar(scratch):
    data = raw(prelim={"files": ["events.hepmc"]}, run__one__tools=["pythia", "lambda"],
               tools__lambda={**MODULE, "input": "events.hepmc"})
    _, _, p = plan(data, scratch)
    assert f"--sidecar={p.rendered['pythia'].sidecar}" in p.rendered["lambda"].argv


def test_the_count_check_reads_the_report_and_it_follows_its_product(scratch):
    partial, final = scratch / "lambda.partial.root", scratch / "lambda.root"
    partial.write_text("root")
    execute.report_of(partial).write_text(json.dumps({"events": 12, "sum_w": 12.0}))
    assert execute.read_count(partial, "json:events") == 12
    assert execute.read_count(scratch / "missing.root", "json:events") is None
    step = Step(tag="lambda", tool=None, folder=None, group=0, exe=scratch)
    step.products = [(final, partial)]
    assert execute._settle([step], {}) is None
    assert final.exists() and json.loads(execute.report_of(final).read_text())["events"] == 12
    assert not execute.report_of(partial).exists()


def _plans(data, scratch, configuration):
    run = parse(data, scratch)
    conf = run.configuration(configuration)
    master = quantities.load_master(run.project, run.master_toml)
    plans = []
    for point in sweep.points(run, conf):
        p = tools.plan_point(run, conf, point, master)
        p.identity = record.identity(p)
        plans.append(p)
    record.assign_seeds(plans)
    return plans


def test_seeds_follow_the_generator_not_the_rest_of_the_chain(scratch):
    """The same generator setup gives the same events in any configuration (the chain against an
    integrated program, P4 S1 row 6); within one plan, points never share a seed block (V9)."""
    data = raw(run__two={"tools": [["pythia", "rivet"], "yd2rt"]},
               tools__yd2rt={"tool": "yd2rt", "input": "photo.yoda", "output_file": "photo.root"},
               run__sweep={"tools": [["pythia", "rivet"]], "sweeps": ["radius"]},
               quantities__radius={"target": "rivet/photo_eic", "key": "R", "values": [0.4, 0.7], "tags": ["r04", "r07"]})
    [one], [two] = _plans(data, scratch, "one"), _plans(data, scratch, "two")
    assert one.identity != two.identity and one.seed == two.seed
    swept = _plans(data, scratch, "sweep")                       # one generator setup, two points
    assert record.seed_basis(swept[0]) == record.seed_basis(swept[1])
    assert abs(swept[0].seed - swept[1].seed) >= swept[0].threads
