"""`parallelism = K` (V36): up to K points at once. It never changes a point (identity, seeds); the
scheduler keeps K running and stops starting on a stop; the views keep each point's part, so a
block is printed whole; the event bus (and so the journal) and the prepare caches are safe to share."""

from __future__ import annotations

import io
import json
import threading
import time
from types import SimpleNamespace

import pytest

from runner import config, execute, record
from runner.errors import HepError
from runner.events import Bus, Journal
from runner.execute import PointResult, Stopper
from runner.sweep import Point
from runner.watch import PlainView

from helpers import parse, plan, raw


def test_parallelism_is_read_from_run_and_the_configuration(scratch):
    assert parse(raw(), scratch).configuration(None).parallelism == 1
    assert parse(raw(run__parallelism=4), scratch).configuration(None).parallelism == 4
    assert parse(raw(run__parallelism=4, run__one__parallelism=2), scratch).configuration(None).parallelism == 2
    with pytest.raises(HepError, match="at least 1"):
        parse(raw(run__parallelism=0), scratch)


def test_parallelism_changes_neither_identity_nor_seeds(scratch):
    _, _, one = plan(raw(run__threads=2), scratch)
    _, _, four = plan(raw(run__threads=2, run__parallelism=4), scratch)
    assert record.identity(one) == record.identity(four)
    assert record.seed_basis(one) == record.seed_basis(four)


def fake_plans(n: int):
    return [SimpleNamespace(point=Point(index=i + 1, name=f"p{i + 1}")) for i in range(n)]


def test_the_scheduler_keeps_k_points_running_in_order(monkeypatch):
    live, peak, started = [0], [0], []
    lock = threading.Lock()

    def run_point(plan, run, configuration, *, bus, stopper, logs):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
            started.append(plan.point.name)
        time.sleep(0.05)
        with lock:
            live[0] -= 1
        return PointResult(plan.point.name != "p4", cause="" if plan.point.name != "p4" else "x")

    monkeypatch.setattr(execute, "run_point", run_point)
    monkeypatch.setattr(execute, "is_complete", lambda plan: plan.point.name == "p2")
    done, failed, stopped = execute.run_points(fake_plans(8), None, SimpleNamespace(parallelism=3),
                                               stopper=Stopper(), rerun=False)
    assert (done, failed, stopped) == (6, 1, False)                  # p2 was complete, p4 failed
    assert peak[0] == 3
    assert started[:3] == ["p1", "p3", "p4"]                         # in order, the complete one skipped


def test_a_stop_starts_nothing_more(monkeypatch):
    stopper, started = Stopper(), []

    def run_point(plan, run, configuration, *, bus, stopper, logs):
        started.append(plan.point.name)
        time.sleep(0.05)
        stopper.requested = True                                     # Ctrl-C while the first ones run
        return PointResult(False, stopped=True)

    monkeypatch.setattr(execute, "run_point", run_point)
    monkeypatch.setattr(execute, "is_complete", lambda plan: False)
    done, failed, stopped = execute.run_points(fake_plans(6), None, SimpleNamespace(parallelism=2),
                                               stopper=stopper, rerun=False)
    assert stopped and (done, failed) == (0, 0)
    assert started == ["p1", "p2"]


def test_points_running_at_once_each_print_one_whole_block():
    out = io.StringIO()
    view, bus = PlainView(stream=out), Bus()
    bus.subscribe(view)
    bus.emit("", "", {"k": "run", "state": "started", "points": 2})
    bus.emit("MSTW08lo", "", {"k": "point", "state": "started", "index": 1})
    bus.emit("NNPDF23lo", "", {"k": "point", "state": "started", "index": 2})
    bus.emit("NNPDF23lo", "", {"k": "note", "msg": "   sherpa:prepare: cached"})   # a note knows its point
    bus.emit("MSTW08lo", "rivet", {"k": "tool", "state": "started"})
    bus.emit("MSTW08lo", "rivet", {"k": "log", "level": "error", "msg": "boom"})
    bus.emit("MSTW08lo", "rivet", {"k": "exit", "code": 1, "seconds": 1.0})
    bus.emit("NNPDF23lo", "", {"k": "point", "state": "done", "res": "results/x/NNPDF23lo"})
    bus.emit("MSTW08lo", "", {"k": "point", "state": "failed", "cause": "rivet", "msg": "rivet exited 1"})
    view.flush()
    lines = out.getvalue().splitlines()
    assert lines[0].startswith("── point 2/2: NNPDF23lo ── ok")
    assert lines[1:3] == ["   sherpa:prepare: cached", "   done → results/x/NNPDF23lo"]
    assert lines[3].startswith("── point 1/2: MSTW08lo ── FAILED [rivet]")
    assert lines[4:] == ["   rivet: exit 1 after 1.0s  (boom)", "   rivet exited 1"]


