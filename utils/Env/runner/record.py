"""Identity, seeds, skip-unchanged and provenance (rank 3).

docs/02_Architecture.md §8 and §12.

* The identity of a point hashes everything that decides its result: each tool's binary, cards
  (before seeds), argv, extracted config, analyses and files, plus threads and events. It is
  computed before the seeds are written into the cards, and the seeds are then derived from it.
* Seeds (`seed_type`, V39): the threads of a point use base … base+threads−1, and the base is
  - "identity" (the default): lo + int(basis[:12], 16) mod (hi − lo + 1 − threads), [lo, hi] the point's seed range (V54). The basis is the
    generator's own identity (the `produces_events` steps: their cards, binaries and replica
    values), so the same generator setup gives the same events in any configuration: the chain's
    point and an integrated program's (P4 S1). Without a seeded step it is the point's identity.
    Blocks are checked for overlap across the whole plan, and a clash moves up by `threads` (L4),
    so two points of one plan never share events (V9);
  - "manual": exactly the value of a quantity targeting <tool>/seed, else `manual_seed`. Points
    with one generator setup whose blocks overlap without being the same are refused: they would
    repeat some of each other's events;
  - "random": drawn from the OS when the point runs (disjoint as above); a complete point keeps the
    seed its provenance.json records.
* A point is complete when output/…/<point>/.complete holds its identity. It is written last,
  after the count checks, so a half-written point is never skipped.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .errors import HepError
from .paths import repo_root
from .tools import DEFAULT_SEED_RANGE, PointPlan, version_of



def identity(plan: PointPlan) -> str:
    parts = {
        "threads": plan.threads,
        "events": plan.events,
        "tools": [plan.rendered[tag].identity_parts for tag in sorted(plan.rendered)],
        "groups": [[s.tag for s in group] for group in plan.groups],
        "prelim": plan.prelim,
        "seeds": seed_rule(plan),        # the seed rule: changing it must rerun what it decided
    }
    if plan.upstream:                    # post: it changes when any point does
        parts["upstream"] = plan.upstream
    text = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def seed_rule(plan: PointPlan):
    """What the identity says about the seeds: "generator" (the default: the seeds follow from the
    rest, so this is what every identity said before V39), ["manual", seed] or "random"."""
    if plan.seed_type == "manual":
        return ["manual", manual_seed_of(plan)]
    return "random" if plan.seed_type == "random" else "generator"


def manual_seed_of(plan: PointPlan) -> int:
    """seed_type = "manual": the value of the quantity targeting <tool>/seed, else manual_seed."""
    values = list(dict.fromkeys(v for step in plan.rendered.values() for v in step.identity_parts.get("replica", [])))
    where = f"point {plan.point.name}"
    if len(values) > 1:
        raise HepError(f"two seed quantities give this point the seeds {values}", where=where,
                       hint="a point has one seed: target <tool>/seed from one quantity")
    seed = values[0] if values else plan.manual_seed
    if seed is None:
        raise HepError("seed_type is manual but this point has no seed", where=where,
                       hint="set manual_seed in [run] or [run.<cfg>], or sweep a quantity targeting <tool>/seed")
    lo, hi = plan.seed_range
    if isinstance(seed, bool) or not isinstance(seed, int) or not lo <= seed <= hi - plan.threads:
        raise HepError(f"the seed {seed!r} is not an integer from {lo:,} to {hi - plan.threads:,}", where=where,
                       hint=f"with threads = {plan.threads} the point uses seed … seed + {plan.threads - 1}; the range is "
                            "its generators' [card] seed_range")
    return seed


def seed_of(identity_hex: str, threads: int, seed_range: tuple[int, int] = DEFAULT_SEED_RANGE) -> int:
    lo, hi = seed_range
    return lo + int(identity_hex[:12], 16) % (hi - lo + 1 - threads)


def seed_basis(plan: PointPlan, replica: bool = True) -> str:
    """What the seeds follow: the identity of the event generators (`produces_events`), without their
    argv (which names this point's FIFOs) or card comments, whether they run or are only exported to
    an integrated program. A detector simulation downstream does not move the generator's seeds.
    Without `replica`, the generator setup alone (what a manual seed is checked against)."""
    seeded = []
    for _, step in sorted(plan.rendered.items()):
        if not step.folder.get("tool", "produces_events"):      # the generators, not Delphes
            continue
        parts = {k: v for k, v in step.identity_parts.items()
                 if k != "argv" and not k.startswith("_") and (replica or k != "replica")}
        comment = step.folder.get("card", "comment", "")
        if comment and "card" in parts:                  # the header comment names the point
            parts["card"] = [line for line in parts["card"] if not line.startswith(comment)]
        seeded.append(parts)
    if not seeded:
        return plan.identity
    text = json.dumps({"threads": plan.threads, "events": plan.events, "generators": seeded}, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assign_seeds(plans: list[PointPlan], rerun: frozenset[str] = frozenset()) -> None:
    """A seed block per point (V39): given ("manual"), kept from a complete point's provenance or
    drawn ("random"; `rerun` names the points about to run again, which draw anew), else from the
    generator's identity; the last two disjoint across the plan."""
    taken: list[tuple[int, int]] = []

    def clear(base: int, threads: int) -> bool:
        return not any(base < end and start < base + threads for start, end in taken)

    by_setup: dict[str, list[PointPlan]] = {}
    for plan in [p for p in plans if p.seed_type == "manual"]:
        plan.seed = manual_seed_of(plan)
        for other in by_setup.setdefault(seed_basis(plan, replica=False), []):
            if other.seed != plan.seed and plan.seed < other.seed + other.threads and other.seed < plan.seed + plan.threads:
                raise HepError(f"points {other.point.name} (seed {other.seed}) and {plan.point.name} (seed {plan.seed}) "
                               f"have one generator setup and overlapping seed blocks at threads = {plan.threads}",
                               where=f"point {plan.point.name}",
                               hint=f"they would repeat some of each other's events: space the seeds by ≥ {plan.threads}")
        by_setup[seed_basis(plan, replica=False)].append(plan)
    for plan in [p for p in plans if p.seed_type == "random"]:
        plan.seed, plan.seed_kept = (0 if plan.point.name in rerun else _recorded_seed(plan)), True
        if plan.seed:
            taken.append((plan.seed, plan.seed + plan.threads))
    for plan in [p for p in plans if p.seed_type == "random" and not p.seed]:
        plan.seed_kept = False
        lo, hi = plan.seed_range
        while not clear(base := lo + secrets.randbelow(hi - lo + 1 - plan.threads), plan.threads):
            pass
        taken.append((base, base + plan.threads))
        plan.seed = base
    for plan in sorted([p for p in plans if p.seed_type == "identity"], key=lambda p: p.identity):
        lo, hi = plan.seed_range
        base = seed_of(seed_basis(plan), plan.threads, plan.seed_range)
        while not clear(base, plan.threads):
            base = lo + (base - lo + plan.threads) % (hi - lo + 1 - plan.threads)
        taken.append((base, base + plan.threads))
        plan.seed = base


def _recorded_seed(plan: PointPlan) -> int:
    """A complete point's seed, from its provenance.json (0 when it is not complete, or unreadable)."""
    if not is_complete(plan):
        return 0
    try:
        return int(json.loads((plan.out / "provenance.json").read_text(encoding="utf-8"))["seed"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def complete_marker(plan: PointPlan) -> Path:
    return plan.out / ".complete"             # technical: beside the cards and logs, not the products


def is_complete(plan: PointPlan) -> bool:
    marker = complete_marker(plan)
    return marker.is_file() and marker.read_text(encoding="utf-8").strip() == plan.identity


def git_state() -> dict:
    def git(*args) -> str:
        try:
            return subprocess.run(["git", *args], cwd=repo_root(), capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    return {"revision": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain", "--untracked-files=no"))}


def provenance(plan: PointPlan, run, configuration, started: str, finished: str, results: dict) -> dict:
    tools = []
    for tag, step in plan.rendered.items():
        entry = {"tag": tag, "tool": step.tool.tool, "exe": str(step.exe), "version": version_of(step.folder),
                 "argv": step.argv, "ran": step.group >= 0, "result": results.get(tag, {})}
        if step.exe.is_file():
            entry["exe_sha256"] = step.identity_parts.get("exe_sha256", "")
        if step.card_combined:
            entry["card"] = str(step.card_combined)
            entry["card_sha256"] = hashlib.sha256(plan.writes.get(step.card_combined, "").encode("utf-8")).hexdigest()
        if step.config_path:
            entry["config"] = str(step.config_path)
        tools.append(entry)
    return {
        "point": plan.point.name,
        "run": run.name, "project": run.project, "configuration": configuration.key,
        "config_file": str(run.path),
        "values": {name: {"index": index, "tag": _tag(run, name, index), "value": run.quantities[name].values[index]}
                   for name, index in plan.values.items()},
        "identity": plan.identity, "seed": plan.seed, "threads": plan.threads, "events": plan.events,
        "tools": tools,
        "host": socket.gethostname(), "platform": platform.platform(), "user": os.environ.get("USER", ""),
        "git": git_state(), "started": started, "finished": finished,
    }


def _tag(run, name: str, index: int) -> str:
    from .sweep import tag_of
    return tag_of(run.quantities[name], index)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".tmp")
    partial.write_text(text, encoding="utf-8")
    partial.replace(path)


def points_manifest(plans: list[PointPlan], run, configuration) -> dict:
    """points.json (02 §7): every point's values, page, products and state, for plot and post tools."""
    from .sweep import label_of, tag_of
    page_names = [name for entry in configuration.sweeps for name in (entry if isinstance(entry, list) else [entry])
                  if (set(entry) if isinstance(entry, list) else {entry}) & set(configuration.plot_points)]
    points = []
    for plan in plans:
        quantity = run.quantities
        points.append({
            "name": plan.point.name, "index": plan.point.index,
            "values": {name: {"tag": tag_of(quantity[name], i), "label": label_of(quantity[name], i),
                              "value": quantity[name].values[i], "swept": name in plan.point.choice}
                       for name, i in plan.values.items()},
            "page": [tag_of(quantity[name], plan.point.choice[name]) for name in page_names],
            "products": {i.name: str(i.path) for i in plan.interfaces.values() if i.kind == "product" and not i.shard},
            "results": str(plan.res), "output": str(plan.out),
            "identity": plan.identity, "seed": plan.seed, "complete": is_complete(plan),
        })
    return {"run": run.name, "project": run.project, "configuration": configuration.key,
            "config_file": str(run.path), "plot_points": configuration.plot_points, "points": points}

