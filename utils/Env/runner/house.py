"""Housekeeping: `hep ls`, `hep explain`, `hep status`, `hep clean` (rank 5, V74).

docs/05_Commands_and_Tools.md §1, audit 1 F5. Nothing here runs a tool; `clean` is the only command
that deletes, and only what the runner made and no plan uses (it never deletes from results/ but a
product's `.partial` leftover, and it refuses while a job is running).
"""

from __future__ import annotations

import shutil
import textwrap
import time
import tomllib
from pathlib import Path

from . import config as configmod
from . import schema, tools
from .errors import HepError, did_you_mean
from .events import greeting, hubs
from .paths import configs_root, output_root, results_root
from .record import is_complete, complete_marker

TABLES = {"run": "run", "master": "master", "prelim": "prelim", "plot": "plot", "data": "data",
          "configuration": "configuration", "quantity": "quantity", "quantities": "quantity", "tool": "tool",
          "tools": "tool", "figure": "figure", "figures": "figure"}


# ── hep ls ─────────────────────────────────────────────────────────────────────────────────────

def config_names(project: str | None = None) -> list[str]:
    """Every configs/<Project>/<name>.toml that has a [run], as <Project>/<name>."""
    root = configs_root()
    names = []
    for path in sorted(root.glob(f"{project or '*'}/*.toml")):
        try:
            has_run = "run" in tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            has_run = True                                   # a broken file is listed, and says so
        if has_run:
            names.append(str(path.relative_to(root).with_suffix("")))
    return names


def ls(project: str | None = None) -> list[str]:
    """Each config, then each configuration: its title and description, and whether a sweep runs it."""
    names = config_names(project)
    if not names:
        raise HepError(f"no run TOML under {configs_root() / (project or '')}", hint="a config has a [run] table")
    lines = []
    for name in names:
        try:
            run = configmod.load(name)
        except HepError as error:
            lines.append(f"{name}   (does not load: {error.message})")
            continue
        swept = set(run.runs(None)) if run.sweep_runs else {run.raw.get("run", {}).get("configuration")}
        lines.append(f"{name}   run {run.name}" + ("   sweep_runs" if run.sweep_runs else ""))
        for key, configuration in run.configurations.items():
            mark = "*" if key in swept else " "
            about = configuration.description or (configuration.title if configuration.title != key else "")
            lines.append(f"  {mark} {key:16s} {about}")
    return lines


# ── hep explain ────────────────────────────────────────────────────────────────────────────────

def explain(key: str) -> list[str]:
    """A key's type, default, choices, bounds, inheritance and doc, from utils/Env/schema/run.toml.
    `plot.y_gutter`, `[plot].y_gutter`, `run.event_count`, `quantities.<q>.styles`, `tools.<tag>.shards`,
    `plot.figures.<figure>.logy`; a bare key is looked up in every table."""
    parts = [p for p in key.replace("[", "").replace("]", ".").split(".") if p]
    if not parts:
        raise HepError("explain which key?", hint="e.g. hep explain plot.y_gutter")
    found = []
    if len(parts) >= 2 and parts[0] in TABLES:
        table = TABLES[parts[0]]
        if parts[0] == "run" and len(parts) == 3:            # run.<cfg>.<key>: a configuration's
            table = "configuration"
        name = parts[-1]
        if name in schema.keys(table):
            found.append((table, name))
    else:
        found = [(table, parts[-1]) for table in schema.spec() if table != "sections" and parts[-1] in schema.keys(table)]
    if not found:
        every = sorted({k for t in schema.spec() if t != "sections" for k in schema.keys(t)})
        raise HepError(f"no key '{key}' in the schema", hint=did_you_mean(parts[-1], every) or
                       "keys are written as plot.y_gutter, run.event_count, quantities.<q>.styles")
    lines = []
    for table, name in found:
        entry = schema.keys(table)[name]
        lines.append(f"[{table}].{name}")
        lines.append(f"  type     {schema.type_name(entry['type'])}" +
                     (f" ({schema.type_name(entry['items'])} each)" if entry.get("items") else ""))
        if "choices" in entry:
            lines.append("  choices  " + ", ".join(c if isinstance(c, str) else str(c).lower() for c in entry["choices"]))
        if "min" in entry:
            lines.append(f"  min      {entry['min']}")
        if "default" in entry:
            lines.append(f"  default  {entry['default']!r}")
        if entry.get("required"):
            lines.append("  required")
        if entry.get("inherit"):
            lines.append("  a configuration inherits it from [run]")
        if entry.get("default_ok"):
            lines.append('  "default": in a child, the parent\'s value; at the top level, set nothing (the tool decides)')
        if entry.get("doc"):
            lines.append(f"  {entry['doc']}")
        if entry.get("notes"):
            lines += [""] + [f"  {line}" for line in textwrap.wrap(entry["notes"], 96)]
    return lines


# ── hep status ─────────────────────────────────────────────────────────────────────────────────

def _size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _human(size: int) -> str:
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    return ""


