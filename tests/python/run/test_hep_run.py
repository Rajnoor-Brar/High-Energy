"""`hep-run` end to end: the exit-code contract (06 §3.3) and the status stream of a real run (P2-S04).

These tests run the built binary against specs written by `hekit.plan`, which is the actual contract
between the two halves — a mock spec would only test my idea of one. They are the reason the C++ side
keeps no configuration logic: everything here is a file `hep plan` produced.

The expensive cases (anything that reaches `Pythia::init`, about two seconds of LHAPDF) share
module-scoped fixtures, so the whole file costs four initialisations rather than a dozen.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import migrated                                              # noqa: E402
from hekit import sweep                                      # noqa: E402
from hekit.config import load_config                         # noqa: E402
from hekit.plan import build as builder                      # noqa: E402
from hekit.plan import spec as spec_module                   # noqa: E402
from hekit.run.status import StatusReader, read              # noqa: E402

REPO = Path(__file__).resolve().parents[3]
INPUTS = REPO / "tests" / "golden" / "inputs" / "PhotoProduction"
RUN = REPO / "build" / "bin" / "hep-run"

pytestmark = pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)")

#: Small enough to run in a moment, big enough that both workers and two chunks are exercised.
EVENTS = 200
THREADS = 2


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    """The frozen inputs as a schema-2 project (the same fixture the plan tests use)."""
    directory = tmp_path_factory.mktemp("PhotoProduction")
    migrated.write_v2(INPUTS / "eic.toml", directory / "eic.toml")
    (directory / "photo_ep.cmnd").write_bytes((INPUTS / "photo_ep.cmnd").read_bytes())
    return directory


@pytest.fixture(scope="module")
def spec_path(project: Path, tmp_path_factory) -> Path:
    """A written, runnable spec: `hep plan --write` in one call, without the CLI in the way."""
    config = load_config(project / "eic.toml", machine_file=None, project="PhotoProduction")
    plan = builder.build(config, sweep.select(config, study="single"))
    group = plan.groups[0]
    group.spec["run"]["events"] = EVENTS
    group.spec["run"]["threads"] = THREADS
    group.spec["run"]["seeds"]["instances"] = group.spec["run"]["seeds"]["instances"][:THREADS]
    written = spec_module.write(plan, tmp_path_factory.mktemp("specs"))
    return next(path for path in written if path.name == "run.toml")


def variant(spec_path: Path, name: str, *, card_extra: str = "", edit=None) -> Path:
    """A copy of the good spec with one thing wrong, next to the original so its paths still resolve."""
    text = spec_path.read_text(encoding="utf-8")
    if card_extra:
        card = Path(_cards(text)[-1])                 # the point card is the last one
        broken = card.with_name(f"{name}.cmnd")
        broken.write_text(card.read_text(encoding="utf-8") + card_extra, encoding="utf-8")
        text = text.replace(str(card), str(broken))
    if edit is not None:
        text = edit(text)
    target = spec_path.with_name(f"{name}.toml")
    target.write_text(text, encoding="utf-8")
    return target


def _cards(text: str) -> list[str]:
    return _parsed(text)["source"]["cards"]


def _seeds(text: str) -> list[int]:
    return _parsed(text)["run"]["seeds"]["instances"]


def _parsed(text: str) -> dict:
    import tomllib
    return tomllib.loads(text)


def attempt(*arguments: str, stream: Path | None = None, timeout: int = 180):
    """Run hep-run, optionally with a real fd 3 for the status stream."""
    command = [str(RUN), *arguments]
    if stream is not None:
        # fd 3 has to *be* fd 3 in the child; `pass_fds` does not promise a number (see test_status).
        command = ["sh", "-c", f'exec 3>{shlex.quote(str(stream))}; exec "$@"', "hep-run", *command]
    done = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                          cwd=os.fspath(REPO / "output" / "scratch"))
    return done


def messages(stream: Path) -> StatusReader:
    return StatusReader().feed_lines(_lines(stream))


def stream_messages(stream: Path) -> list:
    """Every message, which the reader itself does not keep — on a million-event run it would grow
    without bound, so folding into state is its job and holding the log is the test's."""
    return list(read(_lines(stream)))


def _lines(stream: Path) -> list[str]:
    return stream.read_text(encoding="utf-8").splitlines()


@pytest.fixture(scope="module")
def finished(spec_path: Path, tmp_path_factory):
    """One real run of EVENTS events, shared by every test that reads its status stream."""
    stream = tmp_path_factory.mktemp("status") / "run.jsonl"
    done = attempt(str(spec_path), stream=stream)
    return done, messages(stream), stream


# ── usage: nothing here touches a generator, so these are the cheap cases ────

def test_no_arguments_is_a_usage_error():
    done = attempt()
    assert done.returncode == 2
    assert "Usage:" in done.stderr


