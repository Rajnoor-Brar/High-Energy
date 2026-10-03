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
from .paths import config_file, configs_root, resolve
from .quantities import check_shapes

#: How a point's seeds are chosen (V39, 02 §8); the schema's [run.seed_type].choices.
SEED_TYPES = tuple(schema.keys("run")["seed_type"]["choices"])
DEFAULT = schema.DEFAULT
CURVE_LINES = ("solid", "dashed", "dotted", "dashdot")


def check_curve_style(look, where: str) -> None:
    """A quantity value's curve look (V67): colour ("#rrggbb", a ROOT name or number), line, width
    (points); "default" for a key is the style's, as if left out."""
    if not isinstance(look, dict):
        raise HepError("a style is a table, { colour, line, width }", where=where)
    for key, value in look.items():
        if value == DEFAULT:
            continue
        if key == "colour":
            ok = isinstance(value, str) and value or isinstance(value, int) and not isinstance(value, bool)
        elif key == "line":
            ok = value in CURVE_LINES
        elif key == "width":
            ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
        else:
            raise HepError(f"a style has no key '{key}'", where=where, hint=did_you_mean(key, ["colour", "line", "width"])
                           or "its keys: colour, line, width")
        if not ok:
            raise HepError(f"style {key} = {value!r} is not one", where=where,
                           hint={"colour": '"#rrggbb", a ROOT colour name ("kBlue+1") or number',
                                 "line": " | ".join(CURVE_LINES), "width": "a number of points > 0"}[key])


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
    settings: dict = field(default_factory=dict)     # native card settings, as written (V59)
    cores: int = 0                                   # cores it keeps busy, for --plan's note (0: estimated, V60)
    filters: str = ""                                # its own filters.toml (configs/<P>/…), V61
    extra: dict = field(default_factory=dict)       # tool-specific keys and export requests


@dataclass
class Quantity:
    name: str
    values: list
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    styles: list[dict] = field(default_factory=list)   # one per value: its curves' look (V67)
    key: str | dict | None = None
    target: list[str] = field(default_factory=list)
    format: str = ""
    description: str = ""
    exclude: list[int] = field(default_factory=list)   # 1-based value indices a sweep leaves out (V42)


@dataclass
class Configuration:
    key: str
    label: str                                      # its folder: [run.<cfg>].label, else the table key (V45)
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
    parallelism_auto: bool = False                      # "auto" (V75): set from the plans, cores ÷ a point's
    swept: bool = True                                  # run by [run].sweep_runs (V38)
    title: str = ""                                     # the `run NN - <title> -` header of a sweep
    run_folder: str = ""                                # <project>/<run_folder>/…: [run.<cfg>].name, else [run].name (V46)
    seed_type: str = "identity"                         # SEED_TYPES (V39)
    manual_seed: int | None = None                      # seed_type = "manual": every point's seed
    origins: dict = field(default_factory=dict)         # key → where its value came from (--show-config, V56)


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
    included: dict = field(default_factory=dict)        # "<section>.<name>" → the [master].include file it came from

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

#: [run.defaults]: keys every configuration shares (V56); a reserved name, never a configuration.
DEFAULTS = "defaults"
#: Each configuration's own: never taken from the one it extends, [run.defaults] or [run].
OWN = ("label", "title", "extends", "swept")


def _layers(run: dict, where: str) -> dict[str, list[tuple[str, dict]]]:
    """Each configuration's layers, most specific first (V56): its own table, the ones it `extends`, in
    turn, then [run.defaults]. [run] and the schema's defaults come after, in `inherited`."""
    tables = {k: v for k, v in run.items() if isinstance(v, dict)}
    defaults = tables.pop(DEFAULTS, None)
    if defaults is not None:
        schema.check(defaults, "configuration", f"{where}: [run.{DEFAULTS}]")
        own = [k for k in OWN if k in defaults]
        if own:
            raise HepError(f"[run.{DEFAULTS}] sets {', '.join(own)}, which each configuration has of its own",
                           where=f"{where}: [run.{DEFAULTS}]", hint="set them in the configurations")
    out = {}
    for key, table in tables.items():
        schema.check(table, "configuration", f"{where}: [run.{key}]")
        chain, seen, parent = [(f"[run.{key}]", table)], {key}, table.get("extends")
        while parent:
            if parent not in tables:
                raise HepError(f"extends names '{parent}', which is not a configuration", where=f"{where}: [run.{chain[-1][0][5:-1]}].extends",
                               hint=did_you_mean(parent, tables) or f"configurations: {', '.join(tables)}")
            if parent in seen:
                raise HepError(f"extends goes round in a circle: {' → '.join([*seen, parent])}", where=f"{where}: [run.{key}].extends")
            seen.add(parent)
            chain.append((f"[run.{parent}]", tables[parent]))
            parent = tables[parent].get("extends")
        if defaults is not None:
            chain.append((f"[run.{DEFAULTS}]", defaults))
        out[key] = chain
    return out


