"""The prepare cache: integrate once, generate many (04 §1).

Sherpa integration grids, Whizard grids, Herwig `.run` files and MadGraph process directories all
cost far more than the generation that follows, and none of them depends on the seed or the event
count. A seed-replica study — ten points that differ only in their seed (03 §5) — should therefore
integrate **once**, and a study that changes the event count should not integrate at all.

That is the whole idea, and it lives or dies on what the hash covers:

* **in:** the rendered card with the seed and event-count lines removed, the tool, and the tool's
  version. A different physics point is a different grid; a new Sherpa is a new grid, because a grid
  written by one version is not guaranteed readable by another (04 §8).
* **out:** the seed, the event count, and anything about where the results go.

A cache entry is only reusable once it is **complete**, so readiness is a marker file written last —
the same rule as the event store's index (11 §1) and the YODA writer's rename (D22). A directory
without the marker is an interrupted prepare, not a usable grid.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..errors import HepError

#: Written last, so its presence means "this entry is complete".
MARKER = "prepared.json"

#: Lines a prepare hash ignores, per tool: the seed and the event count. Matched against a card line
#: that has already been stripped, case-insensitively.
VOLATILE: dict[str, tuple[str, ...]] = {
    "pythia": ("random:seed", "random:setseed", "parallelism:seeds", "main:numberofevents"),
    "sherpa": ("random_seed", "events", "event_generation_mode"),
    "whizard": ("seed", "n_events"),
    "herwig": ("set /herwig/random:seed", "run -s", "saverun"),
    "madgraph": ("iseed", "nevents"),
}

_ASSIGNMENT = re.compile(r"^\s*([A-Za-z0-9_:/ .-]+?)\s*[:=]\s*(.*)$")


#: Always ignored, whatever the tool spells them: a seed and an event count are never physics, and a
#: rendered card may carry either spelling in its header.
GENERIC = ("seed", "events", "nevents", "n_events")


def volatile_keys(tool: str) -> tuple[str, ...]:
    """The tool's own spellings, plus the generic ones.

    The union rather than the tool's list alone: the hash is taken over the *rendered* card, and an
    adapter that writes `seed = 11` while its native language says `RANDOM_SEED` would otherwise put
    the seed into the key and give every replica its own grid — the exact thing the cache exists to
    prevent.
    """
    return tuple(dict.fromkeys(VOLATILE.get(tool, ()) + GENERIC))


def stable_card(text: str, tool: str) -> str:
    """The card with its seed and event-count lines removed, and comments and blanks dropped.

    Comments go because a rendered card's header carries a timestamp and the point's own name, and
    two seeds of one physics point would otherwise hash differently for no physical reason.
    """
    volatile = volatile_keys(tool)
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in "!#":
            continue
        lowered = stripped.lower()
        match = _ASSIGNMENT.match(stripped)
        key = "".join(match.group(1).split()).lower() if match else ""
        if any(lowered.startswith(name) or key == "".join(name.split()).lower()
               for name in volatile):
            continue
        kept.append(" ".join(stripped.split()))
    return "\n".join(kept)


def prepare_hash(text: str, *, tool: str, version: str = "") -> str:
    """sha256 over what a prepare step actually depends on."""
    digest = hashlib.sha256()
    digest.update(tool.encode("utf-8"))
    digest.update(b"\0")
    digest.update(version.encode("utf-8"))
    digest.update(b"\0")
    digest.update(stable_card(text, tool).encode("utf-8"))
    return digest.hexdigest()


@dataclass
class Entry:
    """One cache entry: where it is, and whether it is usable."""

    tool: str
    hash: str
    directory: Path

    @property
    def marker(self) -> Path:
        return self.directory / MARKER

    @property
    def ready(self) -> bool:
        return self.marker.is_file()

    def meta(self) -> dict[str, Any]:
        if not self.ready:
            return {}
        try:
            return json.loads(self.marker.read_text(encoding="utf-8"))
        except ValueError:                             # pragma: no cover - a truncated marker
            return {}


def cache_root(project: str) -> Path:
    from ..env import paths

    return paths.results_root() / project / ".cache"


def entry_for(project: str, tool: str, digest: str) -> Entry:
    """`results/<project>/.cache/<tool>/<prep-hash>/` (04 §1)."""
    return Entry(tool=tool, hash=digest, directory=cache_root(project) / tool / digest)


def lookup(project: str, tool: str, text: str, *, version: str = "") -> Entry:
    return entry_for(project, tool, prepare_hash(text, tool=tool, version=version))


def mark_ready(entry: Entry, *, version: str = "", produced: Iterable[Path] = (),
               note: str = "") -> Path:
    """Write the marker, last, and only when the outputs it names really exist."""
    produced = [Path(path) for path in produced]
    missing = [str(path) for path in produced if not path.exists()]
    if missing:
        raise HepError(f"the {entry.tool} prepare step did not produce: {', '.join(missing)}",
                       hint="its log says why; the cache entry is left unmarked so it is not reused")
    entry.directory.mkdir(parents=True, exist_ok=True)
    document = {
        "tool": entry.tool,
        "hash": entry.hash,
        "version": version,
        "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": os.uname().nodename if hasattr(os, "uname") else "",
        "produces": [str(path.relative_to(entry.directory))
                     if path.is_relative_to(entry.directory) else str(path)
                     for path in produced],
        "note": note,
    }
    # Written through a temporary name, so a crash mid-write cannot leave a half marker that says
    # "ready" (D22).
    temporary = entry.marker.with_suffix(".part")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(entry.marker)
    return entry.marker


def invalidate(entry: Entry) -> None:
    """Make an entry unusable without deleting what it holds, so a failure can be inspected."""
    entry.marker.unlink(missing_ok=True)


def entries(project: str, tool: str = "") -> list[Entry]:
    """Every cache entry, for `hep clean` and for reporting."""
    root = cache_root(project)
    if not root.is_dir():
        return []
    found: list[Entry] = []
    for tool_dir in sorted(root.iterdir()):
        if not tool_dir.is_dir() or (tool and tool_dir.name != tool):
            continue
        for directory in sorted(tool_dir.iterdir()):
            if directory.is_dir():
                found.append(Entry(tool=tool_dir.name, hash=directory.name, directory=directory))
    return found
