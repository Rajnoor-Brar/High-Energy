"""The package skeleton: errors, paths, the CLI shell and the write guard (P1-S01)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import guard          # tests/guard.py, the write guard itself
from hekit import __version__, cli
from hekit.env import paths
from hekit.errors import HepError, NotImplementedYet, did_you_mean


# ── errors ───────────────────────────────────────────────────────────────────

def test_error_renders_where_and_hint():
    error = HepError("bad value", where="[sweep].seed_step", hint="use 20")
    assert error.render() == "[sweep].seed_step: bad value\n  hint: use 20"
    assert HepError("plain").render() == "plain"
    assert HepError("plain").exit_code == 2


def test_not_implemented_names_its_step():
    error = NotImplementedYet("plan", "P1-S05")
    assert error.exit_code == 3
    assert "P1-S05" in error.render()


@pytest.mark.parametrize(("typo", "expected"), [("plna", "plan"), ("dctor", "doctor")])
def test_did_you_mean(typo, expected):
    assert expected in did_you_mean(typo, cli.COMMANDS)


def test_did_you_mean_is_silent_when_nothing_is_close():
    assert did_you_mean("zzzzzz", cli.COMMANDS) == ""


# ── paths ────────────────────────────────────────────────────────────────────

def test_root_is_found_from_the_package(monkeypatch):
    monkeypatch.delenv(paths.ROOT_VAR, raising=False)
    assert paths.looks_like_root(paths.repo_root())


def test_root_is_found_from_any_directory(monkeypatch, tmp_path):
    monkeypatch.delenv(paths.ROOT_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    assert paths.looks_like_root(paths.repo_root())


def test_declared_root_must_look_like_the_repository(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ROOT_VAR, str(tmp_path))
    with pytest.raises(HepError, match="does not look like the repository"):
        paths.repo_root()


def test_results_follows_its_variable(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.RESULTS_VAR, str(tmp_path))
    assert paths.results_root() == tmp_path.resolve()
    monkeypatch.delenv(paths.RESULTS_VAR)
    assert paths.results_root() == paths.repo_root() / "results"


def test_project_dir_kinds(monkeypatch):
    monkeypatch.delenv(paths.RESULTS_VAR, raising=False)
    root = paths.repo_root()
    assert paths.project_dir("configs", "PhotoProduction") == root / "configs" / "PhotoProduction"
    assert paths.project_dir("output", "PhotoProduction") == root / "output" / "PhotoProduction"
    with pytest.raises(HepError, match="unknown directory kind"):
        paths.project_dir("nowhere", "PhotoProduction")


def test_scratch_is_inside_output():
    assert paths.scratch_root() == paths.output_root() / "scratch"


def test_describe_reports_where_the_roots_came_from(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.RESULTS_VAR, str(tmp_path))
    described = paths.describe()
    assert described["results_from"] == paths.RESULTS_VAR
    assert described["results"] == str(tmp_path.resolve())


# ── the write guard ──────────────────────────────────────────────────────────
# Tested on a fake tree: planting a write in the real configs/ is exactly what the guard forbids.

def test_guard_detects_a_planted_write(tmp_path):
    fake = tmp_path / "configs"
    fake.mkdir()
    (fake / "kept.toml").write_text("a = 1", encoding="utf-8")
    before = guard.snapshot((fake,))
    (fake / "planted.toml").write_text("b = 2", encoding="utf-8")
    found = guard.changes(before, guard.snapshot((fake,)))
    assert found == [f"added {fake / 'planted.toml'}", f"modified {fake}/"]


def test_guard_detects_a_write_that_cleans_up_after_itself(tmp_path):
    """The file set is unchanged, but the directory mtime is not: this is why directories are snapshotted."""
    fake = tmp_path / "configs"
    fake.mkdir()
    before = guard.snapshot((fake,))
    planted = fake / "planted.toml"
    planted.write_text("b = 2", encoding="utf-8")
    planted.unlink()
    assert guard.changes(before, guard.snapshot((fake,))) == [f"modified {fake}/"]


def test_guard_detects_modification_and_removal(tmp_path):
    fake = tmp_path / "fake_results"   # "results" belongs to the redirect_results fixture
    fake.mkdir()
    victim = fake / "point.yoda"
    victim.write_text("x", encoding="utf-8")
    doomed = fake / "gone.yoda"
    doomed.write_text("y", encoding="utf-8")
    before = guard.snapshot((fake,))
    victim.write_text("xx", encoding="utf-8")
    doomed.unlink()
    found = guard.changes(before, guard.snapshot((fake,)))
    assert found == [f"removed {doomed}", f"modified {fake}/", f"modified {victim}"]


def test_guard_is_quiet_when_nothing_changes(tmp_path):
    fake = tmp_path / "configs"
    fake.mkdir()
    (fake / "a.toml").write_text("a = 1", encoding="utf-8")
    before = guard.snapshot((fake,))
    (fake / "a.toml").read_text(encoding="utf-8")            # reading is fine
    assert guard.changes(before, guard.snapshot((fake,))) == []


def test_guard_watches_the_real_trees():
    assert guard.PROTECTED == ("results", "configs")
    assert guard.REPO == paths.repo_root()


def test_results_are_redirected_for_tests(redirect_results):
    assert paths.results_root() == redirect_results
    assert paths.repo_root() not in paths.results_root().parents


# ── the CLI shell ────────────────────────────────────────────────────────────

def run_hep(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    # encoding is explicit: under a C locale (ctest's environment) `text=True` decodes as ASCII and
    # raises on any non-ASCII byte the command prints.
    return subprocess.run([sys.executable, "-m", "hekit.cli", *arguments],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=cwd, timeout=60)


def test_version_shows_the_version_and_the_root(tmp_path):
    done = run_hep("--version", cwd=tmp_path)
    assert done.returncode == 0
    assert __version__ in done.stdout and str(paths.repo_root()) in done.stdout


def test_help_lists_every_command(tmp_path):
    done = run_hep("--help", cwd=tmp_path)
    assert done.returncode == 0
    for name in cli.COMMANDS:
        assert name in done.stdout


def test_unimplemented_command_names_its_step(tmp_path):
    """A command whose module does not exist yet says which step adds it, rather than failing
    obscurely.

    The command is *found* rather than named, so this test does not need editing every time a step
    lands — which it did twice before it was written this way.
    """
    pending = [(name, step) for name, (_, step, _) in cli.COMMANDS.items()
               if not cli.LazyGroup._resolve(name)[1]]
    if not pending:                                       # pragma: no cover - after P10
        pytest.skip("every command is implemented")
    name, step = pending[0]
    done = run_hep(name, "whatever.toml", cwd=tmp_path)
    assert done.returncode == 3, done.stderr
    assert step in done.stderr


def test_the_landed_commands_are_all_real(tmp_path):
    """Every step that has been done must have left a real command behind it."""
    landed = {"plan", "run", "watch", "runs", "show", "plot", "config", "studies", "doctor",
              "pdf", "analyses", "build"}
    for name in sorted(landed):
        assert cli.LazyGroup._resolve(name)[1], f"{name} is still a placeholder"


def test_no_command_is_a_placeholder_any_more(tmp_path):
    """P10-S01's end state: the command tree of 08 §2 is complete.

    The test above names the commands that had landed at the time it was written and needs editing
    as steps land; this one needs no editing ever, and going red means a command was *added* to
    `COMMANDS` without an implementation rather than that one regressed.
    """
    pending = [name for name in cli.COMMANDS if not cli.LazyGroup._resolve(name)[1]]
    assert not pending, f"still placeholders: {', '.join(sorted(pending))}"


@pytest.mark.parametrize("name,step", [("plan", "P1-S05"), ("run", "P3-S05"), ("watch", "P3-S04"),
                                       ("runs", "P3-S04"), ("show", "P3-S04"),
                                       ("plot", "P4-S02")])
def test_an_implemented_command_is_loaded_lazily(tmp_path, name, step):
    """Once a step lands, its command must be the real one and not the placeholder."""
    done = run_hep(name, "--help", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert "Usage:" in done.stdout
    assert step not in done.stdout, f"{name} is still a placeholder"


def test_unknown_command_suggests(tmp_path):
    done = run_hep("plna", cwd=tmp_path)
    assert done.returncode == 2
    assert "did you mean 'plan'" in done.stderr


def test_every_command_of_the_tree_is_registered():
    # docs/rework/08_CLI.md §2
    expected = {"run", "plan", "plot", "compare", "watch", "runs", "show", "events", "store", "proc",
                "analyses", "studies", "config", "pdf", "build", "bench", "doctor", "clean", "new"}
    assert set(cli.COMMANDS) == expected
    for name, (target, step, summary) in cli.COMMANDS.items():
        assert ":" in target and step[0] == "P" and summary


def test_help_stays_fast(tmp_path):
    """No heavy import at start-up: click only, no rich, yoda or ROOT."""
    import time

    start = time.monotonic()
    run_hep("--help", cwd=tmp_path)
    assert time.monotonic() - start < 1.0          # generous for a cold subprocess; measured ~0.05 s


def test_start_up_imports_nothing_heavy(tmp_path):
    code = ("import sys; from hekit import cli; "
            "heavy = [m for m in ('rich', 'yoda', 'ROOT', 'numpy', 'matplotlib') if m in sys.modules]; "
            "print(heavy)")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tmp_path, timeout=60)
    assert done.stdout.strip() == "[]", done.stdout
