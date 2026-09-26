"""`hep run` end to end, with the real binary (P3-S05).

`tests/e2e/mini.toml` is two generations of a few hundred events: small enough for a test suite, big
enough to exercise the whole chain — plan, preflight, spawn, status stream, journal, results layout,
skip rule, provenance and the YODA stamp.

Marked `slow` and registered as the ctest test `e2e`; the fast suite does not run a generator.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "tests" / "e2e" / "mini.toml"
RUN = REPO / "build" / "bin" / "hep-run"
PLUGIN = REPO / "build" / "analyses" / "PhotoProduction" / "Rivet_photo_eic.so"

pytest.importorskip("yoda")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)"),
    pytest.mark.skipif(not PLUGIN.is_file(), reason="build the Rivet plugin first"),
]

POINTS = ["mini_27x920_MSTW08lo", "mini_27x920_NNPDF23lo"]


def hep(*arguments: str, results: Path, timeout: int = 1800, expect: int | None = 0,
        stdin=subprocess.DEVNULL):
    """Run the real `hep` CLI with its results redirected into the test's own tree."""
    done = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(REPO / 'utils' / 'python')!r});"
         f" from hekit.cli import main; raise SystemExit(main({list(arguments)!r}))"],
        cwd=REPO, capture_output=True, timeout=timeout, stdin=stdin,
        env=dict(os.environ, HEKIT_RESULTS=str(results)))
    done.text_stdout = done.stdout.decode("utf-8", errors="replace")
    done.text_stderr = done.stderr.decode("utf-8", errors="replace")
    if expect is not None:
        assert done.returncode == expect, done.text_stdout + done.text_stderr
    return done


def project_root(results: Path) -> Path:
    return results / "e2e"


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    """One complete run of the e2e config, shared by the tests that inspect what it left."""
    results = tmp_path_factory.mktemp("e2e") / "results"
    done = hep("run", str(CONFIG), "--study", "pdf", "--plain", results=results)
    return done, results


# ── the run itself ───────────────────────────────────────────────────────────

def test_a_run_produces_a_yoda_and_provenance_for_every_generation(ran):
    """The step's 'e2e' row: 2 groups, YODA + provenance."""
    _, results = ran
    points = project_root(results) / "points"
    assert sorted(path.name for path in points.iterdir()) == POINTS
    for name in POINTS:
        directory = points / name
        assert (directory / "analysis.yoda").is_file()
        assert (directory / "run.summary.json").is_file()
        assert (directory / "provenance.json").is_file()
        assert (directory / "run.toml").is_file() and (directory / "point.cmnd").is_file()
        assert (directory / "status.jsonl").is_file()
        assert (directory / "logs" / "hep-run.log").is_file()
        assert not (directory / "run.pid").exists(), "the pid file goes when the run ends"
        assert not list(directory.glob("*.tmp.*")) and not list(directory.glob("*.partial.yoda"))


def test_the_plain_output_reads_like_06_section_2(ran):
    done, _ = ran
    lines = [line for line in done.text_stdout.splitlines() if line.strip()]
    assert lines[0].split()[1] == "start"
    assert any("[1/2 mini_27x920_MSTW08lo] hep-run  start (2 threads, serial)" in line
               for line in lines), lines
    assert any("done" in line and "σ" in line and "analysis.yoda" in line for line in lines)
    assert any(line.endswith("2 done  " + line.split()[-1]) for line in lines if "end " in line)
    assert lines[-1].startswith("hep: 2 done in "), lines[-1]
    for line in lines[:-1]:
        assert line[2] == ":" and line[5] == ":", line


