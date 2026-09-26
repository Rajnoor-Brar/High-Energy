"""Root lookup that never raises, for provenance: a missing repository is recorded, not fatal."""

from __future__ import annotations

from pathlib import Path


def root_or_cwd() -> Path:
    from ..env.paths import repo_root
    from ..errors import HepError

    try:
        return repo_root()
    except HepError:
        return Path.cwd()
