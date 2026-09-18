"""The supervisor's failure modes, with fake stages (P3-S02).

Everything here is a case that costs a real run to reproduce and seconds to fake: a stage that exits
before the FIFO is opened, one that hangs silently, one that floods stderr, one that ignores SIGINT,
and a reader that dies while its writer is still writing. The fakes live in `fakes/` and are ordinary
scripts, so a failing case can be run by hand.

Each test is kept under ten seconds, which is why the grace periods are set small here — the policy
itself (10 s after SIGINT) is 06 §4's and is tested by its own arithmetic, not by waiting for it.
"""

from __future__ import annotations

import os
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hekit.run import signals as signal_policy
from hekit.run.supervisor import StageSpec, Supervisor
from hekit.run.transport import PREFIX, Transport

FAKES = Path(__file__).resolve().parent / "fakes"


def fake(name: str, *arguments: str) -> list[str]:
    return [sys.executable, str(FAKES / name), *[str(argument) for argument in arguments]]


def supervisor(tmp_path: Path, **overrides) -> Supervisor:
    settings = dict(poll=0.02, grace=0.5, term_grace=0.5, log_dir=tmp_path / "logs")
    settings.update(overrides)
    return Supervisor(**settings)


# ── the happy path ───────────────────────────────────────────────────────────

def test_a_pipeline_that_works_reports_nothing_wrong(tmp_path):
    with Transport(label="ok") as transport:
        fifo = transport.fifo("events.hepmc")
        outcome = supervisor(tmp_path).run([
            StageSpec(name="writer", role="generate", command=fake("writer.py", fifo, 20)),
            StageSpec(name="reader", role="analyse", command=fake("reader.py", fifo)),
        ], transport=transport)
    assert outcome.ok, outcome.summary()
    assert outcome.exit_code == 0
    assert [stage.status for stage in outcome.stages] == [0, 0]
    assert not outcome.stalled


def test_each_stage_gets_its_own_log_file(tmp_path):
    with Transport() as transport:
        fifo = transport.fifo("events.hepmc")
        supervisor(tmp_path).run([
            StageSpec(name="writer", role="generate", command=fake("writer.py", fifo, 5)),
            StageSpec(name="reader", role="analyse", command=fake("reader.py", fifo)),
        ], transport=transport)
    logs = sorted(path.name for path in (tmp_path / "logs").iterdir())
    assert logs == ["reader.log", "writer.log"]
    assert "wrote 5 blocks" in (tmp_path / "logs" / "writer.log").read_text()
    assert "read 20480 bytes" in (tmp_path / "logs" / "reader.log").read_text()


# ── the verification rows ────────────────────────────────────────────────────

def test_a_stage_that_exits_before_opening_the_fifo_stops_the_run(tmp_path):
    """The case that used to hang: the reader blocks opening the FIFO, so waiting on it alone waits
    for ever. The supervisor polls every stage, so it sees the generator go."""
    with Transport() as transport:
        fifo = transport.fifo("events.hepmc")
        started = time.monotonic()
        outcome = supervisor(tmp_path).run([
            StageSpec(name="generator", role="generate",
                      command=fake("early_exit.py", 1, "bad card")),
            StageSpec(name="rivet", role="analyse", command=fake("reader.py", fifo)),
        ], transport=transport)
    assert outcome.exit_code == 1, outcome.summary()
    assert outcome.attribution.stage == "generator"
    assert time.monotonic() - started < 10, "it must not wait for the blocked reader"
    assert outcome.status_of("rivet") is not None, "the reader was stopped, not left behind"


def test_a_silent_hang_is_detected_and_can_be_killed(tmp_path):
    """06 §4: no status and no log growth for `stall_after` → stalled; after `stall_kill` → exit 7."""
    outcome = supervisor(tmp_path, stall_after=0.3, stall_kill=0.6).run(
        [StageSpec(name="generator", role="generate", command=fake("hang.py", 3600))])
    assert outcome.exit_code == signal_policy.EXIT_STALLED, outcome.summary()
    assert outcome.stalled == "generator"
    assert outcome.wall_seconds < 10