def running_configs() -> dict[str, list[str]]:
    """The jobs running on this machine (their watch sockets): config path → its configurations."""
    out: dict[str, list[str]] = {}
    for name in hubs():
        hello = greeting(name)
        if hello:
            out.setdefault(hello.get("config", ""), []).extend(hello.get("configurations", []))
    return out


def point_state(plan) -> str:
    """complete; stale (complete for an earlier identity: a changed setup reruns it); incomplete (begun,
    not done: failed, stopped or running); to run (never begun)."""
    if is_complete(plan):
        return "complete"
    if complete_marker(plan).exists():
        return "stale"
    if plan.out.exists() and any(plan.out.iterdir()):
        return "incomplete"
    return "to run"


def status(planned: list, running: dict[str, list[str]]) -> list[str]:
    """Per configuration, a line per point: its state, when it finished, its results' size."""
    lines = []
    for p in planned:
        stages = [*([p.pre] if p.pre else []), *p.every, *p.combined, *([p.post] if p.post else [])]
        states = [point_state(s) for s in stages]
        live = p.configuration.key in running.get(str(p.run.path), [])
        counts = ", ".join(f"{states.count(s)} {s}" for s in ("complete", "stale", "incomplete", "to run") if states.count(s))
        lines.append(f"{p.run.name} · {p.configuration.key} ({tools.run_dir(p.run, p.configuration)}): {counts}"
                     + ("   [running]" if live else ""))
        for stage, state in zip(stages, states):
            when = ""
            provenance = stage.out / "provenance.json"
            if state == "complete" and provenance.exists():
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(provenance.stat().st_mtime))
            size = _human(_size(stage.res)) if stage.res.exists() else ""
            lines.append(f"  {stage.point.name:24s} {state:10s} {when:16s} {size}")
    return lines


# ── hep clean ──────────────────────────────────────────────────────────────────────────────────

def _stage_dirs(planned) -> tuple[set[Path], set[Path]]:
    outs, ress = set(), set()
    for p in planned:
        for stage in [*([p.pre] if p.pre else []), *p.every, *p.combined, *([p.post] if p.post else [])]:
            outs.add(stage.out)
            ress.add(stage.res)
    return outs, ress


def clean_targets(planned: list, everything: bool) -> tuple[list[Path], list[Path]]:
    """What `hep clean` removes, and the results it only lists. Within each planned configuration's
    folder: point folders no plan has (output side), and `.partial` leftovers (both sides). With
    `everything` (no config named: every config was planned): also a project's run folders no
    configuration has, and prepare cache entries no plan references."""
    remove: list[Path] = []
    kept: list[Path] = []
    outs, ress = _stage_dirs(planned)
    keep_names = {"plots", "pre", "post"}
    for p in planned:
        base_out = output_root() / tools.run_dir(p.run, p.configuration)
        base_res = results_root() / tools.run_dir(p.run, p.configuration)
        for folder in sorted(base_out.iterdir()) if base_out.is_dir() else ():
            if folder.is_dir() and folder not in outs and folder.name not in keep_names:
                remove.append(folder)
        for folder in sorted(base_res.iterdir()) if base_res.is_dir() else ():
            if folder.is_dir() and folder not in ress and folder.name not in keep_names:
                kept.append(folder)
        for root in (base_out, base_res):
            if root.is_dir():
                remove.extend(sorted(f for f in root.rglob("*.partial*") if f.is_file()))
    if everything:
        used_runs: dict[str, set[Path]] = {}
        referenced: set[Path] = set()
        for p in planned:
            used_runs.setdefault(p.run.project, set()).add(output_root() / tools.run_dir(p.run, p.configuration))
            for stage in [*p.every, *p.combined, *([p.pre] if p.pre else []), *([p.post] if p.post else [])]:
                for step in stage.rendered.values():
                    if step.prepare_dir is not None:
                        referenced.add(step.prepare_dir)
        for project, used in used_runs.items():
            root = output_root() / project
            for run_folder in sorted(root.iterdir()) if root.is_dir() else ():
                if run_folder.name.startswith(".") or not run_folder.is_dir():
                    continue
                for cfg in sorted(run_folder.iterdir()):
                    if cfg.is_dir() and cfg not in used and not any(u.is_relative_to(cfg) or cfg.is_relative_to(u) for u in used):
                        remove.append(cfg)
            cache = root / ".cache"
            for tool_dir in sorted(cache.iterdir()) if cache.is_dir() else ():
                if tool_dir.name in ("checks", "datasets") or not tool_dir.is_dir():
                    continue
                for entry in sorted(tool_dir.iterdir()):
                    if entry.is_dir() and entry not in referenced:
                        remove.append(entry)
                        lock = entry.with_name(entry.name + ".lock")
                        if lock.exists():
                            remove.append(lock)
    return list(dict.fromkeys(remove)), kept


def remove(paths: list[Path]) -> int:
    """Deletes them (folders whole); returns the bytes freed."""
    freed = 0
    for path in paths:
        freed += _size(path)
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    return freed
