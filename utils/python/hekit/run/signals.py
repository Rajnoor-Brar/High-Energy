"""Stopping stages, and working out which one actually failed (06 §3.3, §4; finding 00/B20).

Two jobs that look small and are not:

**Escalation.** A pipeline is stopped politely first, because `hep-run` answers SIGINT by finishing the
current chunk and writing its partial outputs (06 §4). Only a stage that ignores that gets SIGTERM, and
only one that ignores *that* gets SIGKILL. Each step has its own grace period, and every signal goes to
the whole process group when we started one, so a stage's own children die with it.

**Attribution.** When one stage of a FIFO pipeline fails, the others die of it: the generator writing
into a closed pipe takes SIGPIPE, and whatever we stop takes SIGTERM. The old `rivpyth` reported
whichever status it noticed first, which is how a plain "unknown analysis" could surface as
"generator killed by signal 13" (00/B20). So statuses are ranked rather than read in order:

1. a status we caused ourselves is not evidence of anything;
2. a real exit code beats a signal death, and consumers are considered before producers, because a
   consumer that exits early is what closes the pipe on the producer;
3. if only signal deaths are left and one of them is a SIGPIPE, the pipeline's data path broke while
   it was running — 06 §3.3 calls that exit 4, "FIFO closed early". The code says the data path
   broke; the message names whatever actually crashed, because that is what the user must fix.
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass

#: 06 §3.3. `hep-run` produces these itself; the supervisor adds 7 and maps external tools onto them.
EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_USAGE = 2
EXIT_INIT = 3
EXIT_SOURCE = 4
EXIT_SINK = 5
EXIT_STOPPED = 6
EXIT_STALLED = 7
EXIT_INTERNAL = 70

MEANING = {
    EXIT_OK: "success",
    EXIT_CONFIG: "spec or card error",
    EXIT_USAGE: "usage",
    EXIT_INIT: "generator init failed",
    EXIT_SOURCE: "source I/O",
    EXIT_SINK: "sink error",
    EXIT_STOPPED: "stopped by signal, partial outputs finalised",
    EXIT_STALLED: "stalled or timed out",
    EXIT_INTERNAL: "internal error",
}

#: What a role's own crash means in the table above, when the crash carries no exit code of its own.
ROLE_EXIT = {"generate": EXIT_SOURCE, "analyse": EXIT_SINK, "detector": EXIT_SINK,
             "prepare": EXIT_CONFIG}


def describe(status: int | None) -> str:
    """"exit 3", "killed by SIGTERM", or "still running"."""
    if status is None:
        return "still running"
    if status >= 0:
        meaning = MEANING.get(status)
        return f"exit {status}" + (f" ({meaning})" if meaning else "")
    try:
        name = signal.Signals(-status).name
    except ValueError:                                   # pragma: no cover - unknown signal number
        name = f"signal {-status}"
    return f"killed by {name}"


def stopped_by_us(status: int | None, sent: set[int]) -> bool:
    """True when this status is just the echo of a signal the supervisor sent."""
    return status is not None and status < 0 and -status in sent


@dataclass
class Attribution:
    """Which stage failed, with what, and how sure we are."""

    stage: str = ""
    status: int | None = None
    exit_code: int = EXIT_OK
    reason: str = ""

    @property
    def failed(self) -> bool:
        return self.exit_code != EXIT_OK


def attribute(results: list[tuple[str, str, int | None]], *, sent: set[int] | None = None,
              stalled: str = "") -> Attribution:
    """Pick the failure that explains a pipeline.

    `results` is `[(stage name, role, status)]` **in chain order** (producers first). `sent` is the set
    of signal numbers the supervisor sent, whose echoes carry no information.
    """
    sent = sent or set()
    if stalled:
        return Attribution(stalled, None, EXIT_STALLED, "no output and no status for too long")

    # Consumers first: a reader that exits early is the reason a writer sees a closed pipe.
    ordered = list(reversed(results))

    for name, _role, status in ordered:
        if status is not None and status > 0 and not stopped_by_us(status, sent):
            return Attribution(name, status, status, f"{name} failed with {describe(status)}")

    # Only signal deaths left. A SIGPIPE among them means the pipeline's data path broke while it was
    # running, which 06 §3.3 calls exit 4 ("source I/O, FIFO closed early"). The *code* says the data
    # path broke; the *message* still names whatever crashed, because that is what the user must fix.
    deaths = [(name, role, status) for name, role, status in ordered
              if status is not None and status < 0 and not stopped_by_us(status, sent)]
    broken_pipe = [entry for entry in deaths if -entry[2] == signal.SIGPIPE]
    crashes = [entry for entry in deaths if -entry[2] != signal.SIGPIPE]
    if broken_pipe:
        if crashes:
            name, _role, status = crashes[0]
            return Attribution(name, status, EXIT_SOURCE,
                               f"{name} was {describe(status)}, so {broken_pipe[0][0]} wrote into a "
                               f"closed pipe")
        name, _role, status = broken_pipe[0]
        return Attribution(name, status, EXIT_SOURCE,
                           f"{name} wrote into a closed pipe: the reader ended early")
    if crashes:
        name, role, status = crashes[0]
        return Attribution(name, status, ROLE_EXIT.get(role, EXIT_INTERNAL),
                           f"{name} was {describe(status)}")

    # Nothing but our own signals: the run was stopped rather than broken.
    for name, _role, status in ordered:
        if stopped_by_us(status, sent):
            return Attribution(name, status, EXIT_STOPPED, "stopped on request")
    return Attribution()


@dataclass
class Escalation:
    """SIGINT → grace → SIGTERM → grace → SIGKILL (06 §4)."""

    grace: float = 10.0              # after SIGINT, for a stage to finalise its outputs
    term_grace: float = 5.0          # after SIGTERM, before SIGKILL
    steps: tuple[int, ...] = (signal.SIGINT, signal.SIGTERM, signal.SIGKILL)

    def wait_for(self, step: int) -> float:
        return {signal.SIGINT: self.grace, signal.SIGTERM: self.term_grace}.get(step, 0.0)


def send(process, number: int, *, group: bool = True) -> None:
    """Signal a process, its group when it has one. A dead process is not an error."""
    if process is None or process.poll() is not None:
        return
    try:
        if group:
            os.killpg(os.getpgid(process.pid), number)
        else:
            process.send_signal(number)
    except (ProcessLookupError, PermissionError):
        # It died between the poll and the signal, or it is not ours to signal any more.
        try:
            process.send_signal(number)
        except (ProcessLookupError, ValueError, PermissionError):
            pass


def stop(processes, escalation: Escalation | None = None, *, group: bool = True) -> set[int]:
    """Stop everything still running, escalating only as far as needed. Returns the signals sent."""
    escalation = escalation or Escalation()
    sent: set[int] = set()
    for step in escalation.steps:
        alive = [process for process in processes if process is not None and process.poll() is None]
        if not alive:
            break
        for process in alive:
            send(process, step, group=group)
        sent.add(step)
        deadline = time.monotonic() + escalation.wait_for(step)
        while time.monotonic() < deadline:
            if all(process.poll() is not None for process in alive):
                break
            time.sleep(0.05)
    for process in processes:                            # reap, so no zombie is left behind
        if process is not None and process.poll() is None:
            try:
                process.wait(timeout=5)
            except Exception:                            # pragma: no cover - a truly stuck child
                pass
    return sent
