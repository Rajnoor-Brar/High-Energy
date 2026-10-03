"""Running a point: [prelim], the tool groups, supervision, the checks (rank 3).

docs/02_Architecture.md §11. A FIFO chain fails in two ways a single process does not,
and both are handled here by construction:

* **Deadlock at open (L8).** A FIFO blocks until both ends are open. If the writer dies before
  opening, the reader waits for ever and gets no SIGPIPE. So each tool runs in its own process
  group. The first nonzero exit is the cause, and after a grace period the rest of the group gets
  SIGTERM, then SIGKILL. A tool silent for `stall_after` seconds (no output, status or heartbeat)
  counts as failed.
* **A partial result that looks complete.** If the generator dies mid-stream, Rivet sees end of file
  and exits 0. So a consumer's event count is checked against the producer's sidecar, and a product
  keeps its `.partial` name until every check has passed. `.complete` is written last.

Attribution: the cause is the first process to exit nonzero before the runner sent any signal. A
SIGPIPE death is a consequence (its reader went away), never the cause: the reader is blamed, even
when both exits are seen in the same poll (found by P1's failure injection).

**Points at once** (`parallelism = K`, V36): `run_points` runs up to K points on threads of their
own, each through the same `run_point`. Nothing of a point is shared with another (its folder holds
its FIFOs, logs and products), except the event bus (locked) and a prepare cache entry, which one
point at a time may fill (`_prepare_lock`: a lock in this process and flock across processes).

**What is said** goes onto the run's event bus (events.py, V72): a point's and a tool's start and end,
and every status message. A tool's output is read from a pipe (status.Reader); only a failed tool's last
lines reach logs/<tag>.log, unless `logs` (--logs) keeps every tool's whole log.
"""

from __future__ import annotations

import fcntl
import json
import os
import signal
import stat
import subprocess
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import hepfiles
from .errors import HepError
from .paths import repo_root
from .record import complete_marker, is_complete, now, provenance, write_atomic, write_identity
from .status import Reader, ToolState
from .tools import PointPlan, Step, expand

GRACE = 2.0                  # after the first failure, before the rest of the group is asked to stop
TERM_GRACE = 5.0             # after SIGTERM, before SIGKILL
POLL = 0.2


class Stopper:
    """Set by the CLI's SIGINT/SIGTERM handler; the supervisor turns it into the stop ladder."""

    def __init__(self):
        self.requested = False


@dataclass
class ToolResult:
    tag: str
    exit: int | None = None
    seconds: float = 0.0
    cause: str = ""                      # failed | stalled | timeout | stopped | count | missing
    message: str = ""


@dataclass
class PointResult:
    ok: bool
    stopped: bool = False
    cause: str = ""                      # the tag to blame
    message: str = ""
    tools: dict[str, ToolResult] = field(default_factory=dict)


class _Quiet:
    """A bus no one hears (tests, and a caller that wants no events)."""

    def emit(self, point, tool, message):
        return message


def _bus(bus):
    return bus if bus is not None else _Quiet()


def run_points(plans: list[PointPlan], run, configuration, *, bus=None, stopper: Stopper,
               rerun: bool, logs: bool = False) -> tuple[int, int, bool]:
    """Every point not already complete, `configuration.parallelism` at a time, in order: (done,
    failed, stopped). A stop (Ctrl-C) starts nothing more and stops the running points through
    their groups' stop ladder. An error of the runner itself is raised once the running points
    have ended."""
    bus = _bus(bus)
    todo = []
    for plan in plans:
        if not rerun and is_complete(plan):
            bus.emit(plan.point.name, "", {"k": "point", "state": "skipped", "index": plan.point.index,
                                           **({"stage": plan.point.stage} if plan.point.stage else {})})
        else:
            todo.append(plan)
    done = failed = 0
    stopped = False
    at_once = max(1, configuration.parallelism)
    if at_once == 1:
        for plan in todo:
            result = run_point(plan, run, configuration, bus=bus, stopper=stopper, logs=logs)
            if result.stopped or stopper.requested:
                return done, failed, True
            failed += not result.ok
            done += result.ok
        return done, failed, False
    error: BaseException | None = None
    with ThreadPoolExecutor(max_workers=at_once, thread_name_prefix="hep-point") as pool:
        running: set = set()
        while todo or running:
            while todo and len(running) < at_once and not stopper.requested and error is None:
                plan = todo.pop(0)
                running.add(pool.submit(run_point, plan, run, configuration, bus=bus, stopper=stopper, logs=logs))
            if not running:
                break
            finished, running = wait(running, timeout=0.5, return_when=FIRST_COMPLETED)   # SIGINT gets in
            for future in finished:
                try:
                    result = future.result()
                except BaseException as caught:          # the runner's own error, not a tool's
                    error = error or caught
                    continue
                stopped |= result.stopped
                failed += not result.ok and not result.stopped
                done += result.ok
    if error is not None:
        raise error
    return done, failed, stopped or stopper.requested