def _deep(base: dict, over: dict) -> dict:
    """`over` merged into `base`, tables recursively, anything else replaced; a "default" keeps base's."""
    out = dict(base)
    for key, value in over.items():
        if value == DEFAULT:
            continue
        out[key] = _deep(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def _own_prelim(chain, prelim: dict, origins: dict) -> dict:
    """A configuration's [prelim] is the nearest layer's, whole, else the file's: the interfaces belong to
    one chain (eic's delphes writes a file where the default chain has a FIFO), so they are not merged."""
    for origin, layer in chain:
        if isinstance(layer.get("prelim"), dict):
            origins["prelim"] = origin
            return layer["prelim"]
    origins["prelim"] = "[prelim]"
    return prelim


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

def _read(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise HepError("cannot read the file", where=str(path)) from None
    except tomllib.TOMLDecodeError as error:
        escape = "escape" in str(error).lower() or "'\\'" in str(error)
        raise HepError(f"not valid TOML: {error}", where=str(path),
                       hint="in a \"…\" string a backslash starts a TOML escape: write the label in single quotes, "
                            "'PDF4LHC21\\_40', or double the backslash, \"PDF4LHC21\\\\_40\"" if escape else None) from None


#: How an included file's sections meet the file's (V56): whole entries replace for quantities and tools
#: (a redefined quantity takes nothing of the included one), keys for [static], tables recursively else.
ENTRIES = ("quantities", "tools")


def _over(base: dict, over: dict) -> dict:
    out = dict(base)
    for section, value in over.items():
        if section in ENTRIES and isinstance(value, dict):
            out[section] = {**out.get(section, {}), **value}
        elif section == "run" and isinstance(value, dict):          # configurations whole, [run] keys one by one
            out[section] = {**out.get(section, {}), **value}
        elif isinstance(value, dict) and isinstance(out.get(section), dict):
            out[section] = _deep(out[section], value)
        else:
            out[section] = value
    return out


def _with_includes(raw: dict, path: Path) -> tuple[dict, dict]:
    """[master].include = ["common.toml"]: the run starts from those files' tables, in order, and its own
    win (V56). Returns the merged tables and which included file gave each quantity, tool and configuration."""
    names = _as_list(raw.get("master", {}).get("include"))
    if not names:
        return raw, {}
    project = raw.get("run", {}).get("project")
    if not project:
        raise HepError("[master].include needs [run].project in the file itself", where=f"{path}: [master].include")
    merged, included = {}, {}
    for name in names:
        source = resolve(name, "master", project=project, where=f"{path}: [master].include")
        if source.suffix != ".toml":
            source = source.with_name(source.name + ".toml")
        part = _read(source)
        if "master" in part:
            raise HepError("an included file has no [master] of its own (includes do not nest)", where=str(source))
        for section in ENTRIES:
            included.update({f"{section}.{key}": source.name for key in part.get(section, {})})
        included.update({f"run.{key}": source.name for key, v in part.get("run", {}).items() if isinstance(v, dict)})
        merged = _over(merged, part)
    for section in ENTRIES:                                           # the file's own entries are its own
        for key in raw.get(section, {}):
            included.pop(f"{section}.{key}", None)
    for key, value in raw.get("run", {}).items():
        if isinstance(value, dict):
            included.pop(f"run.{key}", None)
    return _over(merged, raw), included


def load(name: str, *, sets: list[str] = ()) -> RunConfig:
    path = config_file(name)
    raw, included = _with_includes(_read(path), path)
    apply_sets(raw, list(sets))
    run = parse(raw, path)
    run.included = included
    return run


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
        for listed in ("tags", "labels", "styles"):
            if listed in table and len(table[listed]) != len(values):
                raise HepError(f"'{listed}' must have one entry per value ({len(values)})", where=f"{at}.{listed}")
        for i, look in enumerate(table.get("styles", []), start=1):
            check_curve_style(look, f"{at}.styles[{i}]")
        exclude = table.get("exclude", [])
        for index in exclude:
            if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= len(values):
                raise HepError(f"exclude names {index!r}, which is not a value's place", where=f"{at}.exclude",
                               hint=f"1-based: 1 to {len(values)}, as static \"#2\" and --points 2 count")
        if len(set(exclude)) == len(values):
            raise HepError("exclude leaves no value to sweep", where=f"{at}.exclude")
        quantity = Quantity(name=name, values=values, tags=[str(t) for t in table.get("tags", [])],
                                    labels=[str(l) for l in table.get("labels", [])], key=table.get("key"),
                                    styles=[{k: v for k, v in s.items() if v != DEFAULT} for s in table.get("styles", [])],
                                    target=_as_list(table.get("target")), format=table.get("format", ""),
                                    description=table.get("description", ""), exclude=sorted(set(exclude)))
        check_shapes(quantity, at)                                          # V58: the vocabulary's shape
        quantities[name] = quantity

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
                          settings=dict(table.get("settings", {})), cores=int(table.get("cores", 0)),
                          filters=table.get("filters", ""),
                          extra=extras)

    static = raw.get("static", {})
    if not isinstance(static, dict):
        raise HepError("[static] is a table of quantity = value", where=where)
    for name in static:
        if name not in quantities:
            raise HepError(f"[static] sets '{name}', which is not a [quantities.<q>] table",
                           where=f"{where}: [static]", hint=did_you_mean(name, quantities))

    configurations: dict[str, Configuration] = {}
    for key, chain in _layers(run, where).items():
        table = chain[0][1]
        at = f"{where}: [run.{key}]"
        origins: dict[str, str] = {}

        def inherited(name: str, fallback=None):
            """The most specific layer's value (V56): own, extended, [run.defaults], then [run]; a
            "default" in a layer is the next one's (V55); else the schema's default."""
            layers = chain[:1] if name in OWN else chain
            if name in schema.keys("run"):
                layers = [*layers, ("[run]", run)]
            for origin, layer in layers:
                if name in layer and layer[name] != DEFAULT:
                    origins[name] = origin
                    return layer[name]
            origins[name] = "default"
            value = schema.default("configuration", name, schema.default("run", name))
            return fallback if value is None else value

        def merged(name: str, base: dict) -> dict:
            """A table merged through the layers, parent first ([static], [prelim])."""
            out = dict(base)
            for origin, layer in reversed(chain):
                if isinstance(layer.get(name), dict):
                    out = _deep(out, layer[name])
                    origins[name] = origin
            return out

        tools_entries = inherited("tools")
        if tools_entries is None:
            raise HepError("a configuration needs tools = [...]", where=at,
                           hint="here, in the configuration it extends, or in [run.defaults]")
        sweeps = _sweeps(inherited("sweeps", []), f"{at}.sweeps", quantities)
        swept = {n for entry in sweeps for n in (entry if isinstance(entry, list) else [entry])}
        plot_points = inherited("plot_points", [])
        for name in plot_points:
            if name not in swept:
                raise HepError(f"plot_points names '{name}', which is not swept here", where=f"{at}.plot_points",
                               hint="pages are cells of the grid of swept quantities (04 §5.2)")
        combine = inherited("combine", [])
        axes = {entry for entry in sweeps if isinstance(entry, str)}
        for name in combine:                                                # C14
            if name not in axes:
                raise HepError(f"combine names '{name}', which is not swept here as an axis of its own",
                               where=f"{at}.combine",
                               hint="the points that differ only in a combined quantity are merged into one (04 §5.5)")
            if name in plot_points:
                raise HepError(f"'{name}' is both combined and a page axis (plot_points)", where=f"{at}.combine",
                               hint="a combined quantity's points become one curve: it cannot also make pages")
        local_static = merged("static", {})
        for name in local_static:
            if name not in quantities:
                raise HepError(f"static sets '{name}', which is not a [quantities.<q>] table", where=f"{at}.static",
                               hint=did_you_mean(name, quantities))
        for _, layer in chain:
            if isinstance(layer.get("prelim"), dict):
                schema.check(layer["prelim"], "prelim", f"{at}.prelim")
        event_count = inherited("event_count")
        if event_count is None:
            raise HepError("no event_count: set it here or in [run]", where=at)
        static_values = {k: v for k, v in _deep(static, local_static).items() if v != DEFAULT}   # top-level "default": unset
        configurations[key] = Configuration(
            key=key, label=table.get("label") or key, serial=inherited("serial"),                     # V45
            run_folder=inherited("name") or run["name"],                                              # V46
            swept=table.get("swept", schema.default("configuration", "swept")), title=table.get("title", key),
            seed_type=inherited("seed_type"), manual_seed=inherited("manual_seed"),
            description=inherited("description", ""), event_count=int(event_count),
            threads=_resolved_threads(int(inherited("threads"))), parallelism=1 if inherited("parallelism") == "auto" else int(inherited("parallelism")),
            parallelism_auto=inherited("parallelism") == "auto",
            sweeps=sweeps, plot_points=list(plot_points), combine=list(combine),
            tools=_groups(tools_entries, f"{at}.tools", tools),
            post=_groups(inherited("post", []), f"{at}.post", tools),
            pre=_groups(inherited("pre", []), f"{at}.pre", tools),
            static=static_values,
            prelim=_own_prelim(chain, prelim, origins),                     # replaced whole: its chain's interfaces
            origins=origins)

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

