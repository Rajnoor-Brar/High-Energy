"""`hep watch`, `hep runs` and `hep show` (P3-S04, 06 §5–6).

All three read files only, so the test writes a results tree the way a run would leave one and then
drives the real CLI. That is also the point being tested: a result directory has to explain itself,
including one copied from another machine.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from hekit.cli import main as cli_main
from hekit.results.cli import runs, show
from hekit.run import journal
from hekit.term import model
from hekit.term.cli import find_run, watch


@pytest.fixture
def results(redirect_results: Path) -> Path:
    """A results tree holding one finished point and one finished study."""
    root = redirect_results / "PhotoProduction"
    point = root / "points" / "eic_5x41_ep_NNPDF23lo"
    point.mkdir(parents=True)
    (point / "analysis.yoda").write_text("BEGIN YODA_COUNTER_V3 /_EVTCOUNT\nEND YODA_COUNTER_V3\n",
                                         encoding="utf-8")
    (point / "run.summary.json").write_text(json.dumps({
        "schema": 2, "point": "eic_5x41_ep_NNPDF23lo", "hash": "sha256:" + "ab" * 32,
        "origin": "configs/PhotoProduction/eic.v2.toml --study pdf [1]",
        "host": "pp-exphep", "finished": "2026-09-18T04:21:21Z",
        "run": {"events_requested": 1000, "events": 1000, "attempted": 1024, "threads": 2,
                "chunk": 20, "mode": "serial", "stopped": False, "wall_s": 12.5,
                "xsec_pb": 70818.73, "xsec_err_pb": 2212.24,
                "seeds": {"point": 718623745, "instances": [718623745, 718623746]},
                "warnings": {"maximum for cross section violated": 3}},
    }), encoding="utf-8")
    (point / "provenance.json").write_text(json.dumps({
        "schema": 2, "point": "eic_5x41_ep_NNPDF23lo", "hash": "sha256:" + "ab" * 32,
        "git": {"sha": "0a10209", "branch": "rework", "dirty": True},
        "tools": {"hekit": "0.1.0", "pythia": "8.317", "rivet": "4.1.3"},
        "resources": {"analyses": {"photo_eic": {"so_sha256": "cd" * 32}}},
        "outputs": [{"path": str(point / "analysis.yoda"), "sha256": "ef" * 32, "bytes": 35034}],
        "run": {"events": 1000},
    }), encoding="utf-8")
    logs = point / "logs"
    logs.mkdir()
    (logs / "hep-run.log").write_text(
        " *-------  PYTHIA Settings (changes only)  ----*\n"
        " Beams:eA                                       920.000\n"
        " Beams:idB                                      -11\n"
        " PDF:pSet                                       LHAPDF6:NNPDF23_lo_as_0130_qed\n"
        "\n", encoding="utf-8")

    study = root / "studies" / "01_pdf"
    study.mkdir(parents=True)
    (study / "manifest.json").write_text(json.dumps({
        "schema": 2, "study": "pdf", "project": "PhotoProduction", "serial": 1, "label": "thesis",
        "finished": "2026-09-18T04:22:00Z", "exit": 0,
        "points": [{"name": "eic_5x41_ep_NNPDF23lo", "hash": "sha256:" + "ab" * 32,
                    "path": "points/eic_5x41_ep_NNPDF23lo", "state": "done"}],
        "pages": [], "warnings": [],
    }), encoding="utf-8")
    return root


def invoke(command, arguments, **rest):
    return CliRunner().invoke(command, arguments, obj={"plain": True}, **rest)


# ── hep runs ─────────────────────────────────────────────────────────────────

def test_runs_lists_studies_and_points(results: Path):
    result = invoke(runs, [])
    assert result.exit_code == 0, result.output
    assert "01_pdf" in result.output and "thesis" in result.output
    assert "eic_5x41_ep_NNPDF23lo" in result.output
    assert "done" in result.output
    assert "1.00 k" in result.output, "events, in the terminal's own number format"


def test_runs_says_so_when_there_is_nothing(redirect_results: Path):
    result = invoke(runs, [])
    assert result.exit_code == 0 and "no results" in result.output


def test_runs_shows_a_live_run_first(results: Path):
    point = results / "points" / "eic_5x41_ep_NNPDF23lo"
    (point / journal.PID).write_text(f"{os.getpid()}\n", encoding="utf-8")
    result = invoke(runs, [])
    assert "running now" in result.output and str(os.getpid()) in result.output


def test_runs_has_a_machine_readable_form(results: Path):
    result = invoke(runs, ["--json"])
    payload = json.loads(result.output)
    assert payload["studies"][0]["study"] == "pdf" and payload["studies"][0]["serial"] == 1
    assert payload["points"][0]["events"] == 1000
    assert payload["points"][0]["xsec_pb"] == 70818.73


# ── hep show ─────────────────────────────────────────────────────────────────

def test_show_explains_a_point_from_its_own_files(results: Path):
    result = invoke(show, ["eic_5x41_ep_NNPDF23lo"])
    assert result.exit_code == 0, result.output
    text = result.output
    assert "eic_5x41_ep_NNPDF23lo" in text
    assert "1.00 k of 1.00 k" in text and "1024 attempted" in text
    assert "7.082e+04 pb ± 3.1 %" in text
    assert "718623745" in text, "the seeds the instances really used"
    assert "0a10209+dirty" in text and "rework" in text
    assert "pythia 8.317" in text and "rivet 4.1.3" in text
    assert "×3" in text and "maximum for cross section violated" in text
    assert "photo_eic" in text
    assert "analysis.yoda" in text and "34 KiB" in text


def test_show_parses_the_settings_the_generator_changed(results: Path):
    """06 §5: parsed from the log rather than copied into provenance, so the two cannot disagree."""
    result = invoke(show, ["eic_5x41_ep_NNPDF23lo"])
    assert "settings the generator changed" in result.output
    assert "Beams:idB" in result.output and "-11" in result.output


def test_show_can_print_the_provenance_itself(results: Path):
    result = invoke(show, ["eic_5x41_ep_NNPDF23lo", "--json"])
    payload = json.loads(result.output)
    assert payload["hash"].startswith("sha256:")
    assert payload["tools"]["pythia"] == "8.317"


def test_show_suggests_a_near_miss(results: Path):
    result = invoke(show, ["NNPDF23lo"])
    assert result.exit_code != 0
    assert "did you mean" in str(result.exception) or "did you mean" in result.output


def test_show_works_on_a_directory_from_anywhere(results: Path, tmp_path: Path):
    """A result copied off the machine still explains itself, by path."""
    result = invoke(show, [str(results / "points" / "eic_5x41_ep_NNPDF23lo")])
    assert result.exit_code == 0 and "7.082e+04 pb" in result.output


# ── hep watch ────────────────────────────────────────────────────────────────

def a_journal(directory: Path, *, finished: bool = True) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    with journal.Journal(directory, write_pid=False) as book:
        book.header(cli="hep run eic.toml --study pdf", project="PhotoProduction", git="0a10209",
                    points=["point_a", "point_b"])
        book.point("point_a", model.RUNNING)
        book.raw('{"t": 1.0, "k": "init", "threads": 2, "mode": "serial"}',
                 point="point_a", stage="hep-run")
        book.raw('{"t": 2.0, "k": "progress", "done": 100, "total": 100, "rate": 50.0,'
                 ' "workers": [50, 50]}', point="point_a", stage="hep-run")
        book.raw('{"t": 2.1, "k": "summary", "events": 100, "xsec_pb": 70818.73, "err_pb": 2212.2,'
                 ' "stopped": false}', point="point_a", stage="hep-run")
        book.point("point_a", model.DONE, exit_code=0, outputs=["analysis.yoda"])
        if finished:
            book.done(0)
    return directory


def test_watch_renders_a_finished_run_from_its_journal(results: Path):
    directory = a_journal(results / "points" / "point_a")
    result = invoke(watch, [str(directory), "--plain"])
    assert result.exit_code == 0, result.output
    assert "hep run eic.toml --study pdf" in result.output
    assert "[1/2 point_a]" in result.output
    assert "done" in result.output and "7.082e+04 pb" in result.output


def test_watch_on_a_pipe_is_plain(results: Path):
    """Verification row 'Plain on pipe': no bars, no escapes, one line per event of interest."""
    directory = a_journal(results / "points" / "point_a")
    result = invoke(watch, [str(directory)])            # obj={"plain": True} stands in for a pipe
    assert "█" not in result.output and "\x1b[" not in result.output
    assert result.output.strip().splitlines()[0][2] == ":"


def test_watch_through_a_real_pipe_is_plain(results: Path):
    """The row as written: `hep watch latest | cat`. The group callback turns plain on when stdout is
    not a terminal, and only a real subprocess exercises that."""
    import subprocess
    import sys

    directory = a_journal(results / "points" / "point_a")
    repo = Path(__file__).resolve().parents[3]
    done = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(repo / 'utils' / 'python')!r});"
         f" from hekit.cli import main; raise SystemExit(main(['watch', {str(directory)!r}]))"],
        capture_output=True, timeout=120,
        env=dict(os.environ, HEKIT_RESULTS=str(results.parent)))
    # Decoded explicitly: under a C locale the *parent* would otherwise try ASCII on the child's
    # output, which is how this test first failed under ctest.
    stdout = done.stdout.decode("utf-8", errors="replace")
    assert done.returncode == 0, done.stderr.decode("utf-8", errors="replace")
    assert "█" not in stdout and "\x1b[" not in stdout
    assert "[1/2 point_a]" in stdout


def test_watch_renders_the_dashboard_on_a_terminal(results: Path, monkeypatch):
    directory = a_journal(results / "points" / "point_a")
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    result = CliRunner().invoke(watch, [str(directory)], obj={"plain": False})
    assert result.exit_code == 0, result.output
    assert "points" in result.output and "point_a" in result.output


def test_watch_finds_the_latest_run(results: Path):
    a_journal(results / "points" / "point_a")
    later = a_journal(results / "points" / "point_b")
    os.utime(later / journal.NAME, (2_000_000_000, 2_000_000_000))
    assert find_run("latest") == later
    assert find_run("point_a").name == "point_a"


def test_watch_says_so_when_there_is_nothing_to_watch(redirect_results: Path):
    result = invoke(watch, ["latest"])
    assert result.exit_code != 0
    assert "no run to watch" in str(result.exception) or "no run to watch" in result.output


# ── the command tree ─────────────────────────────────────────────────────────

def test_the_three_commands_are_reachable_from_hep(capsys):
    """They are declared in `hekit.cli.COMMANDS`; this checks they now resolve to real commands."""
    for name in ("watch", "runs", "show"):
        assert cli_main([name, "--help"]) == 0
        output = capsys.readouterr().out
        assert "step P3-S04" not in output, f"{name} is still a placeholder"
        assert "Usage:" in output
