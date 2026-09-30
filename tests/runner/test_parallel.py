"""`parallelism = K` (V36): up to K points at once. It never changes a point (identity, seeds); the
scheduler keeps K running and stops starting on a stop; the views keep each point's part, so a
block is printed whole; the journal and the prepare caches are safe to share."""

from __future__ import annotations

import io
import json
import threading
import time
from types import SimpleNamespace

import pytest

from runner import config, execute, record
from runner.errors import HepError
from runner.execute import PointResult, Stopper, ToolResult
from runner.status import Journal, ToolState
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

    def run_point(plan, run, configuration, *, sink, journal, stopper):
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
    sink = execute.NullSink()
    done, failed, stopped = execute.run_points(fake_plans(8), None, SimpleNamespace(parallelism=3), sink=sink,
                                               journal=None, stopper=Stopper(), rerun=False)
    assert (done, failed, stopped) == (6, 1, False)                  # p2 was complete, p4 failed
    assert peak[0] == 3
    assert started[:3] == ["p1", "p3", "p4"]                         # in order, the complete one skipped


def test_a_stop_starts_nothing_more(monkeypatch):
    stopper, started = Stopper(), []

    def run_point(plan, run, configuration, *, sink, journal, stopper):
        started.append(plan.point.name)
        time.sleep(0.05)
        stopper.requested = True                                     # Ctrl-C while the first ones run
        return PointResult(False, stopped=True)

    monkeypatch.setattr(execute, "run_point", run_point)
    monkeypatch.setattr(execute, "is_complete", lambda plan: False)
    done, failed, stopped = execute.run_points(fake_plans(6), None, SimpleNamespace(parallelism=2),
                                               sink=execute.NullSink(), journal=None, stopper=stopper, rerun=False)
    assert stopped and (done, failed) == (0, 0)
    assert started == ["p1", "p2"]


def test_points_running_at_once_each_print_one_whole_block():
    out = io.StringIO()
    view = PlainView(stream=out)
    view.begin(2)
    a = SimpleNamespace(point=Point(index=1, name="MSTW08lo"), res="results/x/MSTW08lo")
    b = SimpleNamespace(point=Point(index=2, name="NNPDF23lo"), res="results/x/NNPDF23lo")
    sa, sb = view.for_point(a), view.for_point(b)
    sa.point_started(a)
    sb.point_started(b)
    sb.note("   sherpa:prepare: cached")                               # a note knows its point
    sa.tool_finished(ToolState(point="MSTW08lo", tag="rivet", error="boom"), ToolResult("rivet", exit=1, seconds=1.0))
    sb.point_finished(b, PointResult(True))
    sa.point_finished(a, PointResult(False, cause="rivet", message="rivet exited 1"))
    view.flush()
    lines = out.getvalue().splitlines()
    assert lines[0].startswith("── point 2/2: NNPDF23lo ── ok")
    assert lines[1:3] == ["   sherpa:prepare: cached", "   done → results/x/NNPDF23lo"]
    assert lines[3].startswith("── point 1/2: MSTW08lo ── FAILED [rivet]")
    assert lines[4:] == ["   rivet: exit 1 after 1.0s  (boom)", "   rivet exited 1"]


def test_the_journal_takes_lines_from_many_threads(scratch):
    journal = Journal(scratch / "status.jsonl")

    def write(n: int):
        for i in range(500):
            journal.write(f"p{n}", "pythia", {"k": "progress", "done": i, "pad": "x" * 200})

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