def test_a_stall_can_be_reported_without_killing(tmp_path):
    """`stall_kill` is off by default: a slow point is not a broken one."""
    outcome = supervisor(tmp_path, stall_after=0.2, stall_kill=0).run(
        [StageSpec(name="generator", role="generate", command=fake("hang.py", 0.8))])
    assert outcome.stalled == "generator", "it was noticed"
    assert outcome.exit_code == 0, "and left alone to finish"


def test_a_flood_of_output_costs_disk_and_not_memory(tmp_path):
    """Verification row 'Flood': a gigabyte of stderr must not be a gigabyte of RSS."""
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    outcome = supervisor(tmp_path).run(
        [StageSpec(name="noisy", role="generate", command=fake("flood.py", 1024))])
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert outcome.ok, outcome.summary()

    log = tmp_path / "logs" / "noisy.log"
    assert log.stat().st_size > 1024 * 1024 * 1024, "the whole flood reached the log file"
    assert (after - before) < 64 * 1024, f"RSS grew by {(after - before) / 1024:.0f} MiB"
    assert outcome.stages[0].log_bytes > 1024 * 1024 * 1024


def test_a_stage_that_ignores_sigint_is_escalated_to_sigterm(tmp_path):
    """06 §4: SIGINT first, because hep-run finalises on it; SIGTERM only for what ignores it."""
    with Transport() as transport:
        fifo = transport.fifo("events.hepmc")
        outcome = supervisor(tmp_path).run([
            StageSpec(name="stubborn", role="generate", command=fake("ignores_sigint.py", 3600)),
            StageSpec(name="doomed", role="analyse", command=fake("early_exit.py", 5)),
        ], transport=transport)
    assert outcome.exit_code == 5, outcome.summary()          # the real failure, not the stopping
    assert outcome.status_of("stubborn") == -signal.SIGTERM
    assert signal.SIGINT in outcome.signals_sent and signal.SIGTERM in outcome.signals_sent
    assert signal.SIGKILL not in outcome.signals_sent, "SIGTERM was enough"


def test_a_stage_that_ignores_everything_is_killed(tmp_path):
    outcome = supervisor(tmp_path).run([
        StageSpec(name="immortal", role="generate",
                  command=fake("ignores_sigint.py", 3600, "--also-term")),
        StageSpec(name="doomed", role="analyse", command=fake("early_exit.py", 3)),
    ])
    assert outcome.exit_code == 3, outcome.summary()
    assert outcome.status_of("immortal") == -signal.SIGKILL


def test_a_reader_that_dies_is_reported_and_not_the_writers_sigpipe(tmp_path):
    """00/B20: the generator writing into a closed pipe is a consequence, never the explanation.

    Here the reader dies of a signal with no status of its own, so the only real information is that
    the data path broke — which is exit 4 in 06 §3.3 ("source I/O, FIFO closed early")."""
    with Transport() as transport:
        fifo = transport.fifo("events.hepmc")
        outcome = supervisor(tmp_path).run([
            StageSpec(name="generator", role="generate", command=fake("writer.py", fifo, 0)),
            StageSpec(name="rivet", role="analyse",
                      command=fake("reader.py", fifo, 0, 2, "--signal", int(signal.SIGSEGV))),
        ], transport=transport)
    assert outcome.exit_code == signal_policy.EXIT_SOURCE, outcome.summary()
    assert outcome.status_of("rivet") == -signal.SIGSEGV
    assert outcome.status_of("generator") == -signal.SIGPIPE
    # The code says the data path broke; the message still names the crash, which is the thing to fix.
    assert outcome.attribution.stage == "rivet"
    assert "SIGSEGV" in outcome.attribution.reason and "closed pipe" in outcome.attribution.reason


