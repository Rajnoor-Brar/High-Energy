"""Identity, seeds, skip-unchanged and provenance (rank 3).

docs/rework_v2/02_Architecture.md §7 and §10.

* The identity of a point hashes everything that decides its result: each tool's binary, cards
  (before seeds), argv, extracted config, analyses and files, plus threads and events. It is
  computed before the seeds are written into the cards, and the seeds are then derived from it.
* Seeds: base = 1 + int(basis[:12], 16) mod (9e8 − threads); the threads use base … base+threads−1.
  The basis is the generator's own identity (the `produces_events` steps: their cards, binaries
  and replica values), so the same generator setup gives the same events in any configuration: the
  chain's point and an integrated program's (P4 S1). Without a seeded step it is the point's
  identity. Blocks are checked for overlap across the whole plan, and a clash moves up by
  `threads` (L4), so two points of one plan never share events (V9).
* A point is complete when output/…/<point>/.complete holds its identity. It is written last,
  after the count checks, so a half-written point is never skipped.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .paths import repo_root
from .tools import PointPlan, version_of

SEED_RANGE = 900_000_000


def identity(plan: PointPlan) -> str:
    parts = {
        "threads": plan.threads,
        "events": plan.events,
        "tools": [plan.rendered[tag].identity_parts for tag in sorted(plan.rendered)],
        "groups": [[s.tag for s in group] for group in plan.groups],
        "prelim": plan.prelim,
        "seeds": "generator",            # the seed rule: changing it must rerun what it decided
    }
    if plan.upstream:                    # post: it changes when any point does
        parts["upstream"] = plan.upstream
    text = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def seed_of(identity_hex: str, threads: int) -> int:
    return 1 + int(identity_hex[:12], 16) % (SEED_RANGE - threads)


def seed_basis(plan: PointPlan) -> str:
    """What the seeds follow: the identity of the event generators (`produces_events`), without their
    argv (which names this point's FIFOs) or card comments, whether they run or are only exported to
    an integrated program. A detector simulation downstream does not move the generator's seeds."""
    seeded = []
    for _, step in sorted(plan.rendered.items()):
        if not step.folder.get("tool", "produces_events"):      # the generators, not Delphes
            continue
        parts = {k: v for k, v in step.identity_parts.items() if k != "argv" and not k.startswith("_")}
        comment = step.folder.get("card", "comment", "")
        if comment and "card" in parts:                  # the header comment names the point
            parts["card"] = [line for line in parts["card"] if not line.startswith(comment)]
        seeded.append(parts)
    if not seeded:
        return plan.identity
    text = json.dumps({"threads": plan.threads, "events": plan.events, "generators": seeded}, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assign_seeds(plans: list[PointPlan]) -> None:
    """A seed block per point, disjoint across the plan (the same point keeps its seed across runs)."""
    taken: list[tuple[int, int]] = []
    for plan in sorted(plans, key=lambda p: p.identity):
        base = seed_of(seed_basis(plan), plan.threads)
        while any(base < end and start < base + plan.threads for start, end in taken):
            base = 1 + (base + plan.threads - 1) % (SEED_RANGE - plan.threads)
        taken.append((base, base + plan.threads))
        plan.seed = base


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
    """points.json (02 §6): every point's values, page, products and state, for plot and post tools."""
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
            "products": {i.name: str(i.path) for i in plan.interfaces.values() if i.kind == "product"},
            "results": str(plan.res), "output": str(plan.out),
            "identity": plan.identity, "seed": plan.seed, "complete": is_complete(plan),
        })
    return {"run": run.name, "project": run.project, "configuration": configuration.key,
            "config_file": str(run.path), "plot_points": configuration.plot_points, "points": points}