def cores(plan: PointPlan) -> int:
    """About how many cores a point keeps busy, for the plan's note: its busiest group, where a
    generator counts its threads, a table's own `cores` what it says, an integrated program (one that
    asks for a generator's standard configuration) the generator's threads and one more, anything
    else one (V60: no tool named here)."""
    from .tools import folders
    busiest = 0
    for group in plan.groups:
        count = 0
        for step in group:
            standard = (step.config_data or {}).get("standard", {})
            if step.folder.get("tool", "produces_events"):
                count += plan.threads
            elif step.tool.cores:
                count += step.tool.cores
            elif any(folders().get(s.get("tool"), None) and folders()[s["tool"]].get("tool", "produces_events")
                     for s in standard.values()):
                count += plan.threads + 1
            else:
                count += 1
        busiest = max(busiest, count)
    return max(busiest, 1)


_PREPARE_LOCKS: dict[Path, threading.Lock] = {}
_PREPARE_GUARD = threading.Lock()


@contextmanager
def _prepare_lock(directory: Path):
    """One point at a time in a prepare cache entry: a lock per entry in this process, and flock on
    <entry>.lock beside it across processes (two hep runs), so the entry's own folder stays the tool's."""
    with _PREPARE_GUARD:
        lock = _PREPARE_LOCKS.setdefault(directory, threading.Lock())
    with lock:
        directory.parent.mkdir(parents=True, exist_ok=True)
        with open(directory.with_name(directory.name + ".lock"), "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


# ── the count check ────────────────────────────────────────────────────────────────────────────

def read_count(path: Path, reader: str) -> float | None:
    """`yoda:/RAW/_EVTCOUNT` → the counter's numEntries, read from the YODA text;
    `json:events` → that key of the product's report, <product>.json (the module kit writes it);
    `root:Delphes` → that tree's entries (uproot, imported only here: the runner is stdlib otherwise)."""
    kind, _, obj = reader.partition(":")
    if kind == "root":
        try:
            import uproot
            with uproot.open(path) as file:
                return float(file[obj].num_entries)
        except Exception:                        # no uproot, no file, no tree: no count
            return None
    if kind == "json":
        try:
            return float(json.loads(report_of(path).read_text(encoding="utf-8"))[obj])
        except (OSError, ValueError, KeyError, TypeError):
            return None
    if kind != "yoda":
        return None
    return hepfiles.entries(path, obj)


def report_of(product: Path) -> Path:
    return product.with_name(product.name + ".json")


# ── [prelim] ───────────────────────────────────────────────────────────────────────────────────

def prepare(plan: PointPlan, logs: bool = False) -> None:
    for directory in (plan.out, plan.out / "logs", plan.res):
        directory.mkdir(parents=True, exist_ok=True)
    marker = complete_marker(plan)
    if marker.exists():
        marker.unlink()                  # an attempt is under way: whatever was complete no longer is
    for path, text in plan.writes.items():
        write_atomic(path, text)
    for step in plan.rendered.values():  # a product left by an earlier attempt must not pass for this one's
        for final, partial in step.products:
            final.parent.mkdir(parents=True, exist_ok=True)          # a shard's is under output/…/shards/
            for path in (final, partial, report_of(final), report_of(partial)):
                path.unlink(missing_ok=True)
    for interface in plan.interfaces.values():
        if interface.kind == "fifo":
            if interface.path.exists() or interface.path.is_symlink():
                if not stat.S_ISFIFO(interface.path.stat().st_mode):
                    raise HepError(f"{interface.path} exists and is not a FIFO", hint="remove it")
                interface.path.unlink()  # fresh per attempt
            os.mkfifo(interface.path)
        elif interface.kind == "file" and interface.name in plan.prelim.get("files", []):
            interface.path.touch(exist_ok=True)
    for command in plan.prelim.get("commands", []):
        context = {"repo": str(repo_root()), "out": str(plan.out), "res": str(plan.res),
                   "file:": {n: str(i.path) for n, i in plan.interfaces.items()}}
        argv = [x for a in command for x in ([expand(str(a), context, "[prelim].commands")])]
        done = subprocess.run(argv, cwd=plan.out, capture_output=True, text=True)
        if done.returncode != 0 or logs:              # its output is on disk when it failed, or with --logs (V72)
            (plan.out / "logs" / "prelim.log").open("a", encoding="utf-8").write(
                f"$ {' '.join(argv)}\n{done.stdout}{done.stderr}")
        if done.returncode != 0:
            raise HepError(f"[prelim] command failed ({done.returncode}): {' '.join(argv)}",
                           where=str(plan.out / "logs" / "prelim.log"))


# ── one group ──────────────────────────────────────────────────────────────────────────────────

@dataclass
class _Running:
    step: Step
    process: subprocess.Popen
    state: ToolState
    reader: Reader
    fd: int | None
    started: float
    exited_at: float | None = None


def _signal(entry: _Running, sig: int) -> None:
    try:
        os.killpg(entry.process.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def run_group(plan: PointPlan, group: list[Step], *, bus, stopper: Stopper,
              results: dict[str, ToolResult], logs: bool = False) -> tuple[bool, str, str]:
    """Run one group to the end. Returns (ok, blamed tag, message)."""
    bus = _bus(bus)
    running: list[_Running] = []
    for step in group:
        step.log.parent.mkdir(parents=True, exist_ok=True)
        out_read, out_write = os.pipe()
        env = dict(os.environ)
        env.update(step.env)
        env.pop("HEP_STATUS_FD", None)
        read_fd = write_fd = None
        if step.status == "standard":
            read_fd, write_fd = os.pipe()
            env["HEP_STATUS_FD"] = str(write_fd)
        try:
            process = subprocess.Popen(step.argv, cwd=step.cwd or plan.out, env=env, stdin=subprocess.DEVNULL,
                                       stdout=out_write, stderr=subprocess.STDOUT, start_new_session=True,
                                       pass_fds=(write_fd,) if write_fd is not None else ())
        except OSError as error:
            for entry in running:
                _signal(entry, signal.SIGKILL)
            os.close(out_read)
            if read_fd is not None:
                os.close(read_fd)
            raise HepError(f"cannot start {step.tag}: {error}", where=" ".join(step.argv[:2]))
        finally:
            os.close(out_write)
            if write_fd is not None:
                os.close(write_fd)
        state = ToolState(point=plan.point.name, tag=step.tag)
        bus.emit(plan.point.name, step.tag, {"k": "tool", "state": "started"})
        entry = _Running(step, process, state, Reader(state, fd=read_fd, out=out_read, rules=step.filters, bus=bus,
                                                      log=step.log, keep=logs), read_fd, time.monotonic())
        running.append(entry)

    failure: tuple[str, str, str] | None = None      # (tag, cause, message)
    failed_at = 0.0
    termed = killed = interrupted = False
    exits: list[_Running] = []
    while True:
        for entry in running:
            if entry.exited_at is None and entry.process.poll() is not None:
                entry.exited_at = time.monotonic()
                entry.reader.join(0.5)                # its last status and lines
                entry.state.running, entry.state.exit = False, entry.process.returncode
                exits.append(entry)
                results[entry.step.tag] = ToolResult(entry.step.tag, entry.process.returncode,
                                                     entry.exited_at - entry.started)
                bus.emit(plan.point.name, entry.step.tag, {"k": "exit", "code": entry.process.returncode,
                                                           "seconds": round(entry.exited_at - entry.started, 3)})
        alive = [e for e in running if e.exited_at is None]
        clock = time.monotonic()

        if failure is None:
            failed = [e for e in exits if e.process.returncode != 0]
            if failed:
                # A SIGPIPE death is a consequence (the reader went away), never the cause: blame the
                # first real failure, else the process that left first, even if it exited 0.
                real = [e for e in failed if e.process.returncode != -signal.SIGPIPE]
                blamed = real[0] if real else exits[0]
                piped = [e.step.tag for e in failed if e.process.returncode == -signal.SIGPIPE]
                message = f"{blamed.step.tag} exited with {_describe(blamed.process.returncode)}"
                if piped and blamed.step.tag not in piped:
                    message += f"; {', '.join(piped)} then lost its pipe"
                failure, failed_at = (blamed.step.tag, "failed", message), clock
        if failure is None:
            for entry in alive:
                if clock - entry.state.last_activity > entry.step.stall_after:
                    failure = (entry.step.tag, "stalled", f"{entry.step.tag} was silent for {entry.step.stall_after:.0f} s")
                elif entry.step.timeout and clock - entry.started > entry.step.timeout:
                    failure = (entry.step.tag, "timeout", f"{entry.step.tag} ran past its timeout of {entry.step.timeout:.0f} s")
                if failure:
                    failed_at = clock
                    break
        if failure is None and stopper.requested:
            failure, failed_at = ("", "stopped", "stopped by the user"), clock
            for entry in alive:
                _signal(entry, signal.SIGINT)
            interrupted = True

        if not alive:
            break
        if failure is not None:
            waited = clock - failed_at
            if not termed and waited >= GRACE:
                for entry in alive:
                    _signal(entry, signal.SIGTERM)
                termed = True
            elif termed and not killed and waited >= GRACE + TERM_GRACE:
                for entry in alive:
                    _signal(entry, signal.SIGKILL)
                killed = True
        time.sleep(POLL)

    for entry in running:
        entry.reader.join()
    if failure is None:
        return True, "", ""
    for entry in running:                         # what a failed tool said last, beside its point (V72)
        if entry.process.returncode != 0 or entry.step.tag == failure[0]:
            entry.reader.keep_tail()
    tag, cause, message = failure
    if tag and tag in results:
        results[tag].cause, results[tag].message = cause, message
    if interrupted:
        return False, "", message
    return False, tag, message


def _describe(code: int) -> str:
    if code < 0:
        try:
            return f"signal {signal.Signals(-code).name}"
        except ValueError:
            return f"signal {-code}"
    return f"exit code {code}"


# ── one point ──────────────────────────────────────────────────────────────────────────────────

def run_point(plan: PointPlan, run, configuration, *, bus=None, stopper: Stopper | None = None,
              logs: bool = False) -> PointResult:
    bus = _bus(bus)
    stopper = stopper or Stopper()
    started = now()
    results: dict[str, ToolResult] = {}
    bus.emit(plan.point.name, "", {"k": "point", "state": "started", "index": plan.point.index,
                                   **({"stage": plan.point.stage} if plan.point.stage else {})})
    try:
        prepare(plan, logs)
    except HepError as error:
        result = PointResult(False, cause="prelim", message=error.render())
        _finished(plan, result, bus)
        return result

    ok, blamed, message = run_prepares(plan, bus=bus, stopper=stopper, results=results, logs=logs)
    if not ok:
        result = PointResult(False, stopped=stopper.requested, cause=blamed, message=message, tools=results)
        _cleanup(plan)
        _finished(plan, result, bus)
        return result

    for group in plan.groups:
        ok, blamed, message = run_group(plan, group, bus=bus, stopper=stopper, results=results, logs=logs)
        if not ok:
            result = PointResult(False, stopped=stopper.requested, cause=blamed, message=message, tools=results)
            _cleanup(plan)
            _finished(plan, result, bus)
            return result
        # a group's products are checked and take their final names before the next group reads them
        failure = _settle(group, results)
        if failure is not None:
            _cleanup(plan)
            _finished(plan, failure, bus)
            return failure

    _cleanup(plan)
    record = provenance(plan, run, configuration, started, now(),
                        {tag: {"exit": r.exit, "seconds": round(r.seconds, 3), "note": r.message} for tag, r in results.items()})
    write_atomic(plan.out / "provenance.json", json.dumps(record, indent=1, default=str) + "\n")
    write_identity(plan)                          # what it ran with, for --why (V57)
    write_atomic(complete_marker(plan), plan.identity + "\n")
    result = PointResult(True, tools=results)
    _finished(plan, result, bus)
    return result


def run_prepares(plan: PointPlan, *, bus=None, stopper: Stopper, results: dict[str, ToolResult],
                 logs: bool = False) -> tuple[bool, str, str]:
    """[prepare] steps (Herwig's read, Sherpa's integration), each in its cache entry, before the
    groups. An entry with a `.prepared` stamp is a hit and runs nothing; the stamp is written only
    after the step exited 0 and left its marker, so an interrupted integration is redone."""
    for step in plan.rendered.values():
        if step.prepare_dir is None or not step.prepare_needed:
            continue
        tag = f"{step.tag}:prepare"
        stamp = step.prepare_dir / ".prepared"
        if stamp.exists():
            results[tag] = ToolResult(tag, exit=0, message=f"cache hit {step.prepare_dir.name}")
            _bus(bus).emit(plan.point.name, "", {"k": "note", "msg": f"   {tag}: cached ({step.prepare_dir})"})
            continue
        with _prepare_lock(step.prepare_dir):            # another point may be filling it (V36)
            if stopper.requested:
                return False, step.tag, "stopped before its prepare step"
            if stamp.exists():
                results[tag] = ToolResult(tag, exit=0, message=f"cache hit {step.prepare_dir.name}")
                _bus(bus).emit(plan.point.name, "", {"k": "note", "msg": f"   {tag}: cached, made by a point running "
                                                                         f"beside it ({step.prepare_dir})"})
                continue
            ok, blamed, message = _prepare(plan, step, tag, stamp, bus=bus, stopper=stopper, results=results, logs=logs)
            if not ok:
                return False, blamed, message
    return True, "", ""


def _prepare(plan: PointPlan, step: Step, tag: str, stamp: Path, *, bus, stopper: Stopper,
             results: dict[str, ToolResult], logs: bool = False) -> tuple[bool, str, str]:
    """One prepare step into its (locked) cache entry; the stamp only after it exited 0 with its marker."""
    step.prepare_dir.mkdir(parents=True, exist_ok=True)
    job = replace(step, tag=tag, argv=step.prepare_argv, cwd=step.prepare_dir, inputs=[], outputs=[], products=[],
                  count_check=None, sidecar=None, sidecar_written=None, log=plan.out / "logs" / f"{step.tag}.prepare.log",
                  stall_after=max(step.stall_after, 3600.0))
    ok, blamed, message = run_group(plan, [job], bus=bus, stopper=stopper, results=results, logs=logs)
    if not ok:
        return False, step.tag, message
    marker = step.folder.spec["prepare"].get("marker")
    if marker and not (step.prepare_dir / marker).exists():
        return False, step.tag, f"{tag} exited 0 but left no {marker} in {step.prepare_dir}"
    write_atomic(stamp, json.dumps({"argv": job.argv, "finished": now()}, indent=1) + "\n")
    return True, "", ""


def _settle(group: list[Step], results: dict[str, ToolResult]) -> PointResult | None:
    """After a group succeeded: the count checks, then partial → final names. None when all is well."""
    for step in group:                           # [outputs] written = "requested": exit 0 means all of it
        if step.sidecar_written is not None and step.sidecar is not None:
            write_atomic(step.sidecar, json.dumps({"written": step.sidecar_written, "source": "requested",
                                                   "tool": step.tag}) + "\n")
    for step in group:
        if step.count_check is None:
            continue
        product, sidecar, reader, key = step.count_check
        counted = read_count(product, reader)
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            written = data["written_per_output"][key] if key else data["written"]   # a shard: its own share
        except (OSError, ValueError, KeyError, TypeError):
            written = None
        if counted is None or written is None or round(counted) != written:
            share = f" to {Path(key).name}" if key else ""
            message = (f"{step.tag} analysed {counted if counted is None else round(counted)} events; "
                       f"the producer wrote {written}{share} ({sidecar.name})")
            results.setdefault(step.tag, ToolResult(step.tag)).cause = "count"
            return PointResult(False, cause=step.tag, message=message, tools=results)
        results[step.tag].message = f"count ok: {written} events"
    for step in group:
        for final, partial in step.products:
            if report_of(partial).exists():          # a report travels with its product
                report_of(partial).replace(report_of(final))
            if partial.exists():
                partial.replace(final)
            elif not final.exists():
                return PointResult(False, cause=step.tag, message=f"{step.tag} did not write {final.name}", tools=results)
    return None


def _finished(plan: PointPlan, result: PointResult, bus) -> None:
    bus.emit(plan.point.name, "", {"k": "point", "state": "done" if result.ok else "stopped" if result.stopped else "failed",
                                   "cause": result.cause, "msg": result.message, "res": str(plan.res)})


def _cleanup(plan: PointPlan) -> None:
    """FIFOs are removed when the point ends (04 §6); files are kept."""
    for interface in plan.interfaces.values():
        if interface.kind == "fifo" and interface.path.exists() and stat.S_ISFIFO(interface.path.stat().st_mode):
            interface.path.unlink()
