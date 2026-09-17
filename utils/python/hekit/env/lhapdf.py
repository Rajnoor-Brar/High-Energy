"""LHAPDF sets: which a plan needs, which are installed, and installing the rest (08 §2).

A missing PDF set is one of the two ways a long run dies late (the other is a missing analysis), so
`hep plan` can ask this before anything starts.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from ..errors import HepError

#: How a Pythia card names an LHAPDF set: `LHAPDF6:NNPDF23_lo_as_0130_qed`.
PREFIXES = ("LHAPDF6:", "LHAPDF5:")
#: Keys whose value names a PDF set.
PDF_KEYS = {"pdf:pset", "pdf:psethardb", "pdf:pomset", "pdf:gammaset"}


def data_paths() -> list[Path]:
    """Every directory LHAPDF looks in."""
    found = [Path(entry) for entry in os.environ.get("LHAPDF_DATA_PATH", "").split(os.pathsep) if entry]
    if not found:
        try:
            done = subprocess.run(["lhapdf-config", "--datadir"], capture_output=True, text=True,
                                  timeout=15)
            if done.returncode == 0 and done.stdout.strip():
                found.append(Path(done.stdout.strip()))
        except (OSError, subprocess.SubprocessError):
            pass
    return [path for path in found if path.is_dir()]


def installed_sets() -> list[str]:
    """Names of the sets that are installed, sorted."""
    found: set[str] = set()
    for directory in data_paths():
        for entry in directory.iterdir():
            if entry.is_dir() and (entry / f"{entry.name}.info").is_file():
                found.add(entry.name)
    return sorted(found)


def set_name(value: Any) -> str:
    """`"LHAPDF6:CT18NLO"` → `"CT18NLO"`; anything else (a Pythia internal set number) → ""."""
    text = str(value)
    for prefix in PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):].split("/")[0]
    return ""


def sets_in_plan(plan: Any) -> dict[str, list[str]]:
    """PDF set → the points that need it, from the settings the plan actually applies."""
    needed: dict[str, list[str]] = {}
    for point in plan.points:
        for assignment in point.settings:
            if assignment.key.lower().replace(" ", "") in PDF_KEYS:
                name = set_name(assignment.value)
                if name:
                    needed.setdefault(name, []).append(point.name)
    for group in plan.groups:                       # the base card's own choice
        for line in group.card.splitlines():
            key, _, value = line.partition("=")
            if key.strip().lower() in PDF_KEYS:
                name = set_name(value.strip())
                if name:
                    needed.setdefault(name, []).append(group.name)
    return needed


def check(plan: Any) -> dict[str, bool]:
    """Every set a plan needs, and whether it is installed."""
    present = set(installed_sets())
    return {name: name in present for name in sorted(sets_in_plan(plan))}


def install(names: list[str]) -> None:
    """Download sets with `lhapdf install` (the only command here that reaches the network)."""
    from shutil import which

    if which("lhapdf") is None:
        raise HepError("lhapdf is not on PATH", hint="load the environment first (load_hep)")
    done = subprocess.run(["lhapdf", "install", *names])
    if done.returncode != 0:
        raise HepError(f"lhapdf install failed with status {done.returncode}",
                       hint="check the set names with 'hep pdf list'")