def test_a_readers_own_error_wins_over_the_writers_sigpipe(tmp_path):
    """The same shape, but the reader exits with a real code: that code is the answer (00/B20)."""
    with Transport() as transport:
        fifo = transport.fifo("events.hepmc")
        outcome = supervisor(tmp_path).run([
            StageSpec(name="generator", role="generate", command=fake("writer.py", fifo, 0)),
            StageSpec(name="rivet", role="analyse", command=fake("reader.py", fifo, 4, 2)),
        ], transport=transport)
    assert outcome.exit_code == 4, outcome.summary()
    assert outcome.attribution.stage == "rivet"
    assert outcome.status_of("generator") in {-signal.SIGPIPE, 1, 0}, "however the writer died"


def test_the_fifo_directory_is_always_removed(tmp_path):
    """Verification row 'Cleanup'. The old tools left pipes in /tmp when they crashed (00/B19)."""
    seen = {}
    with Transport(label="cleanup", root=tmp_path / "tmp") as transport:
        fifo = transport.fifo("events.hepmc")
        seen["dir"] = transport.directory
        assert fifo.is_fifo()
        supervisor(tmp_path).run(
            [StageSpec(name="boom", role="generate", command=fake("early_exit.py", 1))],
            transport=transport)
    assert not seen["dir"].exists()
    assert not list((tmp_path / "tmp").iterdir()), "nothing of ours is left behind"


def test_the_supervisor_cleans_up_its_own_transport(tmp_path):
    """A caller that passes no transport gets one, and never has to remember to remove it."""
    before = {path.name for path in Path(os.environ.get("TMPDIR", "/tmp")).glob(f"{PREFIX}*")}
    supervisor(tmp_path).run([StageSpec(name="quick", role="generate",
                                        command=fake("early_exit.py", 0))])
    after = {path.name for path in Path(os.environ.get("TMPDIR", "/tmp")).glob(f"{PREFIX}*")}
    assert after <= before


# ── the status descriptor ────────────────────────────────────────────────────

def test_a_stage_is_told_which_descriptor_to_write_status_on(tmp_path):
    """`pass_fds` keeps the number it is given, so the number cannot be agreed in advance: the
    supervisor allocates it and tells the caller, which is how `[status].fd` gets into the spec."""
    told: dict[str, int] = {}

    def remember(spec: StageSpec, fd: int) -> None:
        told[spec.name] = fd

    outcome = supervisor(tmp_path).run(
        [StageSpec(name="hep-run", role="generate", command=[sys.executable, "-c", "pass"],
                   status=True)],
        on_status_fd=remember)
    assert told["hep-run"] >= 3, told
    assert outcome.ok


def test_the_status_stream_is_read_while_the_stage_runs(tmp_path):
    """The supervisor folds hep-run's status into a reader, which is what P3-S04 draws from."""
    specs = []

    def build(spec: StageSpec, fd: int) -> None:
        spec.command = fake("statusful.py", fd, 4)
        specs.append(spec)

    outcome = supervisor(tmp_path).run(
        [StageSpec(name="hep-run", role="generate", command=[], status=True, tool="")],
        on_status_fd=build)
    assert outcome.ok, outcome.summary()
    reader = outcome.stages[0].reader
    assert reader is not None
    assert reader.threads == 2 and reader.beams["ids"] == [2212, 11]
    assert (reader.done, reader.total) == (400, 400)
    assert reader.summary["events"] == 400
    assert not reader.garbled


def test_status_messages_count_as_liveness(tmp_path):
    """A stage that reports progress is working, even when it prints nothing to its log."""
    def build(spec: StageSpec, fd: int) -> None:
        spec.command = fake("statusful.py", fd, 12)

    outcome = supervisor(tmp_path, stall_after=0.3, stall_kill=0.5).run(
        [StageSpec(name="hep-run", role="generate", command=[], status=True)],
        on_status_fd=build)
    assert outcome.ok, outcome.summary()
    assert not outcome.stalled, "status counts as activity, so this is not a stall"


# ── progress from a tool's own chatter ───────────────────────────────────────

def test_a_tools_progress_lines_are_parsed(tmp_path):
    script = "import sys\nfor n in (100, 200, 300):\n    print(f'Event {n} ( 1 % )', flush=True)\n"
    outcome = supervisor(tmp_path).run(
        [StageSpec(name="sherpa", role="generate", tool="sherpa",
                   command=[sys.executable, "-c", script])])
    assert outcome.ok
    assert outcome.stages[0].progress.events == 300


