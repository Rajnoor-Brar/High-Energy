"""Rivet: finding analyses and checking their options against what they declare (00/B14).

An analysis declares its options in its `.info` file. The legacy configs declared option quantities the
analysis does not have — `zeus_validation.toml` scans `R` and `ETMIN` on `ZEUS_2012_I1116258`, which
takes no options at all — and nothing noticed until the run produced identical curves. `hep plan` now
reads the `.info` and says so before anything starts.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field as dataclass_field
from functools import lru_cache
from pathlib import Path

from ..errors import HepError, did_you_mean

#: `- NAME=#   # comment` inside the `Options:` block of a `.info` file.
OPTION = re.compile(r"^\s*-\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


@dataclass
class AnalysisInfo:
    """What the `.info` file of one analysis says."""

    name: str
    path: Path | None = None
    options: set[str] = dataclass_field(default_factory=set)
    found: bool = False


def split_analysis(entry: str) -> tuple[str, dict[str, str]]:
    """`"photo_eic:R=0.4:ETMIN=5"` → `("photo_eic", {"R": "0.4", "ETMIN": "5"})`."""
    name, *options = entry.split(":")
    chosen: dict[str, str] = {}
    for option in options:
        key, separator, value = option.partition("=")
        if not separator:
            raise HepError(f"'{option}' in analysis '{entry}' is not OPTION=VALUE",
                           hint="write photo_eic:R=0.4")
        chosen[key] = value
    return name, chosen


@lru_cache(maxsize=1)
def installed_paths() -> tuple[Path, ...]:
    """Where Rivet keeps the analyses it ships, plus anything on RIVET_ANALYSIS_PATH."""
    found: list[Path] = []
    for entry in os.environ.get("RIVET_ANALYSIS_PATH", "").split(os.pathsep):
        if entry:
            found.append(Path(entry))
    try:
        done = subprocess.run(["rivet-config", "--datadir"], capture_output=True, text=True, timeout=10)
        if done.returncode == 0 and done.stdout.strip():
            found.append(Path(done.stdout.strip()))
    except (OSError, subprocess.SubprocessError):      # rivet is optional at plan time
        pass
    return tuple(found)


def read_info(name: str, search: tuple[Path, ...]) -> AnalysisInfo:
    """The `.info` of one analysis, from the given directories then Rivet's own."""
    for directory in (*search, *installed_paths()):
        candidate = Path(directory) / f"{name}.info"
        if candidate.is_file():
            return AnalysisInfo(name=name, path=candidate, found=True,
                                options=parse_options(candidate.read_text(encoding="utf-8",
                                                                          errors="replace")))
    return AnalysisInfo(name=name)


def parse_options(text: str) -> set[str]:
    """The option names declared in an `.info` file."""
    options: set[str] = set()
    inside = False
    for line in text.splitlines():
        if line.startswith("Options:"):
            inside = True
            continue
        if inside:
            if line[:1] not in {" ", "-", "\t"} and line.strip():
                break                                   # the next top-level key ends the block
            match = OPTION.match(line)
            if match:
                options.add(match.group(1))
    return options


def check_analyses(entries: list[str], search: tuple[Path, ...], where: str) -> list[str]:
    """Check every analysis entry against its `.info`; returns warnings for what could not be checked.

    An option the analysis does not declare is an error (00/B14). An analysis whose `.info` cannot be
    found is a warning: the plugin may simply not be built yet, and `hep run` will fail loudly anyway.
    """
    warnings: list[str] = []
    checked: set[str] = set()
    for entry in entries:
        name, chosen = split_analysis(entry)
        info = read_info(name, search)
        if not info.found:
            if chosen and name not in checked:
                checked.add(name)
                warnings.append(f"cannot check the options of '{name}': no {name}.info in "
                                f"{', '.join(str(path) for path in search) or 'the search path'}")
            continue
        unknown = sorted(set(chosen) - info.options)
        if unknown:
            declared = ", ".join(sorted(info.options)) or "none"
            raise HepError(
                f"analysis '{name}' does not take {', '.join(unknown)}",
                where=where,
                hint=(did_you_mean(unknown[0], info.options) + " " if info.options else "")
                     + f"it declares: {declared} (from {info.path})")
    return warnings