def test_the_two_generations_have_different_physics(ran):
    """Two PDF sets, so two identities, two seeds and two cross sections."""
    _, results = ran
    summaries = [json.loads((project_root(results) / "points" / name / "run.summary.json")
                            .read_text(encoding="utf-8")) for name in POINTS]
    assert summaries[0]["hash"] != summaries[1]["hash"]
    assert summaries[0]["run"]["seeds"] != summaries[1]["run"]["seeds"]
    assert summaries[0]["run"]["xsec_pb"] != summaries[1]["run"]["xsec_pb"]
    for summary in summaries:
        assert summary["run"]["events"] == 300
        assert summary["run"]["threads"] == 2 and summary["run"]["mode"] == "serial"
        assert summary["run"]["xsec_pb"] > 0 and summary["run"]["xsec_err_pb"] > 0


def test_provenance_ties_the_result_to_its_inputs(ran):
    _, results = ran
    payload = json.loads((project_root(results) / "points" / POINTS[0] / "provenance.json")
                         .read_text(encoding="utf-8"))
    assert payload["schema"] == 2
    assert payload["point"] == POINTS[0] and payload["hash"]
    assert payload["origin"]["study"] == "pdf" and payload["origin"]["config"].endswith("mini.toml")
    assert [card["sha256"] for card in payload["cards"]] == [card["sha256"] for card in
                                                             payload["cards"] if card["sha256"]]
    assert payload["resources"]["pdf_sets"] == ["MSTW2008lo68cl"]
    assert payload["resources"]["analyses"]["photo_eic"]["so_sha256"]
    assert payload["outputs"][0]["path"].endswith("analysis.yoda")
    assert payload["outputs"][0]["bytes"] > 0
    assert payload["tools"]["pythia"] and payload["tools"]["rivet"]
    assert payload["run"]["events"] == 300, "hep-run's own numbers, not a second copy"


def test_the_yoda_is_stamped_with_its_identity(ran):
    """07 §2: a file that leaves its directory still says which point it is."""
    import yoda

    _, results = ran
    directory = project_root(results) / "points" / POINTS[0]
    objects = yoda.read(str(directory / "analysis.yoda"))
    counter = objects["/_EVTCOUNT"]
    assert counter.annotation("HekitPoint") == POINTS[0]
    assert counter.annotation("HekitHash")
    assert counter.annotation("HekitGit")
    assert len([path for path in objects if path.startswith("/photo_eic/")]) == 17


def test_the_study_manifest_points_at_the_points(ran):
    _, results = ran
    studies = sorted((project_root(results) / "studies").iterdir())
    assert [path.name for path in studies] == ["01_pdf"], "D-Q3: a study run carries a serial"
    payload = json.loads((studies[0] / "manifest.json").read_text(encoding="utf-8"))
    assert payload["study"] == "pdf" and payload["serial"] == 1 and payload["exit"] == 0
    assert [entry["name"] for entry in payload["points"]] == POINTS
    assert all(not Path(entry["path"]).is_absolute() for entry in payload["points"])


def test_the_journal_can_be_replayed_by_hep_watch(ran):
    _, results = ran
    directory = project_root(results) / "points" / POINTS[0]
    done = hep("watch", str(directory), "--plain", results=results)
    assert "[1/2 mini_27x920_MSTW08lo]" in done.text_stdout
    assert "done" in done.text_stdout


def test_hep_show_explains_the_result(ran):
    _, results = ran
    done = hep("show", POINTS[0], results=results)
    assert "300 of 300" in done.text_stdout
    assert "pb" in done.text_stdout and "photo_eic" in done.text_stdout


# ── the other verification rows ──────────────────────────────────────────────

def test_a_second_run_skips_what_is_already_there(tmp_path):
    """The 'Rerun' row: done points are skipped, and the skip is decided by name, hash and result."""
    results = tmp_path / "results"
    hep("run", str(CONFIG), "--study", "pdf", "--plain", results=results)
    again = hep("run", str(CONFIG), "--study", "pdf", "--plain", results=results)
    assert "0 done, 2 skipped" in again.text_stdout
    assert "name, hash and a finished result all match" in again.text_stdout

    # --rerun overrides it, and a changed configuration is refused rather than overwritten.
    forced = hep("run", str(CONFIG), "--study", "pdf", "--plain", "--rerun", results=results)
    assert "2 done" in forced.text_stdout
    # A *physics* change, not a seed: the seed is derived from the identity (03 §5), so changing it
    # deliberately does not change the hash — pTHatMin does.
    changed = hep("run", str(CONFIG), "--study", "pdf", "--plain",
                  "--set", "static.gen.PhaseSpace:pTHatMin=5", results=results, expect=None)
    assert changed.returncode != 0
    assert "different identity" in changed.text_stderr
    assert "--rerun" in changed.text_stderr