def test_a_stage_without_a_parser_still_shows_its_last_line(tmp_path):
    script = "print('one', flush=True)\nprint('the last word', flush=True)\n"
    outcome = supervisor(tmp_path).run(
        [StageSpec(name="mystery", role="generate", command=[sys.executable, "-c", script])])
    assert outcome.stages[0].progress.last_line == "the last word"


# ── attribution, as arithmetic ───────────────────────────────────────────────

def test_attribution_prefers_a_real_error_over_a_knock_on_death():
    attribution = signal_policy.attribute(
        [("generator", "generate", -signal.SIGPIPE), ("rivet", "analyse", 1)])
    assert (attribution.stage, attribution.exit_code) == ("rivet", 1)


def test_attribution_ignores_the_signals_we_sent():
    attribution = signal_policy.attribute(
        [("generator", "generate", -signal.SIGTERM), ("rivet", "analyse", 5)],
        sent={signal.SIGINT, signal.SIGTERM})
    assert (attribution.stage, attribution.exit_code) == ("rivet", 5)


def test_a_run_we_stopped_is_reported_as_stopped_not_failed():
    attribution = signal_policy.attribute(
        [("hep-run", "generate", -signal.SIGINT)], sent={signal.SIGINT})
    assert attribution.exit_code == signal_policy.EXIT_STOPPED


def test_a_lone_crash_is_named_by_its_role():
    """No SIGPIPE, so nothing says the data path broke: an analysis that crashed is a sink failure."""
    attribution = signal_policy.attribute([("rivet", "analyse", -signal.SIGSEGV)])
    assert attribution.exit_code == signal_policy.EXIT_SINK
    assert signal_policy.attribute(
        [("hep-run", "generate", -signal.SIGSEGV)]).exit_code == signal_policy.EXIT_SOURCE


def test_a_stall_outranks_everything():
    attribution = signal_policy.attribute(
        [("hep-run", "generate", None)], stalled="hep-run")
    assert attribution.exit_code == signal_policy.EXIT_STALLED


def test_a_clean_run_attributes_nothing():
    assert not signal_policy.attribute([("a", "generate", 0), ("b", "analyse", 0)]).failed


def test_describe_reads_like_a_person_wrote_it():
    assert signal_policy.describe(0).startswith("exit 0")
    assert signal_policy.describe(7) == "exit 7 (stalled or timed out)"
    assert signal_policy.describe(-signal.SIGKILL) == "killed by SIGKILL"
    assert signal_policy.describe(None) == "still running"


# ── the transport itself ─────────────────────────────────────────────────────

def test_a_private_directory_is_not_shared_and_not_guessable(tmp_path):
    """00/B19: fixed /tmp names let two runs hand each other's events to Rivet."""
    with Transport(root=tmp_path) as one, Transport(root=tmp_path) as two:
        assert one.directory != two.directory
        assert one.fifo("events.hepmc") != two.fifo("events.hepmc")
        assert oct(one.directory.stat().st_mode)[-3:] == "700"
        assert one.fifo("events.hepmc").is_fifo()


def test_a_named_fifo_must_exist_and_be_a_fifo(tmp_path):
    from hekit.errors import HepError

    with Transport(root=tmp_path) as transport:
        with pytest.raises(HepError, match="does not exist"):
            transport.adopt(tmp_path / "nothing.hepmc")
        plain = tmp_path / "plain.hepmc"
        plain.write_text("not a pipe")
        with pytest.raises(HepError, match="not a FIFO"):
            transport.adopt(plain)


def test_a_named_fifo_is_not_removed_with_the_transport(tmp_path):
    """The user made it; the user keeps it."""
    theirs = tmp_path / "theirs.hepmc"
    os.mkfifo(theirs)
    with Transport(root=tmp_path) as transport:
        transport.adopt(theirs)
    assert theirs.is_fifo()
