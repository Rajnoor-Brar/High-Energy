"""Helpers the integration tests share: run `hep` with its outputs under a scratch folder.

Configs resolve under tests/fixtures/configs (HEKIT_CONFIGS, set by conftest.py and inherited here).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HEP = REPO / "utils" / "Env" / "hep"


def env(where: Path) -> dict:
    """The environment of a run whose output/ and results/ are under `where`."""
    return dict(os.environ, HEKIT_OUTPUT=str(where / "output"), HEKIT_RESULTS=str(where / "results"))


def hep(where: Path, *args: str, command: str = "run", plain: bool = True, timeout: float = 1800,
        wait: bool = True):
    """`hep <command> ARGS [--plain]` with outputs under `where`: the finished process, or (wait=False) the
    running one, its output merged into stdout."""
    argv = [str(HEP), command, *map(str, args), *(["--plain"] if plain else [])]
    if not wait:
        return subprocess.Popen(argv, cwd=REPO, env=env(where), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8")
    return subprocess.run(argv, cwd=REPO, env=env(where), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def hep_ok(where: Path, *args: str, timeout: float = 1800) -> str:
    """`hep run ARGS --plain`, which must succeed; its stdout."""
    done = hep(where, *args, timeout=timeout)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    return done.stdout


def folder(config: str, configuration: str | None = None) -> Path:
    """<project>/<run name>/<NN_label> of a configuration, as the runner names it (tools.run_dir, V45):
    tests never spell the layout out."""
    from runner import config as configmod, tools
    run = configmod.load(config)
    return tools.run_dir(run, run.configuration(configuration))