def test_an_unknown_option_is_refused_rather_than_ignored():
    """A silently ignored flag in a batch job is worse than a failure."""
    done = attempt("spec.toml", "--nonsense")
    assert done.returncode == 2 and "unknown option '--nonsense'" in done.stderr


def test_a_second_spec_is_a_usage_error():
    done = attempt("one.toml", "two.toml")
    assert done.returncode == 2 and "more than one spec" in done.stderr


def test_list_needs_a_number():
    done = attempt("spec.toml", "--list")
    assert done.returncode == 2 and "--list needs a number" in done.stderr


def test_capabilities_is_json_naming_the_schema():
    done = attempt("--capabilities")
    assert done.returncode == 0
    found = json.loads(done.stdout)
    assert found["spec_schema"] == 2
    assert isinstance(found["components"], list)
    assert "rivet" in found["components"], "this build has Rivet, so it must say so"
    assert found["version"] and found["build"]


def test_version_and_help_exit_zero():
    for argument in ("--version", "--help", "-h"):
        done = attempt(argument)
        assert done.returncode == 0, argument
        assert "hep-run" in done.stdout


# ── the spec: exit 1, before anything is opened ──────────────────────────────

def test_an_absent_spec_is_a_config_error():
    done = attempt("/nowhere/at/all/run.toml")
    assert done.returncode == 1 and "cannot read the spec" in done.stderr


def test_a_garbled_spec_names_toml(spec_path: Path):
    done = attempt(str(variant(spec_path, "garbled", edit=lambda text: "this is not toml")))
    assert done.returncode == 1 and "not valid TOML" in done.stderr


def test_a_missing_table_is_named(spec_path: Path):
    broken = variant(spec_path, "nosource",
                     edit=lambda text: text.replace("[source]", "[sauce]"))
    done = attempt(str(broken))
    assert done.returncode == 1 and "[source]" in done.stderr


def test_a_short_seed_list_is_refused_before_init(spec_path: Path):
    """D-SEEDS: Pythia indexes the seed list without a bounds check, so this must never reach init."""
    broken = variant(spec_path, "shortseeds",
                     edit=lambda text: re.sub(r"instances = \[[^\]]*\]",
                                              f"instances = [{_seeds(text)[0]}]", text))
    done = attempt(str(broken))
    assert done.returncode == 1
    assert "[run.seeds] instances has 1 entries for 2 threads" in done.stderr
    assert "Welcome to the Lund Monte Carlo" not in done.stdout, "it must stop before Pythia starts"


def test_a_misspelled_card_setting_is_a_config_error(spec_path: Path):
    done = attempt(str(variant(spec_path, "badkey", card_extra="\nThisKey:doesNotExist = 3\n")),
                   "--check")
    assert done.returncode == 1
    assert "Pythia rejected the card" in done.stderr and "badkey.cmnd" in done.stderr


def test_a_missing_card_is_a_config_error(spec_path: Path):
    broken = variant(spec_path, "nocard",
                     edit=lambda text: text.replace("point.cmnd", "absent.cmnd"))
    done = attempt(str(broken), "--check")
    assert done.returncode == 1 and "card not found" in done.stderr


# ── init: exit 3, "the cards were fine but the physics is not" ───────────────

def test_check_accepts_a_good_spec(spec_path: Path, tmp_path: Path):
    stream = tmp_path / "check.jsonl"
    done = attempt(str(spec_path), "--check", stream=stream)
    assert done.returncode == 0, done.stderr
    reader = messages(stream)
    assert reader.phase == "checked"
    assert reader.threads == THREADS
    assert reader.beams["ids"] == [2212, -11], "the EIC card collides protons with positrons"
    assert abs(reader.beams["sqrt_s"] - 318.1) < 1.0, reader.beams
    assert reader.summary == {}, "--check generates nothing, so there is no summary"


def test_a_failing_init_has_its_own_exit_code(spec_path: Path):
    """00/B30: with this card `Photon:ProcessType = 2` cannot initialise. A typo is exit 1; this is 3."""
    broken = variant(spec_path, "direct", card_extra="\nPhoton:ProcessType = 2\n")
    done = attempt(str(broken), "--check")
    assert done.returncode == 3
    assert "failed to initialise" in done.stderr


# ── a real run ───────────────────────────────────────────────────────────────

def test_a_run_exits_zero_and_summarises_itself(finished):
    done, reader, _ = finished
    assert done.returncode == 0, done.stderr
    summary = reader.summary
    assert summary["events"] == EVENTS
    assert summary["attempted"] >= summary["events"], "attempts are not successes (00/B21)"
    assert summary["threads"] == THREADS
    assert summary["stopped"] is False
    assert summary["wall_s"] > 0.0