def test_a_partial_result_is_rerun(tmp_path):
    """A stopped run leaves analysis.partial.yoda, and the next `hep run` redoes that point."""
    results = tmp_path / "results"
    hep("run", str(CONFIG), "--study", "pdf", "--plain", results=results)
    directory = project_root(results) / "points" / POINTS[0]
    (directory / "analysis.yoda").rename(directory / "analysis.partial.yoda")
    again = hep("run", str(CONFIG), "--study", "pdf", "--plain", results=results)
    assert "1 done, 1 skipped" in again.text_stdout
    assert (directory / "analysis.yoda").is_file()
    assert not (directory / "analysis.partial.yoda").exists(), "never both (07 §1)"


def test_a_point_that_cannot_initialise_stops_before_anything_is_generated(tmp_path):
    """The 'Preflight' row: `hep-run --check` for every generation before the first spawn."""
    results = tmp_path / "results"
    done = hep("run", str(CONFIG), "--study", "pdf", "--plain",
               "--set", "static.gen.Photon:ProcessType=2", results=results, expect=None)
    assert done.returncode == 3, done.text_stderr
    assert "cannot run" in done.text_stderr and "failed to initialise" in done.text_stderr
    assert not list(project_root(results).rglob("*.yoda")), "nothing was generated"
    assert not (project_root(results) / "studies").exists(), "and no study was started"


def test_check_stops_after_the_preflight(tmp_path):
    results = tmp_path / "results"
    done = hep("run", str(CONFIG), "--study", "pdf", "--check", "--plain", results=results)
    assert "checked 2 generation" in done.text_stdout
    assert not list(project_root(results).rglob("*.yoda"))


def test_ctrl_c_stops_at_a_checkpoint_and_starts_nothing_new(tmp_path):
    """The 'Ctrl-C' row. Every stage runs in its own session, so `hep` forwards the signal itself."""
    results = tmp_path / "results"
    process = subprocess.Popen(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(REPO / 'utils' / 'python')!r});"
         f" from hekit.cli import main; raise SystemExit(main("
         f"{['run', str(CONFIG), '--study', 'pdf', '--plain', '--events', '200000']!r}))"],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        # Explicit: a C locale would otherwise decode the child's UTF-8 as ASCII and raise.
        encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, start_new_session=True,
        env=dict(os.environ, HEKIT_RESULTS=str(results)))
    try:
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            line = process.stdout.readline()
            if not line:
                pytest.fail("the run ended before it generated anything")
            if "%" in line and "ev/s" in line:
                break
        else:                                            # pragma: no cover - a very slow machine
            pytest.fail("no progress within five minutes")
        time.sleep(0.3)
        os.killpg(os.getpgid(process.pid), signal.SIGINT)
        output = process.stdout.read()
        assert process.wait(timeout=300) == 6
    finally:
        if process.poll() is None:                       # pragma: no cover - only on a failure
            process.kill()
            process.wait(timeout=30)

    first = project_root(results) / "points" / POINTS[0]
    second = project_root(results) / "points" / POINTS[1]
    assert (first / "analysis.partial.yoda").is_file()
    assert not (first / "analysis.yoda").exists()
    assert "stopped" in output
    assert not list(second.glob("*.yoda")), "the next point was never started"
    summary = json.loads((first / "run.summary.json").read_text(encoding="utf-8"))
    assert summary["run"]["stopped"] is True
    assert 0 < summary["run"]["events"] < 200000
