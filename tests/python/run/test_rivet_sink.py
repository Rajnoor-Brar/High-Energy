"""The Rivet sink and the results writer, against the real binary (P2-S05).

This is the step the rework exists for: the analysis now runs in the same process as the generator
instead of behind a HepMC FIFO (D4). The things worth testing are therefore not "does Rivet work" but
the joins — that σ reaches the YODA as the run measured it, that a stopped run cannot be mistaken for a
finished one (00/B3), and that an analysis-option variant stays inside one generation (03 §4).

The fixtures run the binary once per spec shape and share the result, because each run costs a Pythia
initialisation.
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
from hekit.run.status import StatusReader                    # noqa: E402

REPO = Path(__file__).resolve().parents[3]
INPUTS = REPO / "tests" / "golden" / "inputs" / "PhotoProduction"
RUN = REPO / "build" / "bin" / "hep-run"
PLUGIN = REPO / "build" / "analyses" / "PhotoProduction" / "Rivet_photo_eic.so"

yoda = pytest.importorskip("yoda")

pytestmark = [
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)"),
    pytest.mark.skipif(not PLUGIN.is_file(), reason="build the Rivet plugin first (target rivet_PhotoProduction)"),
]

EVENTS = 200
THREADS = 2


# ── planning and running ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    directory = tmp_path_factory.mktemp("PhotoProduction")
    migrated.write_v2(INPUTS / "eic.toml", directory / "eic.toml")
    (directory / "photo_ep.cmnd").write_bytes((INPUTS / "photo_ep.cmnd").read_bytes())
    return directory


def plan_spec(project: Path, directory: Path, *, study: str = "single", events: int = EVENTS) -> Path:
    """One planned, runnable spec — the same path `hep plan --write` takes."""
    config = load_config(project / "eic.toml", machine_file=None, project="PhotoProduction")
    plan = builder.build(config, sweep.select(config, study=study))
    group = plan.groups[0]
    group.spec["run"]["events"] = events
    group.spec["run"]["threads"] = THREADS
    group.spec["run"]["seeds"]["instances"] = group.spec["run"]["seeds"]["instances"][:THREADS]
    written = spec_module.write(plan, directory)
    return next(path for path in written if path.name == "run.toml")


def edited(spec: Path, name: str, edit) -> Path:
    target = spec.with_name(f"{name}.toml")
    target.write_text(edit(spec.read_text(encoding="utf-8")), encoding="utf-8")
    return target


def run_spec(spec: Path, *arguments: str, stream: Path | None = None, timeout: int = 300):
    command = [str(RUN), str(spec), *arguments]
    if stream is not None:
        command = ["sh", "-c", f'exec 3>{shlex.quote(str(stream))}; exec "$@"', "hep-run", *command]
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                          cwd=os.fspath(REPO / "output" / "scratch"))


def output_dir(spec: Path) -> Path:
    import tomllib
    return Path(tomllib.loads(spec.read_text(encoding="utf-8"))["output"]["dir"])


@pytest.fixture(scope="module")
def analysed(project: Path, tmp_path_factory):
    """One finished run with the Rivet sink: the spec, its output directory and the status stream."""
    spec = plan_spec(project, tmp_path_factory.mktemp("rivet"))
    stream = tmp_path_factory.mktemp("status") / "rivet.jsonl"
    done = run_spec(spec, stream=stream)
    reader = StatusReader().feed_lines(stream.read_text(encoding="utf-8").splitlines())
    return done, spec, output_dir(spec), reader


# ── a finished run ───────────────────────────────────────────────────────────

def test_a_run_with_a_rivet_sink_writes_a_yoda_and_a_summary(analysed):
    done, _, directory, _ = analysed
    assert done.returncode == 0, done.stderr
    assert sorted(path.name for path in directory.iterdir()) == [
        "analysis.yoda", "point.cmnd", "run.summary.json", "run.toml"]


def test_nothing_temporary_or_partial_is_left_behind(analysed):
    """D22: the file appears complete or not at all — no `.tmp`, and no partial next to a result."""
    _, _, directory, _ = analysed
    assert not [path.name for path in directory.iterdir() if ".tmp." in path.name]
    assert not (directory / "analysis.partial.yoda").exists()


def test_the_analysis_objects_are_there(analysed):
    _, _, directory, _ = analysed
    objects = yoda.read(str(directory / "analysis.yoda"))
    histograms = [path for path in objects if path.startswith("/photo_eic/")]
    assert len(histograms) == 17, sorted(objects)
    assert all(objects[path].numBins() > 0 for path in histograms)


def test_the_cross_section_in_the_yoda_is_the_one_the_run_measured(analysed):
    """D-Q1 end to end: σ combined from the instances → setCrossSection → `/_XSEC`."""
    _, _, directory, reader = analysed
    objects = yoda.read(str(directory / "analysis.yoda"))
    summary = json.loads((directory / "run.summary.json").read_text(encoding="utf-8"))
    xsec = objects["/_XSEC"]
    assert xsec.val() == pytest.approx(summary["run"]["xsec_pb"], rel=1e-6)
    assert xsec.val() == pytest.approx(reader.summary["xsec_pb"], rel=1e-6)
    # The error is not thrown away on the way in, which is the whole point of combining it (D-Q1).
    assert xsec.totalErrAvg() == pytest.approx(summary["run"]["xsec_err_pb"], rel=1e-6)
    assert 0 < summary["run"]["xsec_err_pb"] < summary["run"]["xsec_pb"]


def test_the_event_count_in_the_yoda_matches_the_run(analysed):
    _, _, directory, _ = analysed
    objects = yoda.read(str(directory / "analysis.yoda"))
    assert objects["/_EVTCOUNT"].val() == pytest.approx(EVENTS)


def test_the_summary_carries_what_only_hep_run_knows(analysed):
    """07 §2: `hekit.prov` folds this into provenance rather than parsing a log for it."""
    _, spec, directory, _ = analysed
    summary = json.loads((directory / "run.summary.json").read_text(encoding="utf-8"))
    assert summary["schema"] == 2
    assert summary["point"] and summary["hash"].startswith("sha256:")
    run = summary["run"]
    assert (run["events_requested"], run["events"]) == (EVENTS, EVENTS)
    assert run["attempted"] >= run["events"], "attempts are not successes (00/B21)"
    assert (run["threads"], run["mode"], run["stopped"]) == (THREADS, "serial", False)
    assert run["chunk"] % THREADS == 0
    import tomllib
    planned = tomllib.loads(spec.read_text(encoding="utf-8"))["run"]["seeds"]
    assert run["seeds"] == {"point": planned["point"], "instances": planned["instances"]}
    assert isinstance(run["warnings"], dict), "a count per message, not a wall of text"
    assert summary["outputs"] == [
        {"kind": "yoda", "path": str(directory / "analysis.yoda"), "partial": False}]


def test_the_status_stream_says_what_rivet_did(analysed):
    _, _, _, reader = analysed
    assert reader.sinks == ["rivet"]
    loaded = [entry for entry in reader.logs if entry["source"] == "rivet"]
    assert any("loaded photo_eic" in entry["msg"] for entry in loaded), loaded
    assert any("events analysed" in entry["msg"] for entry in loaded), loaded


# ── a missing analysis ───────────────────────────────────────────────────────

@pytest.mark.parametrize("arguments", [(), ("--check",)], ids=["run", "check"])
def test_an_unknown_analysis_fails_before_any_event(project, tmp_path, arguments):
    """Rivet only *warns* about a name it cannot find, so a typo would otherwise cost a whole run."""
    spec = plan_spec(project, tmp_path)
    broken = edited(spec, "nope",
                    lambda text: re.sub(r"analyses = \[[^\]]*\]", 'analyses = ["NOPE_2099_I1"]', text))
    done = run_spec(broken, *arguments, "--plain")
    assert done.returncode == 1
    assert "unknown Rivet analysis: NOPE_2099_I1" in done.stderr
    assert "RIVET_ANALYSIS_PATH" in done.stderr, "the message has to say where it looked"
    assert not list(output_dir(spec).glob("*.yoda")), "it must not write an empty result"


def test_an_unknown_sink_kind_is_refused(project, tmp_path):
    """A silently skipped sink would look like a successful run that produced nothing."""
    spec = plan_spec(project, tmp_path)
    broken = edited(spec, "weird", lambda text: text.replace('kind = "rivet"', 'kind = "quark"'))
    done = run_spec(broken, "--check", "--plain")
    assert done.returncode == 1 and "unknown sink kind: quark" in done.stderr


# ── option variants stay in one generation (03 §4) ───────────────────────────

def test_two_option_variants_share_one_run_and_one_yoda(project, tmp_path):
    """An analysis option is not a separate generation: both variants are booked in one handler."""
    spec = plan_spec(project, tmp_path, study="radius", events=40)
    done = run_spec(spec, "--plain")
    assert done.returncode == 0, done.stderr
    objects = yoda.read(str(output_dir(spec) / "analysis.yoda"))
    variants = sorted({path.split("/")[1] for path in objects if path.startswith("/photo_eic")})
    assert variants == ["photo_eic:R=0.4", "photo_eic:R=0.7", "photo_eic:R=1.0"], variants
    # One σ and one event count for the generation, not one per variant.
    assert objects["/_EVTCOUNT"].val() == pytest.approx(40)


# ── dumps ────────────────────────────────────────────────────────────────────

def test_dump_every_is_refused_for_a_non_reentrant_analysis(project, tmp_path):
    """Rivet 4.1.3 skips finalize in a dump unless the analysis is re-entrant, so the dump would be
    unscaled — better no file than a wrong one. photo_eic becomes re-entrant in P4-S05."""
    spec = plan_spec(project, tmp_path, events=40)
    dumping = edited(spec, "dump", lambda text: text.replace("dump_every = 0", "dump_every = 20"))
    done = run_spec(dumping, "--plain")
    assert done.returncode == 0, done.stderr
    assert "dump_every ignored" in done.stderr and "not re-entrant" in done.stderr
    assert not (output_dir(spec) / "analysis.dump.yoda").exists()


# ── a stopped run ────────────────────────────────────────────────────────────

def test_a_stopped_run_writes_only_a_partial_yoda(project, tmp_path):
    """00/B3: the defect this replaces left a final-named YODA behind when a run was killed."""
    spec = plan_spec(project, tmp_path, events=400000)
    stream = tmp_path / "stopped.jsonl"
    stream.write_text("", encoding="utf-8")
    process = subprocess.Popen(
        ["sh", "-c", f'exec 3>{shlex.quote(str(stream))}; exec "$@"', "hep-run", str(RUN), str(spec)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=os.fspath(REPO / "output" / "scratch"))
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if '"k":"progress"' in stream.read_text(encoding="utf-8"):
                break
            assert process.poll() is None, "the run ended before it generated anything"
            time.sleep(0.05)
        else:                                                # pragma: no cover - a stuck generator
            pytest.fail("no progress message within three minutes")
        process.send_signal(signal.SIGINT)
        assert process.wait(timeout=180) == 6
    finally:
        if process.poll() is None:                           # pragma: no cover - only on a failure
            process.kill()
            process.wait(timeout=30)

    directory = output_dir(spec)
    assert (directory / "analysis.partial.yoda").is_file()
    assert not (directory / "analysis.yoda").exists(), "never both names (07 §1)"
    assert not [path.name for path in directory.iterdir() if ".tmp." in path.name]

    summary = json.loads((directory / "run.summary.json").read_text(encoding="utf-8"))
    assert summary["run"]["stopped"] is True
    assert 0 < summary["run"]["events"] < 400000
    assert summary["outputs"] == [
        {"kind": "yoda", "path": str(directory / "analysis.partial.yoda"), "partial": True}]

    # The partial file is a readable YODA holding the events that were analysed, not a truncated one.
    objects = yoda.read(str(directory / "analysis.partial.yoda"))
    assert objects["/_EVTCOUNT"].val() == pytest.approx(summary["run"]["events"])
    assert len([path for path in objects if path.startswith("/photo_eic/")]) == 17