def test_the_journal_takes_lines_from_many_threads(scratch):
    journal, bus = Journal(scratch / "status.jsonl"), Bus()
    bus.subscribe(journal)

    def write(n: int):
        for i in range(500):
            bus.emit(f"p{n}", "pythia", {"k": "progress", "done": i, "pad": "x" * 200})

    threads = [threading.Thread(target=write, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    journal.close()
    lines = (scratch / "status.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4000 and all(json.loads(line)["k"] == "progress" for line in lines)


def test_a_prepare_entry_is_filled_by_one_point_at_a_time(scratch):
    entry, inside, peak = scratch / "cache" / "abc", [0], [0]
    lock = threading.Lock()

    def fill():
        with execute._prepare_lock(entry):
            with lock:
                inside[0] += 1
                peak[0] = max(peak[0], inside[0])
            time.sleep(0.05)
            with lock:
                inside[0] -= 1

    threads = [threading.Thread(target=fill) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 1
    assert (scratch / "cache" / "abc.lock").exists() and not entry.exists()   # the lock sits beside the entry


def test_auto_parallelism_is_the_cores_over_a_points_cores(scratch, monkeypatch):
    """V75: "auto" is os.cpu_count() // the costliest point's cores, at least 1."""
    import os
    from runner import cli
    monkeypatch.setattr(os, "cpu_count", lambda: 24)
    _, conf, p = plan(raw(run__threads=6, run__parallelism="auto"), scratch)
    assert conf.parallelism_auto and execute.auto_parallelism([p]) == 24 // execute.cores(p)
    monkeypatch.setattr(os, "cpu_count", lambda: 2)
    assert execute.auto_parallelism([p]) == 1
    with pytest.raises(HepError, match="one of auto"):
        parse(raw(run__parallelism="many"), scratch)


def test_the_budget_holds_a_point_until_its_cores_are_free():
    budget = execute.Budget(24)
    assert budget.take(12) and budget.take(12) and not budget.take(1)
    budget.give(12)
    assert budget.take(12)
    alone = execute.Budget(4)
    assert alone.take(12)                                          # bigger than the budget: it runs alone
    assert not alone.take(1)


def test_a_pipelined_run_says_when_every_point_has_started(monkeypatch):
    """V75: the gate opens once the last point has started, not when it ends; the budget is shared."""
    events, gate = [], threading.Event()

    def run_point(plan, run, configuration, *, bus, stopper, logs):
        events.append(("start", plan.point.name, gate.is_set()))
        time.sleep(0.05)
        return PointResult(True)

    monkeypatch.setattr(execute, "run_point", run_point)
    monkeypatch.setattr(execute, "is_complete", lambda plan: False)
    monkeypatch.setattr(execute, "cores", lambda plan: 2)
    budget = execute.Budget(4)
    done, failed, stopped = execute.run_points(fake_plans(3), None, SimpleNamespace(parallelism=3), stopper=Stopper(),
                                               rerun=False, budget=budget, started_all=gate.set)
    assert (done, failed, stopped) == (3, 0, False) and gate.is_set() and budget.used == 0
    assert [e[2] for e in events[:2]] == [False, False]             # shut while p3 waited for its cores
    assert len(events) == 3                                          # (it opens as p3 is handed its thread)


def test_overlapping_runs_keep_their_points_apart():
    """V75: in a pipelined sweep two runs have points of the same name at once; each heading names its run."""
    out = io.StringIO()
    view, bus = PlainView(stream=out), Bus()
    bus.subscribe(view)
    for run in ("a", "b"):
        bus.emit("", "", {"k": "run", "state": "started", "points": 2, "run": run})
        bus.emit("MSTW08lo", "", {"k": "point", "state": "started", "index": 1, "run": run})
    bus.emit("MSTW08lo", "", {"k": "point", "state": "done", "res": "results/b/MSTW08lo", "run": "b"})
    bus.emit("MSTW08lo", "", {"k": "point", "state": "done", "res": "results/a/MSTW08lo", "run": "a"})
    view.end()
    lines = out.getvalue().splitlines()
    assert lines[0].startswith("── point 1/2 (b): MSTW08lo ── ok") and lines[1] == "   done → results/b/MSTW08lo"
    assert lines[2].startswith("── point 1/2 (a): MSTW08lo ── ok") and lines[3] == "   done → results/a/MSTW08lo"