def test_the_phases_happen_in_order(finished):
    _, _, stream = finished
    phases = [message["phase"] for message in stream_messages(stream) if message.kind == "phase"]
    assert phases == ["configure", "init", "generate", "finish"]


def test_progress_reaches_the_total_even_on_a_short_run(finished):
    """A run shorter than one heartbeat would otherwise leave a reader at 0 %."""
    _, reader, _ = finished
    assert (reader.done, reader.total) == (EVENTS, EVENTS)
    assert reader.fraction == 1.0
    # 06 §3: the per-worker counts are cumulative and add up to `done`, so a reader can draw the
    # load balance. They used to hold only the last chunk, which looked like a run 90 % short.
    assert len(reader.workers) == THREADS
    assert sum(reader.workers) == EVENTS, reader.workers
    assert min(reader.workers) > 0, "balanceLoad is on, so no worker should be idle"


def test_the_chunk_is_a_whole_number_of_workers(finished):
    """D-Q2: otherwise a chunked run would not draw the same events as an unchunked one."""
    _, reader, _ = finished
    chunk = reader.summary["chunk"]
    assert chunk % THREADS == 0 and chunk > 0


def test_the_seeds_are_read_back_from_the_instances(finished, spec_path: Path):
    """Not "the seeds we asked for" — the seeds the instances actually have (05 §3)."""
    _, reader, _ = finished
    assert reader.summary["seeds"] == _seeds(spec_path.read_text(encoding="utf-8"))


def test_sigma_comes_with_an_error(finished):
    """D-Q1: PythiaParallel has no σ error, so it is combined from the instances."""
    _, reader, _ = finished
    assert reader.xsec_final, "the last xsec message is the final one"
    assert reader.summary["xsec_pb"] > 0.0
    assert 0.0 < reader.summary["err_pb"] < reader.summary["xsec_pb"]


def test_the_stream_is_well_formed_from_end_to_end(finished):
    _, reader, _ = finished
    assert not reader.garbled, [message.raw for message in reader.garbled]
    assert not reader.unknown, [message.kind for message in reader.unknown]
    assert reader.last_time > 0


def test_timestamps_have_sub_second_resolution(finished):
    """A whole-second timestamp makes every rate and ETA meaningless; `%.10g` used to do exactly that."""
    _, _, stream = finished
    stamps = [message.time for message in stream_messages(stream)]
    assert any(stamp % 1 for stamp in stamps), stamps[:5]


def test_without_fd_three_the_output_is_readable(spec_path: Path):
    done = attempt(str(spec_path), "--plain", "--check")
    assert done.returncode == 0
    assert "sqrt(s) = " in done.stderr and "threads" in done.stderr
    assert '{"t":' not in done.stderr, "plain mode must not emit JSON"


def test_list_prints_the_first_events(spec_path: Path, tmp_path: Path):
    stream = tmp_path / "list.jsonl"
    done = attempt(str(spec_path), "--list", "3", stream=stream)
    assert done.returncode == 0, done.stderr
    events = [message for message in read(stream.read_text(encoding="utf-8").splitlines())
              if message.kind == "event"]
    assert len(events) == 3, "exactly the N asked for, not one per generated event"
    assert [message["index"] for message in events] == [0, 1, 2]
    for message in events:
        assert message["particles"] > 0 and message["process"] > 0


# ── stopping ─────────────────────────────────────────────────────────────────

def test_sigint_stops_within_one_chunk_and_exits_six(spec_path: Path, tmp_path: Path):
    """The run must end at a chunk boundary with its partial outputs, not be killed (06 §3.3)."""
    big = variant(spec_path, "big",
                  edit=lambda text: text.replace(f"events = {EVENTS}", "events = 400000"))
    stream = tmp_path / "stopped.jsonl"
    stream.write_text("", encoding="utf-8")
    process = subprocess.Popen(
        ["sh", "-c", f'exec 3>{shlex.quote(str(stream))}; exec "$@"', "hep-run", str(RUN), str(big)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=os.fspath(REPO / "output" / "scratch"))
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if '"k":"progress"' in stream.read_text(encoding="utf-8"):
                break
            assert process.poll() is None, "the run ended before it generated anything"
            time.sleep(0.05)
        else:                                                # pragma: no cover - a stuck generator
            pytest.fail("no progress message within two minutes")
        process.send_signal(signal.SIGINT)
        assert process.wait(timeout=120) == 6
    finally:
        if process.poll() is None:                           # pragma: no cover - only on a failure
            process.kill()
            process.wait(timeout=30)

    reader = messages(stream)
    assert reader.summary["stopped"] is True
    assert 0 < reader.summary["events"] < 400000, "it stopped early, but it did generate"
    chunk = reader.summary["chunk"]
    assert reader.summary["attempted"] % chunk == 0, "it stopped at a chunk boundary"
    assert reader.phase == "finish", "a stopped run still finishes its sinks"
