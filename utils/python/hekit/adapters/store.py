"""Replaying a store: resolving one, and refusing what a replay cannot do (11 §4–5).

A replay is a point like any other — it has a name, a hash and a directory — but it differs from a
generation in one way the planner has to enforce:

**a replay cannot change the events.** Beam energies, PDF sets, `pTHatMin`: all of those decide what
was generated, and the events already exist. Only *analysis-side* quantities (an analysis option, a
different analysis) mean anything on a store, so anything else is an error with a hint rather than a
run that silently ignores half its own configuration.

The other half is identity: a replay's hash is `sha256(store hash + analysis configuration)` (11 §4),
so replaying the same store with the same analyses is skipped like any other finished point, and
replaying it with a new analysis is a new point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import HepError

#: Quantity types that change the *events*, and so cannot apply to a store (03 §3).
GENERATION_TYPES = {"setting", "beams", "energies", "seed", "card", "generator", "events"}

#: The ones that only change what is done with them.
ANALYSIS_TYPES = {"analysis", "option"}


def resolve(reference: str, *, project: str = "") -> Path:
    """The store directory a `[generator].input` names.

    Accepts a path, a point name (looked up in this project's results), or `sha256:…` (matched
    against the indexes of the stores that are there).
    """
    from ..env import paths
    from ..store import index as index_module

    if not reference:
        raise HepError("[generator].input is empty, but the generator is a store",
                       hint='name a point, a path, or "sha256:…"')

    candidate = Path(reference).expanduser()
    for path in (candidate, candidate / "events"):
        if (path / index_module.NAME).is_file():
            return path

    # This project first, then the whole results tree: a point name is unique across it (03 §5),
    # and a replay config often does not live in the project directory whose events it reads.
    root = paths.results_root()
    everything = [entry for entry in sorted(root.iterdir()) if entry.is_dir()] if root.is_dir() else []
    roots = ([root / project] if project and (root / project).is_dir() else []) + everything
    found: list[Path] = []
    for base in roots:
        for store in index_module.find_stores(base):
            if store not in found:
                found.append(store)

    if reference.startswith("sha256:"):
        matches = [store for store in found
                   if _hash_of(store) in {reference, reference.removeprefix("sha256:")}]
        if not matches:
            raise HepError(f"no event store with hash {reference[:19]}…",
                           hint="`hep store ls` lists the stores that are there")
        return matches[0]

    named = [store for store in found if store.parent.name == reference]
    if named:
        return named[0]
    raise HepError(f"no event store for '{reference}'",
                   hint="give a point name, a path to an events/ directory, or \"sha256:…\"; "
                        "`hep store ls` lists them")


def _hash_of(store: Path) -> str:
    from ..store import index as index_module

    try:
        return index_module.read(store).hash
    except HepError:                             # pragma: no cover - an unreadable store
        return ""


def store_document(directory: Path, *, queue: int = 0) -> dict[str, Any]:
    """`[source.store]` for the spec: what the index says, so `hep-run` needs no JSON parser.

    The index stays the source of truth (11 §4) — this is `hep` reading it on `hep-run`'s behalf,
    which is the same split as everywhere else: judgement in Python, the event loop in C++.
    """
    from ..store import index as index_module

    index = index_module.read(directory)
    document: dict[str, Any] = {
        "dir": str(directory),
        "compression": index.compression,
        "shards": [shard.file for shard in index.shards],
        "workers": [shard.worker for shard in index.shards],
        "events": index.events,
        "xsec_pb": index.xsec_pb,
        "xsec_err_pb": index.xsec_err_pb,
        "beam_ids": list(index.beam_ids),
        "beam_energies": list(index.beam_energies),
        "weights": list(index.weights),
        "stopped": index.stopped,
    }
    if queue:
        document["queue"] = queue
    return document


def check_quantities(config: Any, selection: Any) -> None:
    """Refuse a sweep that would change events a store already holds."""
    offenders: list[tuple[str, str]] = []
    for name in _quantity_names(config, selection):
        quantity = config.quantities.get(name)
        kind = getattr(quantity, "type", "") if quantity is not None else ""
        if kind in GENERATION_TYPES:
            offenders.append((name, kind))
    if not offenders:
        return
    listed = ", ".join(f"{name} ({kind})" for name, kind in offenders)
    raise HepError(
        f"a store replay cannot scan {listed}",
        hint="those choose what is generated, and the events already exist. A replay may scan "
             f"analysis-side quantities ({', '.join(sorted(ANALYSIS_TYPES))}); to vary the physics, "
             "generate with [generator].tool = \"pythia\"")


def _quantity_names(config: Any, selection: Any) -> list[str]:
    """Every quantity a selection would scan or pin, flattened."""
    found: list[str] = []
    for group in getattr(selection, "across", []) or []:
        if isinstance(group, (list, tuple)):
            found.extend(str(entry) for entry in group)
        else:
            found.append(str(group))
    overlay = getattr(selection, "overlay", "")
    if overlay:
        found.append(str(overlay))
    found.extend(str(name) for name in (getattr(selection, "pins", {}) or {}))
    return [name for name in found if name]


def replay_origin(directory: Path) -> str:
    """A one-line description of what is being replayed, for provenance and the terminal."""
    from ..store import index as index_module

    try:
        index = index_module.read(directory)
    except HepError:                             # pragma: no cover
        return f"store {directory}"
    state = ", partial" if index.stopped else ""
    return (f"store {directory} ({index.events} events, {len(index.shards)} "
            f"{index.compression} shards{state})")
