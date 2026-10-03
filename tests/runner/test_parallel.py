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
