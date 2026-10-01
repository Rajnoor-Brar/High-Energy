"""The run TOML: load it, check it strictly, and hand back a typed model (rank 1).

docs/04_Config_Reference.md. The checks here are the ones that need only the file (rules C1, C2,
C3, C5 and the shape of every key). The ones that need the tool folders, the master TOML or the
point are in `quantities`, `tools` and `execute`.

Every error names the file and the key (`where`) and says what to do (`hint`).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import HepError, did_you_mean
from .paths import config_file, repo_root

TOP_LEVEL = ("master", "run", "prelim", "static", "tools", "quantities", "plot")

# key → accepted Python types. A tuple of types means any of them.
RUN_KEYS = {"serial": int, "name": str, "project": str, "configuration": str, "event_count": int,
            "threads": int, "parallelism": int, "description": str, "sweep_runs": bool, "seed_type": str,
            "manual_seed": int}
CONFIGURATION_KEYS = {"serial": int, "name": str, "title": str, "description": str, "event_count": int,
                      "threads": int, "parallelism": int, "swept": bool, "seed_type": str, "manual_seed": int,
                      "sweeps": list, "plot_points": list, "combine": list, "tools": list, "pre": list, "post": list,
                      "static": dict, "prelim": dict}
#: How a point's seeds are chosen (V39, 02 §8): from the generator's identity (the default), given
#: (`manual_seed`, or a quantity targeting <tool>/seed), or drawn afresh when the point runs.
SEED_TYPES = ("identity", "manual", "random")
PRELIM_KEYS = {"fifo": list, "files": list, "commands": list}
MASTER_KEYS = {"master_toml": str}
QUANTITY_KEYS = {"values": list, "tags": list, "labels": list, "key": (str, dict), "target": (str, list),
                 "format": str, "description": str, "exclude": list}
#: Keys any tool table may carry; the rest are tool-specific, checked in `tools` against the tool
#: folder's [options], or are standard-configuration requests (<tool>_<export>, 04 §9.4).
TOOL_COMMON = {"tool": str, "baseconfig": (str, list), "input": (str, list), "output_file": (str, list),
               "timeout": (int, float), "stall_after": (int, float), "status": str, "executable": str,
               "arguments": list, "consumes": list, "config": dict, "streamable": bool,
               "consumes_events": bool, "shards": int}
PLOT_KEYS = {"backend": (str, list), "formats": list, "objects": list, "ratio": bool, "y_gutter": (int, float, str),
             "x_gutter": (int, float, str), "logy": bool, "logx": bool, "auto_range": bool, "void_empty": bool, "use_data": bool,
             "min_entries": int, "range_pad": int, "root_style": str, "data": dict, "style": dict, "object": dict}


@dataclass
class Tool:
    tag: str
    tool: str
    baseconfig: list[str] = field(default_factory=list)
    input: list[str] = field(default_factory=list)
    output_file: list[str] = field(default_factory=list)
    timeout: float = 0.0
    stall_after: float = 0.0
    status: str = ""
    executable: str = ""
    arguments: list = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    config: dict | None = None
    streamable: bool | None = None
    consumes_events: bool | None = None
    shards: int = 1                                  # K > 1: K processes on a share of the events each (V31)
    extra: dict = field(default_factory=dict)       # tool-specific keys and export requests


@dataclass
class Quantity:
    name: str
    values: list
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    key: str | dict | None = None
    target: list[str] = field(default_factory=list)
    format: str = ""
    description: str = ""
    exclude: list[int] = field(default_factory=list)   # 1-based value indices a sweep leaves out (V42)


@dataclass
class Configuration:
    key: str
    name: str
    serial: int | None
    description: str
    event_count: int
    threads: int
    sweeps: list                                    # entries: str | list[str]
    plot_points: list[str]
    tools: list[list[str]]                          # groups
    post: list[list[str]]
    static: dict
    prelim: dict
    pre: list[list[str]] = field(default_factory=list)   # tools run once before every point
    combine: list[str] = field(default_factory=list)    # swept quantities whose points are merged into one (V35)
    parallelism: int = 1                                # points run at once (V36); never in an identity
    swept: bool = True                                  # run by [run].sweep_runs (V38)
    title: str = ""                                     # the `run NN - <title> -` header of a sweep
    seed_type: str = "identity"                         # SEED_TYPES (V39)
    manual_seed: int | None = None                      # seed_type = "manual": every point's seed


@dataclass
class RunConfig:
    path: Path
    project: str
    name: str
    serial: int | None
    default_configuration: str | None                  # None only under sweep_runs
    configurations: dict[str, Configuration]
    prelim: dict
    static: dict
    tools: dict[str, Tool]
    quantities: dict[str, Quantity]
    plot: dict
    master_toml: str | None
    raw: dict
    sweep_runs: bool = False                            # `hep run` executes every swept configuration (V38)

    def configuration(self, name: str | None) -> Configuration:
        wanted = name or self.default_configuration
        if wanted is None:
            raise HepError("[run] runs every configuration (sweep_runs) and names none", where=f"{self.path}: [run]",
                           hint=f"name one: configurations {', '.join(self.configurations)}")
        if wanted not in self.configurations:
            raise HepError(f"no configuration '{wanted}'", where=f"{self.path}: [run]",
                           hint=did_you_mean(wanted, self.configurations)
                           or f"configurations: {', '.join(self.configurations) or '(none)'}")
        return self.configurations[wanted]

    def runs(self, name: str | None) -> list[str]:
        """The configurations `hep run` executes, in order (V38): the one named on the command line,
        even under sweep_runs; else, under [run].sweep_runs, every configuration not `swept = false`, in the
        order of the file; else [run].configuration."""
        if name:
            return [self.configuration(name).key]
        if self.sweep_runs:
            return [key for key, c in self.configurations.items() if c.swept]
        return [self.configuration(None).key]


# ── checking ───────────────────────────────────────────────────────────────────────────────────

def _type_name(types) -> str:
    types = types if isinstance(types, tuple) else (types,)
    names = {int: "an integer", float: "a number", str: "a string", list: "a list", dict: "a table",
             bool: "true/false"}
    return " or ".join(names.get(t, t.__name__) for t in types)


def _check(table: dict, spec: dict, where: str, *, allow_tables: bool = False, extra_ok: bool = False) -> dict:
    """Unknown keys are errors (C1); known keys must have the right type. Returns the extras."""
    extras = {}
    for key, value in table.items():
        types = spec.get(key)
        if allow_tables and isinstance(value, dict) and dict not in (types if isinstance(types, tuple) else (types,)):
            continue                             # a configuration, even one named like a key ([run.threads])
        if key in spec:
            if isinstance(value, bool) and bool not in (types if isinstance(types, tuple) else (types,)):
                raise HepError(f"'{key}' must be {_type_name(types)}, not true/false", where=f"{where}.{key}")
            if not isinstance(value, types):
                raise HepError(f"'{key}' must be {_type_name(types)}", where=f"{where}.{key}",
                               hint=f"got {value!r}")
        elif extra_ok:
            extras[key] = value
        else:
            raise HepError(f"unknown key '{key}'", where=where,
                           hint=did_you_mean(key, spec) or f"known keys: {', '.join(spec)}")
    return extras


def _seed_type(value: str, where: str) -> str:
    if value not in SEED_TYPES:
        raise HepError(f"seed_type is '{value}'", where=where, hint=f"one of {', '.join(SEED_TYPES)}")
    return value


def _manual_seed(value: int | None, where: str) -> int | None:
    if value is not None and not 1 <= value < 900_000_000:          # Pythia's range (record.SEED_RANGE)
        raise HepError(f"manual_seed {value} is out of range", where=where, hint="1 to 899,999,999")
    return value


def _as_list(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _groups(entries: list, where: str, tools: dict) -> list[list[str]]:
    """`tools = [A, [B, C], D]` → [[A], [B, C], [D]] (04 §5.4, C5)."""
    groups = []
    for entry in entries:
        members = entry if isinstance(entry, list) else [entry]
        if not members:
            raise HepError("an empty group in the tool list", where=where)
        for member in members:
            if isinstance(member, list):
                raise HepError("tool groups nest one level only", where=where,
                               hint="write [A, [B, C], D]: an inner list is one group that runs together")
            if not isinstance(member, str):
                raise HepError(f"a tool entry must be a tool tag, got {member!r}", where=where)
            if member.startswith("@"):
                continue                               # a tool chosen by a quantity (V19): resolved per point
            if member not in tools:
                raise HepError(f"'{member}' is not a [tools.<tag>] table", where=where,
                               hint=did_you_mean(member, tools) or "define [tools." + member + "]")
        groups.append(list(members))
    return groups


def _sweeps(entries: list, where: str, quantities: dict) -> list:
    """C3: every entry names a declared quantity; an inner list is one entangled group."""
    seen: set[str] = set()
    out = []
    for entry in entries:
        members = entry if isinstance(entry, list) else [entry]
        for name in members:
            if not isinstance(name, str):
                raise HepError(f"sweeps entries are quantity names, got {name!r}", where=where)
            if name not in quantities:
                raise HepError(f"sweeps names '{name}', which is not a [quantities.<q>] table", where=where,
                               hint=did_you_mean(name, quantities) or f"declare [quantities.{name}]")
            if name in seen:
                raise HepError(f"'{name}' is swept twice", where=where)
            seen.add(name)
        if isinstance(entry, list):
            counts = {name: len(quantities[name].values) for name in members}
            if len(set(counts.values())) > 1:
                raise HepError("entangled quantities need equal value counts", where=where,
                               hint=", ".join(f"{n}: {c}" for n, c in counts.items()))
        out.append(list(members) if isinstance(entry, list) else entry)
    return out


def _parallelism(value: int, where: str) -> int:
    if value < 1:
        raise HepError("parallelism must be at least 1 (the points run at once)", where=where)
    return value


def _resolved_threads(value: int, where: str) -> int:
    if value < 0:
        raise HepError("threads must be ≥ 0 (0 = every core)", where=where)
    return value or (os.cpu_count() or 1)             # resolved here, never passed on as 0


# ── --set ──────────────────────────────────────────────────────────────────────────────────────

def _literal(text: str):
    try:
        return tomllib.loads(f"v = {text}")["v"]
    except tomllib.TOMLDecodeError:
        return text


def apply_sets(raw: dict, sets: list[str]) -> None:
    """`--set static.energies=18x275`, `--set run.pdf.threads=4`: override one value (dotted keys)."""
    for item in sets:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise HepError(f"--set expects KEY=VALUE, got '{item}'")
        parts = key.strip().split(".")
        table = raw
        for part in parts[:-1]:
            table = table.setdefault(part, {})
            if not isinstance(table, dict):
                raise HepError(f"--set {key}: '{part}' is not a table")
        table[parts[-1]] = _literal(value.strip())


# ── loading ────────────────────────────────────────────────────────────────────────────────────

def load(name: str, *, sets: list[str] = ()) -> RunConfig:
    path = config_file(name)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        escape = "escape" in str(error).lower() or "'\\'" in str(error)
        raise HepError(f"not valid TOML: {error}", where=str(path),
                       hint="in a \"…\" string a backslash starts a TOML escape: write the label in single quotes, "
                            "'PDF4LHC21\\_40', or double the backslash, \"PDF4LHC21\\\\_40\"" if escape else None)
    apply_sets(raw, list(sets))
    return parse(raw, path)


def parse(raw: dict, path: Path) -> RunConfig:
    where = str(path)
    for key in raw:
        if key not in TOP_LEVEL:
            raise HepError(f"unknown section [{key}]", where=where,
                           hint=did_you_mean(key, TOP_LEVEL) or f"sections: {', '.join(TOP_LEVEL)}")

    master = raw.get("master", {})
    _check(master, MASTER_KEYS, f"{where}: [master]")

    run = raw.get("run")
    if not isinstance(run, dict):
        raise HepError("missing [run]", where=where, hint="every run TOML has [run] name, project, configuration")
    _check(run, RUN_KEYS, f"{where}: [run]", allow_tables=True)
    sweep_on = run.get("sweep_runs") is True
    for required in ("name", "project") + (() if sweep_on else ("configuration",)):
        if required not in run:
            raise HepError(f"[run] needs '{required}'", where=f"{where}: [run]")
    project = run["project"]
    # A config under configs/<X>/ belongs to project X; one given as ./path elsewhere (tests) need not.
    if path.parent.parent == repo_root() / "configs" and path.parent.name != project:
        raise HepError(f"[run].project is '{project}' but the file is in configs/{path.parent.name}/",
                       where=f"{where}: [run].project", hint="they must match")

    prelim = raw.get("prelim", {})
    _check(prelim, PRELIM_KEYS, f"{where}: [prelim]")

    quantities: dict[str, Quantity] = {}
    for name, table in raw.get("quantities", {}).items():
        at = f"{where}: [quantities.{name}]"
        if not isinstance(table, dict):
            raise HepError("a quantity is a table", where=at)
        _check(table, QUANTITY_KEYS, at)
        if "values" not in table or not table["values"]:
            raise HepError("a quantity needs values", where=at)
        values = table["values"]
        for listed in ("tags", "labels"):
            if listed in table and len(table[listed]) != len(values):
                raise HepError(f"'{listed}' must have one entry per value ({len(values)})", where=f"{at}.{listed}")
        exclude = table.get("exclude", [])
        for index in exclude:
            if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= len(values):
                raise HepError(f"exclude names {index!r}, which is not a value's place", where=f"{at}.exclude",
                               hint=f"1-based: 1 to {len(values)}, as static \"#2\" and --points 2 count")
        if len(set(exclude)) == len(values):
            raise HepError("exclude leaves no value to sweep", where=f"{at}.exclude")
        quantities[name] = Quantity(name=name, values=values, tags=[str(t) for t in table.get("tags", [])],
                                    labels=[str(l) for l in table.get("labels", [])], key=table.get("key"),
                                    target=_as_list(table.get("target")), format=table.get("format", ""),
                                    description=table.get("description", ""), exclude=sorted(set(exclude)))

    tools: dict[str, Tool] = {}
    for tag, table in raw.get("tools", {}).items():
        at = f"{where}: [tools.{tag}]"
        if not isinstance(table, dict):
            raise HepError("a tool is a table", where=at)
        extras = _check(table, TOOL_COMMON, at, extra_ok=True)
        if "tool" not in table:
            raise HepError("a tool table needs tool = \"<standard tool>\" or \"custom\"", where=at)
        if table.get("shards", 1) < 1:
            raise HepError("shards must be at least 1", where=f"{at}.shards")
        tools[tag] = Tool(tag=tag, tool=table["tool"], baseconfig=_as_list(table.get("baseconfig")),
                          input=_as_list(table.get("input")), output_file=_as_list(table.get("output_file")),
                          timeout=float(table.get("timeout", 0)), stall_after=float(table.get("stall_after", 0)),
                          status=table.get("status", ""), executable=table.get("executable", ""),
                          arguments=list(table.get("arguments", [])), consumes=list(table.get("consumes", [])),
                          config=table.get("config"), streamable=table.get("streamable"),
                          consumes_events=table.get("consumes_events"), shards=int(table.get("shards", 1)),
                          extra=extras)

    static = raw.get("static", {})
    if not isinstance(static, dict):
        raise HepError("[static] is a table of quantity = value", where=where)
    for name in static:
        if name not in quantities:
            raise HepError(f"[static] sets '{name}', which is not a [quantities.<q>] table",
                           where=f"{where}: [static]", hint=did_you_mean(name, quantities))

    configurations: dict[str, Configuration] = {}
    for key, table in run.items():
        if not isinstance(table, dict):
            continue
        at = f"{where}: [run.{key}]"
        _check(table, CONFIGURATION_KEYS, at)
        if "tools" not in table:
            raise HepError("a configuration needs tools = [...]", where=at)
        sweeps = _sweeps(table.get("sweeps", []), f"{at}.sweeps", quantities)
        swept = {n for entry in sweeps for n in (entry if isinstance(entry, list) else [entry])}
        plot_points = table.get("plot_points", [])
        for name in plot_points:
            if name not in swept:
                raise HepError(f"plot_points names '{name}', which is not swept here", where=f"{at}.plot_points",
                               hint="pages are cells of the grid of swept quantities (04 §5.2)")
        combine = table.get("combine", [])
        axes = {entry for entry in sweeps if isinstance(entry, str)}
        for name in combine:                                                # C14
            if name not in axes:
                raise HepError(f"combine names '{name}', which is not swept here as an axis of its own",
                               where=f"{at}.combine",
                               hint="the points that differ only in a combined quantity are merged into one (04 §5.5)")
            if name in plot_points:
                raise HepError(f"'{name}' is both combined and a page axis (plot_points)", where=f"{at}.combine",
                               hint="a combined quantity's points become one curve: it cannot also make pages")
        local_static = table.get("static", {})
        for name in local_static:
            if name not in quantities:
                raise HepError(f"static sets '{name}', which is not a [quantities.<q>] table", where=f"{at}.static",
                               hint=did_you_mean(name, quantities))
        local_prelim = table.get("prelim")
        if local_prelim is not None:
            _check(local_prelim, PRELIM_KEYS, f"{at}.prelim")
        event_count = table.get("event_count", run.get("event_count"))
        if event_count is None:
            raise HepError("no event_count: set it here or in [run]", where=at)
        configurations[key] = Configuration(
            key=key, name=table.get("name", key), serial=table.get("serial", run.get("serial")),   # V43
            swept=table.get("swept", True), title=table.get("title", key),
            seed_type=_seed_type(table.get("seed_type", run.get("seed_type", "identity")),
                                 f"{at}.seed_type" if "seed_type" in table else f"{where}: [run].seed_type"),
            manual_seed=_manual_seed(table.get("manual_seed", run.get("manual_seed")),
                                     f"{at}.manual_seed" if "manual_seed" in table else f"{where}: [run].manual_seed"),
            description=table.get("description", ""), event_count=int(event_count),
            threads=_resolved_threads(int(table.get("threads", run.get("threads", 1))), f"{at}.threads"),
            parallelism=_parallelism(int(table.get("parallelism", run.get("parallelism", 1))), f"{at}.parallelism"),
            sweeps=sweeps, plot_points=list(plot_points), combine=list(combine),
            tools=_groups(table["tools"], f"{at}.tools", tools),
            post=_groups(table.get("post", []), f"{at}.post", tools),
            pre=_groups(table.get("pre", []), f"{at}.pre", tools),
            static={**static, **local_static},
            prelim=local_prelim if local_prelim is not None else prelim)

    if sweep_on and not any(c.swept for c in configurations.values()):
        raise HepError("[run].sweep_runs is on but every configuration has swept = false", where=f"{where}: [run].sweep_runs",
                       hint="leave one in, or turn the sweep off")
    if "configuration" in run and run["configuration"] not in configurations:
        raise HepError(f"[run].configuration is '{run['configuration']}', which is not a [run.<name>] table",
                       where=f"{where}: [run].configuration",
                       hint=did_you_mean(run["configuration"], configurations)
                       or f"configurations: {', '.join(configurations) or '(none)'}")

    plot = raw.get("plot", {})
    if "legend" in plot:
        raise HepError("[plot].legend is now part of the style", where=f"{where}: [plot].legend",
                       hint=f'[plot.style] legend.position = "{plot["legend"]}" (or in the root_style file)')
    # "default" is every drawing option's own value (V37): the tool decides; plot.py resolves it
    _check({k: v for k, v in plot.items() if v != "default" or k in ("data", "style", "object")}, PLOT_KEYS,
           f"{where}: [plot]")

    return RunConfig(path=path, project=project, name=run["name"], serial=run.get("serial"),
                     default_configuration=run.get("configuration"), configurations=configurations,
                     prelim=prelim, static=static, tools=tools, quantities=quantities, plot=plot,
                     master_toml=master.get("master_toml"), raw=raw, sweep_runs=sweep_on)
