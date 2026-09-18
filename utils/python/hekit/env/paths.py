"""Where things are.

Every path the toolkit uses is derived from the repository root, so commands work from any directory
(00/B18: the legacy tools resolved `configs/`, `output/` and `results/` against the current directory).

Resolution order for the root:
1. `HEKIT_ROOT`, if it names a directory that looks like the repository;
2. walking up from this package (an editable install lives inside the repository);
3. walking up from the current directory.

`HEKIT_RESULTS` redirects only the results tree, which is what tests set (see tests/conftest.py).
The idea is taken from `legacy/utils/Utility/Paths.hh:25-54` (env var, else walk up to an anchor).
"""

from __future__ import annotations

import os
from pathlib import Path

from ..errors import HepError

#: A directory is the repository root when it holds all of these. `sources/` was one of them until
#: P4-S06 moved the last generator into `legacy/` and removed it; `analyses/` is the durable
#: replacement, since every project has one.
MARKERS = ("docs/rework", "configs", "analyses")

ROOT_VAR = "HEKIT_ROOT"
RESULTS_VAR = "HEKIT_RESULTS"


def looks_like_root(path: Path) -> bool:
    return all((path / marker).is_dir() for marker in MARKERS)


def _walk_up(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if looks_like_root(candidate):
            return candidate
    return None


def repo_root() -> Path:
    """The repository root, or a HepError explaining how to say where it is."""
    declared = os.environ.get(ROOT_VAR)
    if declared:
        path = Path(declared).expanduser()
        if not looks_like_root(path):
            raise HepError(f"{ROOT_VAR} does not look like the repository: {path}",
                           where=ROOT_VAR,
                           hint=f"it must contain {', '.join(MARKERS)}; unset it to search upwards instead")
        return path.resolve()
    for start in (Path(__file__).resolve().parent, Path.cwd().resolve()):
        found = _walk_up(start)
        if found is not None:
            return found
    raise HepError("cannot find the repository root",
                   hint=f"run inside the repository or set {ROOT_VAR}")


def configs_root() -> Path:
    return repo_root() / "configs"


def sources_root() -> Path:
    return repo_root() / "sources"


def analyses_root() -> Path:
    return repo_root() / "analyses"


def build_root() -> Path:
    """Where CMake put the compiled things. `HEKIT_BUILD` overrides it, as `hep doctor` reports."""
    from os import environ
    override = environ.get("HEKIT_BUILD")
    return Path(override).expanduser() if override else repo_root() / "build"


def output_root() -> Path:
    return repo_root() / "output"


def scratch_root() -> Path:
    """Gitignored scratch area; everything a test or a dry run writes belongs here."""
    return output_root() / "scratch"


def results_root() -> Path:
    """`HEKIT_RESULTS` when set (tests), else `<repo>/results`."""
    declared = os.environ.get(RESULTS_VAR)
    return Path(declared).expanduser().resolve() if declared else repo_root() / "results"


def project_dir(kind: str, project: str) -> Path:
    """`configs/<project>`, `results/<project>`, `output/<project>`, `sources/<project>`, `analyses/<project>`."""
    roots = {"configs": configs_root, "results": results_root, "output": output_root,
             "sources": sources_root, "analyses": analyses_root}
    if kind not in roots:
        raise HepError(f"unknown directory kind '{kind}'", hint=f"one of: {', '.join(sorted(roots))}")
    return roots[kind]() / project


def mpl_config_dir(run: str = "") -> Path:
    """A private `MPLCONFIGDIR` for a plotting run (00/B19).

    matplotlib caches fonts under `$HOME/.config/matplotlib` and rebuilds it when it looks stale;
    two runs doing that at once corrupt each other's cache, and a read-only home makes matplotlib
    warn on every import. A directory under `output/scratch/` avoids both.
    """
    directory = scratch_root() / "mpl" / (run or "default")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def describe() -> dict[str, str]:
    """What `hep doctor` and `hep --version` report about the layout."""
    root = repo_root()
    return {
        "root": str(root),
        "root_from": ROOT_VAR if os.environ.get(ROOT_VAR) else "search",
        "configs": str(configs_root()),
        "results": str(results_root()),
        "results_from": RESULTS_VAR if os.environ.get(RESULTS_VAR) else "default",
        "output": str(output_root()),
        "scratch": str(scratch_root()),
    }
