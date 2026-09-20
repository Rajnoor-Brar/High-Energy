"""What `hep clean` may remove, and what it may never touch (07 §6).

The rule that shapes this command is the second column of 07 §6's table, not the first:

> **Never touched automatically:** YODA files, `fits.json` and provenance.

Those are the things that cost hours to produce and that nobody can reconstruct from what is left.
Everything this command offers to remove is either **regenerable** (plots, prepare caches), **large
and expendable** (event stores, which the index keeps a tombstone for), or **already worthless** (a
point directory with no result in it). So the categories are named individually and none of them is
on by default: `hep clean` with no flags reports and removes nothing, because a cleaner whose
default is to delete is one you run once by accident.

**`--dry-run` is a size report**, and it is the reason to run this at all — "what is taking the
space" is the question, and "delete it" is the follow-up. It prints the same categories with their
sizes and touches nothing.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ..errors import HepError


@dataclass
class Item:
    """One thing that could be removed."""

    path: Path
    bytes: int = 0
    note: str = ""


@dataclass
class Group:
    """One `--flag`'s worth of removable things."""

    kind: str
    items: list[Item] = field(default_factory=list)

    @property
    def bytes(self) -> int:
        return sum(item.bytes for item in self.items)

    def __bool__(self) -> bool:
        return bool(self.items)


#: The categories, in the order the report prints them. `keep` says what stays behind, which is the
#: half of this command that matters.
KINDS = {
    "cache": "prepare caches (regenerated on the next run)",
    "events": "HepMC event stores (the index and provenance are kept as a tombstone)",
    "plots": "study plots (regenerable from the YODA)",
    "orphans": "point directories with no result in them",
}


def size_of(path: Path) -> int:
    """Bytes under a path. Symlinks are counted as themselves, never followed."""
    if path.is_symlink():
        return path.lstat().st_size
    if path.is_file():
        return path.stat().st_size
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_symlink():
                total += entry.lstat().st_size
            elif entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def human(count: int) -> str:
    """A size a person can read. Binary units, because that is what `du` shows."""
    size = float(count)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TiB"


def older_than(path: Path, days: float) -> bool:
    """Whether everything in here was last modified more than `days` ago.

    The *newest* file decides, not the directory's own mtime: a directory keeps the mtime of its
    last entry change, which a read can touch on some filesystems, and the question being asked is
    "has anything happened in here recently".
    """
    if days <= 0:
        return True
    cutoff = time.time() - days * 86400.0
    newest = 0.0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                newest = max(newest, entry.stat().st_mtime)
        except OSError:
            continue
    return newest > 0 and newest < cutoff


def caches(layout) -> Group:
    """Prepare caches: `results/<project>/.cache/<tool>/<hash>/` (P7-S01)."""
    from ..adapters import cache as cache_module

    group = Group("cache")
    try:
        found = cache_module.entries(layout.project)
    except Exception:
        found = []
    for entry in found:
        directory = Path(entry.directory)
        if directory.is_dir():
            group.items.append(Item(directory, size_of(directory), entry.tool))
    return group


def stores(layout, *, days: float = 0.0) -> Group:
    """`events/` directories under each point, older than `days`.

    The events go; `events.index.json` stays. A store that has been removed should still be able to
    say what it held and which run wrote it — a tombstone is what makes "where did the events go"
    answerable a month later (11 §1).
    """
    group = Group("events")
    for point in _points(layout):
        directory = point / "events"
        if not directory.is_dir() or not older_than(directory, days):
            continue
        shards = [entry for entry in directory.iterdir()
                  if entry.is_file() and entry.name != "events.index.json"]
        if not shards:
            continue
        group.items.append(Item(directory, sum(size_of(shard) for shard in shards),
                                f"{len(shards)} shards, index kept"))
    return group


def plots(layout) -> Group:
    """`studies/<study>/plots/` — regenerable with `hep plot`."""
    group = Group("plots")
    if not layout.studies.is_dir():
        return group
    for study in sorted(layout.studies.iterdir()):
        directory = study / "plots"
        if directory.is_dir():
            group.items.append(Item(directory, size_of(directory), study.name))
    return group


def orphans(layout) -> Group:
    """Point directories with no result in them (`Layout.orphans`)."""
    group = Group("orphans")
    for directory in layout.orphans():
        group.items.append(Item(directory, size_of(directory), "no result"))
    return group


def _points(layout) -> Iterable[Path]:
    if not layout.points.is_dir():
        return []
    return [entry for entry in sorted(layout.points.iterdir()) if entry.is_dir()]


def survey(layout, *, kinds: Iterable[str], days: float = 0.0) -> list[Group]:
    """What could be removed, in report order. Reads only."""
    wanted = [kind for kind in KINDS if kind in set(kinds)]
    made = []
    for kind in wanted:
        if kind == "cache":
            made.append(caches(layout))
        elif kind == "events":
            made.append(stores(layout, days=days))
        elif kind == "plots":
            made.append(plots(layout))
        elif kind == "orphans":
            made.append(orphans(layout))
    return made


def remove(group: Group) -> tuple[int, int]:
    """Remove a group's items. Returns (removed, bytes freed).

    An `events` group keeps the index: the directory is emptied of shards rather than deleted, so
    the tombstone survives.
    """
    removed = 0
    freed = 0
    for item in group.items:
        try:
            if group.kind == "events":
                for entry in item.path.iterdir():
                    if entry.is_file() and entry.name != "events.index.json":
                        freed += size_of(entry)
                        entry.unlink()
                        removed += 1
            elif item.path.is_dir():
                freed += item.bytes
                shutil.rmtree(item.path)
                removed += 1
            elif item.path.exists():
                freed += item.bytes
                item.path.unlink()
                removed += 1
        except OSError as error:
            raise HepError(f"could not remove {item.path}: {error}") from None
    return removed, freed


def largest(layout, *, limit: int = 10) -> list[Item]:
    """The biggest directories under this project, whatever category they fall in.

    The report's last section, and the one that answers the question actually being asked. It
    includes things `hep clean` will never remove, because "your YODA files are the 40 GB" is a
    useful answer even though the tool will not act on it.
    """
    found: list[Item] = []
    for directory in (layout.points, layout.studies):
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if entry.is_dir():
                found.append(Item(entry, size_of(entry), directory.name))
    found.sort(key=lambda item: item.bytes, reverse=True)
    return found[:limit]
