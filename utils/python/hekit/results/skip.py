"""Deciding whether a point still needs to run (07 §1; findings 00/B3, 00/B18).

`[run].skip_existing` in the old tools meant "a file with the final name exists". That is how a run
killed halfway through got skipped for ever: the old pipeline wrote straight to the final path, so the
file was there and looked finished (00/B3). It is also why a changed card could be silently ignored —
the name had not changed, so the point was skipped with the *old* physics in place.

A point may be skipped here only when all three of these hold:

1. the **name** matches (it is the same point),
2. the **hash** matches (the same inputs produced it — 03 §5),
3. the output is **complete** (a finished `analysis.yoda`, and a summary that does not say `stopped`).

Anything else has its own answer, and the interesting one is `MISMATCH`: the same point name with a
different hash means the configuration changed under an existing result. That is not something to fix
silently — it is reported, with `--rerun` as the way to say "overwrite it".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .layout import marked

SUMMARY = "run.summary.json"
PROVENANCE = "provenance.json"
YODA = "analysis.yoda"

#: A generator running Rivet itself writes a gzipped YODA (`rivet.mode = "native"`, 04 §4). It is
#: just as finished as the plain one, so "the directory has a result" has to know about it.
COMPRESSED = ".gz"


def finished_yoda(directory: Path, yoda_name: str = YODA) -> Path | None:
    """The finished result in `directory`, whatever it is called, or None."""
    for name in (yoda_name, yoda_name + COMPRESSED):
        if (directory / name).is_file():
            return directory / name
    return None


class State(str, Enum):
    MISSING = "missing"          # nothing there yet
    PARTIAL = "partial"          # a stopped run: only analysis.partial.yoda (00/B3)
    INCOMPLETE = "incomplete"    # a directory with a spec but no result
    MISMATCH = "mismatch"        # same name, different hash — the configuration moved
    COMPLETE = "complete"        # a finished result of exactly these inputs


@dataclass
class Decision:
    state: State
    run: bool
    reason: str = ""
    hint: str = ""
    found_hash: str = ""

    @property
    def skip(self) -> bool:
        return not self.run


def same_hash(left: str, right: str) -> bool:
    """Compare identities regardless of whether they carry the `sha256:` prefix.

    The plan holds a bare digest and a written spec holds `sha256:<digest>`; comparing them raw made
    every rerun look like a name collision.
    """
    return bool(left) and bool(right) and _bare(left) == _bare(right)


def _bare(digest: str) -> str:
    return digest.split(":", 1)[1] if ":" in digest else digest


def recorded_hash(directory: Path) -> str:
    """The identity hash of whatever is in this directory, from the summary or the provenance."""
    for name in (SUMMARY, PROVENANCE):
        path = directory / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        found = payload.get("hash")
        if isinstance(found, str) and found:
            return found
    return ""


def stopped(directory: Path) -> bool:
    """True when the summary says the run was stopped before it finished."""
    path = directory / SUMMARY
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(payload.get("run", {}).get("stopped", False))


def decide(directory: Path, *, name: str = "", wanted_hash: str = "",
           yoda_name: str = YODA, rerun: bool = False) -> Decision:
    """What to do about `directory` for a point with this name and hash."""
    partial = directory / marked(yoda_name, "partial")

    if rerun:
        return Decision(State.MISSING if not directory.exists() else State.COMPLETE, True,
                        "--rerun was given")
    if not directory.is_dir():
        return Decision(State.MISSING, True, "no result yet")

    found = recorded_hash(directory)
    if wanted_hash and found and not same_hash(found, wanted_hash):
        return Decision(State.MISMATCH, False, found_hash=found,
                        reason=f"{name or directory.name} already exists with a different identity "
                               f"({found[:19]}… on disk, {wanted_hash[:19]}… wanted)",
                        hint="the configuration changed under an existing result: rerun it with "
                             "--rerun, or give the point a new [run].name")

    complete = finished_yoda(directory, yoda_name)
    if partial.is_file() and complete is None:
        return Decision(State.PARTIAL, True, reason="the last run was stopped before it finished",
                        hint=f"it left {partial.name}")
    if complete is None:
        return Decision(State.INCOMPLETE, True, reason="the directory has no finished result")
    if stopped(directory):
        # Belt and braces: a summary that says "stopped" beside a final-named YODA should not happen
        # (the sink writes one name or the other), but if it ever does, the summary is believed.
        return Decision(State.PARTIAL, True,
                        reason="the summary says the run was stopped", hint="rerunning it")
    return Decision(State.COMPLETE, False, reason="name, hash and a finished result all match",
                    found_hash=found)


def decide_all(pairs, *, yoda_name: str = YODA, rerun: bool = False) -> dict[str, Decision]:
    """`{group name: Decision}` for `[(group name, directory, hash)]`."""
    return {name: decide(directory, name=name, wanted_hash=point_hash, yoda_name=yoda_name,
                         rerun=rerun)
            for name, directory, point_hash in pairs}
