"""The repository's git state, as recorded in provenance and printed by `hep --version`.

Kept dependency-free and quiet: a missing git, a missing repository or a slow filesystem must never
break a command, so every failure degrades to "unknown".
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(root: Path, *arguments: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(root), *arguments],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def git_state(root: Path | None = None) -> dict[str, str | bool | None]:
    """`{sha, branch, dirty}`; `sha` is None outside a repository."""
    if root is None:
        from .paths_bridge import root_or_cwd
        root = root_or_cwd()
    sha = _git(root, "rev-parse", "--short", "HEAD")
    if sha is None:
        return {"sha": None, "branch": None, "dirty": None}
    status = _git(root, "status", "--porcelain")
    return {"sha": sha, "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(status)}
