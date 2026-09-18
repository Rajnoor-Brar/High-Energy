"""`hep store verify`: is this store still what it said it was? (11 §2).

A store is large, long-lived and copied between machines, which is exactly the population where files
get truncated, half-copied or quietly corrupted. The index records every shard's size and digest at
the moment it was closed, so checking is cheap and definite — and the point of this module is to say
*what* is wrong rather than only that something is.

Four things are checked, cheapest first, because on a 100 GB store the digest is the expensive one:

1. the index is readable and matches its schema;
2. every shard it names exists, and nothing else pretends to be a shard;
3. sizes match (a truncated copy is caught here, in milliseconds);
4. digests match (`--deep`, the definitive check).

A partial store (`stopped: true`) is *valid* — it is a run that was stopped, and its events are real.
That is reported, not failed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .index import Index, NAME, read, validate


@dataclass
class Report:
    """What verification found. `ok` means the store can be trusted as far as it was checked."""

    directory: Path
    index: Index | None = None
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    checked_bytes: int = 0
    deep: bool = False

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        if self.index is None:
            return f"{self.directory}: not a store ({'; '.join(self.problems)})"
        head = self.index.describe()
        if self.problems:
            return f"{head}\n  " + "\n  ".join(self.problems)
        detail = "digests verified" if self.deep else "sizes verified (--deep checks digests)"
        return f"{head} — {detail}" + ("".join(f"\n  note: {note}" for note in self.notes))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(directory: Path | str, *, deep: bool = False) -> Report:
    """Check a store directory against its index."""
    directory = Path(directory)
    report = Report(directory=directory, deep=deep)

    if not (directory / NAME).is_file():
        shards = sorted(path.name for path in directory.glob("events.*.hepmc*")
                        if not path.name.endswith(".part"))
        partials = sorted(path.name for path in directory.glob("*.part"))
        report.problems.append(
            f"no {NAME}: the store is unfinished"
            + (f" ({len(shards)} shard(s) present)" if shards else "")
            + (f"; {len(partials)} shard(s) still being written" if partials else ""))
        return report

    try:
        index = read(directory)
        validate(directory)
    except Exception as error:                   # noqa: BLE001 - the message is the result
        report.problems.append(str(error))
        return report
    report.index = index

    if not index.consistent:
        report.problems.append(
            f"the index says {index.events} events but its shards add up to {index.shard_events}")
    if index.stopped:
        report.notes.append("this store is partial: the run was stopped before it finished")

    named = {shard.file for shard in index.shards}
    for path in sorted(directory.glob("events.*.hepmc*")):
        if path.name.endswith(".part"):
            report.problems.append(f"{path.name} is still being written")
        elif path.name not in named:
            report.problems.append(f"{path.name} is not in the index")

    for shard in index.shards:
        path = directory / shard.file
        if not path.is_file():
            report.problems.append(f"{shard.file} is missing")
            continue
        size = path.stat().st_size
        if shard.bytes and size != shard.bytes:
            report.problems.append(
                f"{shard.file} is {size} bytes, the index says {shard.bytes}"
                + (" (truncated)" if size < shard.bytes else " (grown)"))
            continue
        report.checked_bytes += size
        if deep and shard.sha256:
            if sha256_of(path) != shard.sha256:
                report.problems.append(f"{shard.file} does not match its recorded digest")
    return report
