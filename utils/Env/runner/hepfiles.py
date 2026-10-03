"""Reading the framework's HEP files (rank 0): YODA text, and where Rivet keeps its analyses (V60).

One reader for what plot.py, labels.py and execute.py each read for themselves before: a YODA file's
objects (gzip read transparently), its /RAW twins, a counter's entries, and the Rivet data directories
(build/Rivet first, then `rivet-config --datadir`, asked once per process). The runner stays standard
library (02 §3.1): YODA's text is read with regular expressions, which is all these questions need.
"""

from __future__ import annotations

import functools
import gzip
import re
import subprocess
from pathlib import Path

from .paths import build_root

#: Not pages: Rivet's run counters, and its raw and temporary twins.
COUNTERS = ("/_XSEC", "/_EVTCOUNT")
TECHNICAL = ("/RAW/", "/TMP/")
_BEGIN = re.compile(r"^BEGIN YODA_(?:ESTIMATE1D|HISTO1D|SCATTER2D)_V\d+ (\S+)$", re.M)


@functools.lru_cache(maxsize=64)
def _text(path: str, mtime: int) -> str:
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def yoda_text(path: Path) -> str:
    """A YODA file's text, .yoda.gz included; read once per content (path and mtime)."""
    return _text(str(path), Path(path).stat().st_mtime_ns)


def objects(path: Path) -> list[str]:
    """The 1D objects that get pages: not /RAW or /TMP, not the counters, the nominal weight only (Sherpa
    writes a variation per extra weight, as /x[EXTRA__MEWeight])."""
    return [p for p in _BEGIN.findall(yoda_text(path))
            if not p.startswith(TECHNICAL) and p not in COUNTERS and not p.endswith("]")]


def raw_twins(path: Path) -> set[str]:
    """The /RAW Histo1D twins a file has, whose entries App_yd2rt keeps (a ratio made in finalize has none)."""
    return set(re.findall(r"^BEGIN YODA_HISTO1D_V\d+ (/RAW/\S+)$", yoda_text(path), re.M))


def entries(path: Path, obj: str) -> float | None:
    """A counter's numEntries (`/RAW/_EVTCOUNT`), from the YODA text; None when the file has none."""
    if not Path(path).exists():
        return None
    match = re.search(re.escape(obj) + r"\n.*?# sumW[^\n]*\n\S+\s+\S+\s+(\S+)", yoda_text(path), re.S)
    return float(match.group(1)) if match else None


@functools.cache
def rivet_dirs() -> tuple[Path, ...]:
    """Where analyses' .info, .plot and reference .yoda files are: build/Rivet, then Rivet's own."""
    places = [build_root() / "Rivet"]
    try:
        found = subprocess.run(["rivet-config", "--datadir"], capture_output=True, text=True, timeout=30)
        places += [Path(p) for p in found.stdout.strip().split(":") if p]
    except (OSError, subprocess.SubprocessError):
        pass
    return tuple(places)
