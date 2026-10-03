#!/usr/bin/env python3
"""docs/audit_1/notes/B8_sim.py — the B8 note's simulation: today's schedule vs one DAG with a core budget,
on the real plans of a config (read only; nothing runs).    python3 docs/audit_1/notes/B8_sim.py PhotoProduction/zeus_validation
"""
import argparse, copy, heapq, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "utils", "Env"))
from runner import cli, config as cm, execute

RATE = 10_000_000 / 2260.0          # events/s of one zeus point (6 threads, 6 shards), measured
CORES = os.cpu_count()

def planned(name):
    run = cm.load(name)
    out = []
    for key in run.runs(None):
        p = cli.build_plans(argparse.Namespace(config=name, set=[], points=None, rerun=False, only=None), key)
        out.append(p)
    return run, out

def today(runs):
    """sweep_runs: one configuration after another; in each, `parallelism` points at a time, in order."""
    t = 0.0
    for p in runs:
        k = max(1, p.configuration.parallelism)
        slots = [t] * k
        for plan in p.every:
            start = heapq.heappop(slots)
            heapq.heappush(slots, start + plan.events / RATE)
        t = max(slots)
    return t

def dag(runs, budget=CORES):
    """Every point of every configuration a node; any ready node starts while the core budget allows."""
    nodes = [(plan.events / RATE, execute.cores(plan)) for p in runs for plan in p.every]
    t, free, running, queue = 0.0, budget, [], list(nodes)
    while queue or running:
        started = True
        while started:
            started = False
            for i, (d, c) in enumerate(queue):
                if c <= free or (not running and c > budget):
                    heapq.heappush(running, (t + d, c)); free -= c; queue.pop(i); started = True; break
        end, c = heapq.heappop(running); t = end; free += c
    return t

run, runs = planned(sys.argv[1])
print(f"{run.name}: {sum(len(p.every) for p in runs)} points in {len(runs)} runs; cores per point "
      f"{sorted({execute.cores(pl) for p in runs for pl in p.every})}; {CORES} cores")
a, b = today(runs), dag(runs)
print(f"today (sweep_runs, parallelism per run): {a/3600:.1f} h")
print(f"one DAG, budget {CORES} cores:            {b/3600:.1f} h  ({100*(a-b)/a:.1f}% less)")

# scenarios on the same plans: a point's cost scaled by its name
def scaled(runs, factor):
    for p in runs:
        for plan in p.every:
            plan.events = int(plan.events * factor(plan.point.name, p.configuration.key))
    return runs


for label, factor in [("nompi at 0.6x (MPI off is cheaper)", lambda n, k: 0.6 if n == "nompi" else 1.0),
                      ("one PDF 1.3x dearer", lambda n, k: 1.3 if n == "NNPDF23nlo" else 1.0)]:
    r = scaled(copy.deepcopy(runs), factor)
    a, b = today(r), dag(r)
    print(f"{label}: today {a/3600:.1f} h, DAG {b/3600:.1f} h ({100*(a-b)/a:.1f}% less)")
r = copy.deepcopy(runs)
for p in r:
    p.every = p.every[:3] if len(p.every) == 4 else p.every     # 3 points a run at 2 at once
a, b = today(r), dag(r)
print(f"3 points a run: today {a/3600:.1f} h, DAG {b/3600:.1f} h ({100*(a-b)/a:.1f}% less)")
