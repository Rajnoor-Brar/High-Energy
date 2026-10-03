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

from . import schema
from .errors import HepError, did_you_mean
from .paths import config_file, configs_root

#: How a point's seeds are chosen (V39, 02 §8); the schema's [run.seed_type].choices.
SEED_TYPES = tuple(schema.keys("run")["seed_type"]["choices"])
DEFAULT = schema.DEFAULT


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
    run_name: str = ""                                  # <project>/<run_name>/…: [run].name, or this one's own (V46)
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


def _resolved_threads(value: int) -> int:
    return value or (os.cpu_count() or 1)             # 0 = every core: resolved here, never passed on as 0


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
    sections = schema.sections()
    for key in raw:
        if key not in sections:
            raise HepError(f"unknown section [{key}]", where=where,
                           hint=did_you_mean(key, sections) or f"sections: {', '.join(sections)}")

    master = raw.get("master", {})
    schema.check(master, "master", f"{where}: [master]")

    run = raw.get("run")
    if not isinstance(run, dict):
        raise HepError("missing [run]", where=where, hint="every run TOML has [run] name, project, configuration")
    schema.check(run, "run", f"{where}: [run]", subtables=True)
    sweep_on = run.get("sweep_runs") is True
    for required in ("name", "project") + (() if sweep_on else ("configuration",)):
        if required not in run:
            raise HepError(f"[run] needs '{required}'", where=f"{where}: [run]")
    project = run["project"]
    # A config under configs/<X>/ belongs to project X; one given as ./path elsewhere (tests) need not.
    if path.parent.parent == configs_root() and path.parent.name != project:
        raise HepError(f"[run].project is '{project}' but the file is in configs/{path.parent.name}/",
                       where=f"{where}: [run].project", hint="they must match")

    prelim = raw.get("prelim", {})
    schema.check(prelim, "prelim", f"{where}: [prelim]")

    quantities: dict[str, Quantity] = {}
    for name, table in raw.get("quantities", {}).items():
        at = f"{where}: [quantities.{name}]"
        if not isinstance(table, dict):
            raise HepError("a quantity is a table", where=at)
        schema.check(table, "quantity", at)
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
        extras = schema.check(table, "tool", at, extra=True)
        if "tool" not in table:
            raise HepError("a tool table needs tool = \"<standard tool>\" or \"custom\"", where=at)
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
        schema.check(table, "configuration", at)

        def inherited(name: str):
            """This configuration's value, else [run]'s (\"default\" in the child: [run]'s, V55), else the
            schema's default."""
            value = table.get(name, DEFAULT)
            if value == DEFAULT:
                value = run.get(name, DEFAULT)
            return schema.default("run", name) if value == DEFAULT else value

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
            schema.check(local_prelim, "prelim", f"{at}.prelim")
        event_count = inherited("event_count")
        if event_count is None:
            raise HepError("no event_count: set it here or in [run]", where=at)
        configurations[key] = Configuration(
            key=key, name=table.get("label") or key, serial=inherited("serial"),                     # V45
            run_name=table.get("name", run["name"]),                                                 # V46
            swept=table.get("swept", schema.default("configuration", "swept")), title=table.get("title", key),
            seed_type=inherited("seed_type"), manual_seed=inherited("manual_seed"),
            description=table.get("description", ""), event_count=int(event_count),
            threads=_resolved_threads(int(inherited("threads"))), parallelism=int(inherited("parallelism")),
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
    check_plot(plot, f"{where}: [plot]")

    return RunConfig(path=path, project=project, name=run["name"], serial=run.get("serial"),
                     default_configuration=run.get("configuration"), configurations=configurations,
                     prelim=prelim, static=static, tools=tools, quantities=quantities, plot=plot,
                     master_toml=master.get("master_toml"), raw=raw, sweep_runs=sweep_on)


def check_plot(plot: dict, where: str) -> None:
    """[plot] and its children against the schema, when the file is read (C11, V55): every key, type and
    bound of [plot], [plot.data], [plot.object."<glob>"] and [plot.overlay.<name>]. What needs the style
    (base.toml) or a backend is plot.validate's."""
    schema.check(plot, "plot", where)
    schema.check(plot.get("data", {}), "data", f"{where}.data")
    for glob, table in plot.get("object", {}).items():
        if not isinstance(table, dict):
            raise HepError("an object's table holds keys", where=f'{where}.object."{glob}"')
        schema.check(table, "plot_child", f'{where}.object."{glob}"')
    for name, table in plot.get("overlay", {}).items():
        at = f"{where}.overlay.{name}"
        if not isinstance(table, dict):
            raise HepError("an overlay is a table", where=at)
        own = {k: v for k, v in table.items() if k in schema.keys("overlay")}
        schema.check({k: v for k, v in table.items() if k not in own}, "plot_child", at)
        schema.check(own, "overlay", at)
        objects, labels = table.get("objects"), table.get("labels")
        if not objects:
            raise HepError("an overlay needs objects = [\"d02-x01-y01\", …]: the histograms drawn together",
                           where=f"{at}.objects")
        if labels is not None and len(labels) != len(objects):
            raise HepError(f"labels must give one label per object ({len(objects)})", where=f"{at}.labels")

