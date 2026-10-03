"""Where things are, and how a name in a config becomes a path (rank 0).

docs/04_Config_Reference.md §2. Every key that takes a path has exactly one convention root:
there is no search path and no fallback, because a lookup that tries several places is how v1's
00/B18 happened.

    bare `name`     → the convention root of the key + name
    `./sub/name`    → the repository root + sub/name (not the working directory: V13)
    `/abs/path`     → as written
    `../x`          → refused; write ./… instead

The point-level roots (a point's output and results directories) arrive with the runner in P1.
"""

from __future__ import annotations

import os
from pathlib import Path

from .errors import HepError

#: A directory is the repository root when it holds all of these.
MARKERS = ("configs", "modules", "utils/Env")

ROOT_VAR = "HEKIT_ROOT"
RESULTS_VAR = "HEKIT_RESULTS"
OUTPUT_VAR = "HEKIT_OUTPUT"
CONFIGS_VAR = "HEKIT_CONFIGS"


def is_root(path: Path) -> bool:
    return all((path / marker).is_dir() for marker in MARKERS)


def repo_root() -> Path:
    """The repository: $HEKIT_ROOT if set, else the first ancestor of this file holding the markers."""
    if os.environ.get(ROOT_VAR):
        root = Path(os.environ[ROOT_VAR]).resolve()
        if not is_root(root):
            raise HepError(f"${ROOT_VAR} = {root} is not the repository",
                           hint=f"it must contain {', '.join(MARKERS)}")
        return root
    for candidate in Path(__file__).resolve().parents:
        if is_root(candidate):
            return candidate
    raise HepError("cannot find the repository root",
                   hint=f"set ${ROOT_VAR}, or run from a checkout containing {', '.join(MARKERS)}")


def results_root() -> Path:
    """Where products go: $HEKIT_RESULTS (tests set it) or <repo>/results."""
    value = os.environ.get(RESULTS_VAR)
    return Path(value).resolve() if value else repo_root() / "results"


def output_root() -> Path:
    """Where technical files go: $HEKIT_OUTPUT (tests set it) or <repo>/output."""
    value = os.environ.get(OUTPUT_VAR)
    return Path(value).resolve() if value else repo_root() / "output"


def configs_root() -> Path:
    """Where run TOMLs and their cards are: $HEKIT_CONFIGS (tests set it, to tests/fixtures/configs) or
    <repo>/configs."""
    value = os.environ.get(CONFIGS_VAR)
    return Path(value).resolve() if value else repo_root() / "configs"


def build_root() -> Path:
    return repo_root() / "build"


#: Keys whose root is the point's own directory: resolve() is always given it (`root=`).
POINT_KEYS = ("prelim", "input", "output")

#: The convention root of each path-taking key, as a function of the project (04 §2).
ROOTS = {
    "config":     lambda project: configs_root(),
    "master":     lambda project: configs_root() / project,
    "baseconfig": lambda project: configs_root() / project,
    "executable": lambda project: build_root() / project,
    "data":       lambda project: repo_root() / "datasets",
    "filters":    lambda project: configs_root() / project,
    "root_style": lambda project: configs_root() / project,
}


def resolve(value: str, key: str, *, project: str = "", root: Path | None = None,
            where: str | None = None) -> Path:
    """The path a config value names, under the rules above.

    `root` overrides the convention root (the runner passes a point's directory for `[prelim]`
    names and outputs); otherwise `key` picks it from ROOTS.
    """
    if not isinstance(value, str) or not value:
        raise HepError(f"expected a path, got {value!r}", where=where)
    if value.startswith("../") or value == ".." or "/../" in value:
        raise HepError(f"'{value}' climbs out of its root", where=where,
                       hint="write it relative to the repository root as ./…, or give an absolute path")
    if value.startswith("/"):
        return Path(value)
    if value.startswith("./"):
        return repo_root() / value[2:]
    if root is None:
        if key in POINT_KEYS:
            raise HepError(f"'{key}' paths are under a point's directory, which was not given", where=where)
        if key not in ROOTS:
            raise HepError(f"no convention root for key '{key}'", where=where)
        root = ROOTS[key](project)
    return root / value


def config_file(name: str) -> Path:
    """`hep run <config>`: configs/<config>, `.toml` optional, unless it starts with ./ or /."""
    path = resolve(name, "config")
    if path.suffix != ".toml" and not path.exists():
        path = path.with_name(path.name + ".toml")
    if not path.is_file():
        raise HepError(f"no run config '{name}'", where=str(path),
                       hint="configs are looked up under configs/<Project>/<name>.toml; "
                            "start the name with ./ to give a path from the repository root")
    return path
