"""Tool folders, point cards, argv, and the connection rules (rank 2).

docs/06_Developer_Guide.md §4 (the tool-folder contract), docs/02_Architecture.md §6 (connections) and
docs/04_Config_Reference.md §9 (tool tables, custom tools, standard configurations). Everything the runner knows
about a tool comes from its folder utils/Env/<tool>/. This module never names one.

`plan_point` turns (run, configuration, point) into groups of Steps: argv, environment, files to
write, inputs and outputs, and what to check afterwards. Nothing is spawned or written here; that is
`execute`. Seeds are added last (`finalise`), because they derive from the identity of everything
else (02 §8).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import tomli_w

from . import quantities as qmod
from .config import Tool
from .errors import HepError, did_you_mean
from .paths import output_root, repo_root, resolve, results_root
from .sweep import label_of, tag_of

ENV = Path(__file__).resolve().parents[1]                 # utils/Env

FOLDER_SECTIONS = {
    "tool": {"category", "executable", "streamable", "status", "consumes_events", "produces_events"},
    "card": {"style", "ext", "comment", "bools", "seed", "seed_parallel", "line", "footer"},
    "command": {"argv", "env", "cwd"},
    "options": None,                                      # free: the schema of tool-specific keys
    "outputs": {"products", "event_count", "sidecar", "written", "deal"},
    "exports": None,
    "identity": {"files", "version"},
    "prepare": {"argv", "marker", "ignore", "key"},
    "checks": {"info_dirs", "info_dirs_command", "files"},
    "shard": {"merge"},
}
CARD_STYLES = ("append", "prepend", "none", "render")
EXPORT = re.compile(r"^(?P<tool>[a-z0-9]+)_(?P<export>[a-z0-9_]+)$")


# ── tool folders ───────────────────────────────────────────────────────────────────────────────

@dataclass
class Folder:
    name: str
    dir: Path
    spec: dict

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.spec.get(section, {}).get(key, default)

    @property
    def card_style(self) -> str:
        return self.get("card", "style", "none")

    @property
    def plugin(self):
        """utils/Env/<tool>/render.py, for `[card] style = "render"` (06 §4)."""
        path = self.dir / "render.py"
        if not path.is_file():
            raise HepError(f'{self.name} has [card] style = "render" but no render.py', where=str(self.dir))
        import importlib.util
        spec = importlib.util.spec_from_file_location(f"hep_render_{self.name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @property
    def filters(self) -> list[dict]:
        path = self.dir / "filters.toml"
        return tomllib.loads(path.read_text(encoding="utf-8")).get("rule", []) if path.exists() else []


_FOLDERS: dict[str, Folder] | None = None


def folders() -> dict[str, Folder]:
    """Every utils/Env/<tool>/tool.toml, checked. The set of folders is the dict of standard tools."""
    global _FOLDERS
    if _FOLDERS is None:
        found = {}
        for path in sorted(ENV.glob("*/tool.toml")):
            where = str(path.relative_to(repo_root()))
            try:
                spec = tomllib.loads(path.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as error:
                raise HepError(f"not valid TOML: {error}", where=where)
            for section, table in spec.items():
                if section not in FOLDER_SECTIONS:
                    raise HepError(f"unknown section [{section}] in a tool folder", where=where,
                                   hint=did_you_mean(section, FOLDER_SECTIONS))
                allowed = FOLDER_SECTIONS[section]
                if allowed is not None:
                    for key in table:
                        if key not in allowed:
                            raise HepError(f"unknown key [{section}].{key}", where=where,
                                           hint=did_you_mean(key, allowed))
            style = spec.get("card", {}).get("style", "none")
            if style not in CARD_STYLES:
                raise HepError(f"[card].style must be one of {', '.join(CARD_STYLES)}", where=where)
            found[path.parent.name] = Folder(path.parent.name, path.parent, spec)
        _FOLDERS = found
    return _FOLDERS


def folder_of(tool) -> Folder:
    known = folders()
    if tool.tool not in known:
        raise HepError(f"tool = \"{tool.tool}\" is not a standard tool", where=f"[tools.{tool.tag}]",
                       hint=did_you_mean(tool.tool, known) or f"tool folders: {', '.join(known)}")
    return known[tool.tool]


# ── placeholders ───────────────────────────────────────────────────────────────────────────────

def expand(template: str, context: dict[str, Any], where: str) -> str | list[str]:
    """`{name}` and `{name:arg}` replaced from `context`; `{{`/`}}` are literal braces. A template
    that is exactly one placeholder whose value is a list becomes that list (spliced into argv)."""
    whole = re.fullmatch(r"\{([a-z_]+(?::[^{}]*)?)\}", template)
    if whole and isinstance(_lookup(whole.group(1), context, where), list):
        return [str(v) for v in _lookup(whole.group(1), context, where)]
    out, i = [], 0
    while i < len(template):
        if template.startswith("{{", i):
            out.append("{"); i += 2
        elif template.startswith("}}", i):
            out.append("}"); i += 2
        elif template[i] == "{":
            end = template.index("}", i)
            value = _lookup(template[i + 1:end], context, where)
            out.append(",".join(map(str, value)) if isinstance(value, list) else str(value))
            i = end + 1
        else:
            out.append(template[i]); i += 1
    return "".join(out)


def _lookup(name: str, context: dict, where: str):
    if name in context:
        return context[name]
    head, _, arg = name.partition(":")
    table = context.get(f"{head}:")
    if isinstance(table, dict) and arg in table:
        return table[arg]
    raise HepError(f"unknown placeholder {{{name}}}", where=where,
                   hint=did_you_mean(name, [k for k in context if not k.endswith(":")]))


# ── values in native cards ─────────────────────────────────────────────────────────────────────

def native(value: Any, bools: list[str], fmt: str = "") -> str:
    if fmt:
        return fmt.format(value)
    if isinstance(value, bool):
        return bools[0] if value else bools[1]
    if isinstance(value, float):
        return repr(value)
    return str(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def executable_of(tool, folder: Folder, project: str) -> Path:
    """A folder's executable (`{repo}` expanded, else PATH), or a custom table's (04 §2: bare →
    build/<project>/<name>; when that does not exist, a command on PATH, shown by --plan)."""
    if tool.executable:
        candidate = resolve(tool.executable, "executable", project=project, where=f"[tools.{tool.tag}].executable")
        if candidate.exists() or "/" in tool.executable:
            return candidate
        found = shutil.which(tool.executable)
        if found:
            return Path(found)
        raise HepError(f"executable '{tool.executable}' is neither {candidate} nor a command on PATH",
                       where=f"[tools.{tool.tag}].executable",
                       hint=f"build it (make modules/{project}/{Path(tool.executable).stem}.cc → .exe)")
    template = folder.get("tool", "executable")
    if not template:
        raise HepError(f"[tools.{tool.tag}] needs executable = \"...\"", where=f"[tools.{tool.tag}]")
    text = expand(template, {"repo": str(repo_root())}, f"{folder.name}/tool.toml")
    if "/" in text:
        path = Path(text)
        if not path.exists():
            rel = path.relative_to(repo_root()) if path.is_relative_to(repo_root()) else path
            raise HepError(f"{rel} is not built", where=f"tool '{folder.name}'",
                           hint="run `hep build` (or make utils/App_*.exe)")
        return path
    found = shutil.which(text)
    if not found:
        raise HepError(f"'{text}' is not on PATH", where=f"tool '{folder.name}'", hint="load_hep first")
    return Path(found)


_VERSIONS: dict[str, str] = {}


def version_of(folder: Folder) -> str:
    command = folder.get("identity", "version")
    if not command:
        return ""
    key = " ".join(command)
    if key not in _VERSIONS:
        try:
            out = subprocess.run(command, capture_output=True, text=True, timeout=30)
            _VERSIONS[key] = (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else ""
        except (OSError, subprocess.SubprocessError):
            _VERSIONS[key] = "?"
    return _VERSIONS[key]


# ── the plan of one point ──────────────────────────────────────────────────────────────────────

@dataclass
class Interface:
    name: str
    path: Path
    kind: str                          # fifo | file | product | points (post: that product of every point)
    producer: str = ""                 # tag
    readers: list[str] = field(default_factory=list)
    group: int = -1
    paths: list[Path] = field(default_factory=list)   # kind points: one per point, in point order
    names: list[str] = field(default_factory=list)    # … and the points' names
    shard: bool = False                # one shard's product: technical, merged into the table's own output


@dataclass
class Step:
    tag: str
    tool: Any                          # config.Tool
    folder: Folder
    group: int
    exe: Path
    argv: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    log: Path | None = None
    status: str = "none"               # standard | filters | none
    filters: list[dict] = field(default_factory=list)
    inputs: list[Interface] = field(default_factory=list)
    outputs: list[Interface] = field(default_factory=list)
    products: list[tuple[Path, Path]] = field(default_factory=list)   # (final, partial)
    sidecar: Path | None = None        # what it writes, as a producer of events
    count_check: tuple[Path, Path, str, str | None] | None = None     # (product partial, sidecar, reader, output key)
    stall_after: float = 300.0
    timeout: float = 0.0
    card_base: list[Path] = field(default_factory=list)
    card_lines: list[str] = field(default_factory=list)                # the point card, before seeds
    card_point: Path | None = None
    card_combined: Path | None = None
    config_path: Path | None = None
    config_data: dict | None = None
    identity_parts: dict = field(default_factory=dict)
    card_lines_for_key: list[str] = field(default_factory=list)
    cwd: Path | None = None            # where it runs (default: the point's output directory)
    prepare_dir: Path | None = None    # the prepare cache entry ([prepare]), keyed by the card
    prepare_argv: list[str] = field(default_factory=list)
    prepare_card: Path | None = None   # render.py's prepare_card(): the card the prepare step reads
    prepare_needed: bool = False       # in the chain, or asked for by an export with needs_prepare
    sidecar_written: int | None = None # [outputs] written = "requested": the runner writes the sidecar


@dataclass
class PointPlan:
    point: Any
    values: dict[str, int]             # active quantity → value index
    out: Path
    res: Path
    prelim: dict
    groups: list[list[Step]]
    rendered: dict[str, Step]          # every rendered tag, including export-only ones
    interfaces: dict[str, Interface]
    consumers: dict[str, list]
    identity: str = ""
    seed: int = 0
    threads: int = 1
    events: int = 0
    writes: dict[Path, str] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)   # post: {points}, the manifest
    upstream: list[str] = field(default_factory=list)       # post: the identities of the points
    deal: dict[str, str] = field(default_factory=dict)      # a dealt interface → its deal group (V31)
    seed_type: str = "identity"                             # a point's seed rule (V39); stages keep identity
    manual_seed: int | None = None
    seed_kept: bool = False                                 # random: a complete point's seed, from its provenance


def location(serial: int | None, name: str) -> str:
    return f"{serial:02d}_{name}" if serial is not None else name


def run_dir(run, configuration) -> Path:
    """<project>/<name>/<NN_><label> (V45, V46): `name` is [run]'s, or the configuration's own; the
    configuration's folder is its `label` (its table key when empty or unset), after one serial, the
    configuration's if it has one, else [run]'s."""
    return Path(run.project) / (configuration.run_name or run.name) / location(configuration.serial, configuration.name)


def point_dirs(run, configuration, point) -> tuple[Path, Path]:
    tail = run_dir(run, configuration) / point.name
    return output_root() / tail, results_root() / tail


def _check_options(tool, folder: Folder, where: str) -> None:
    schema = folder.spec.get("options", {})
    for key, value in tool.extra.items():
        if EXPORT.match(key) and tool.tool in ("custom", "module") and EXPORT.match(key).group("tool") in folders():
            continue
        if key not in schema:
            raise HepError(f"unknown key '{key}' for a {folder.name} tool", where=where,
                           hint=did_you_mean(key, schema) or (f"{folder.name} takes: {', '.join(schema)}"
                                                              if schema else f"{folder.name} takes no extra keys"))
        kind = schema[key].get("kind")
        types = {"list": list, "table": dict, "str": str, "int": int, "float": (int, float), "bool": bool, "flag": bool}
        if kind in types and not isinstance(value, types[kind]):
            raise HepError(f"'{key}' must be a {kind}", where=f"{where}.{key}")
    for key, rule in schema.items():
        if rule.get("required") and key not in tool.extra:
            raise HepError(f"a {folder.name} tool needs '{key}'", where=where)


def _export_requests(run, tool) -> dict[str, str]:
    """custom/module: `<tool>_<export> = true | "<tag>"` → {request key: referenced tag} (C13)."""
    if tool.tool not in ("custom", "module"):
        return {}
    out = {}
    for key, value in tool.extra.items():
        m = EXPORT.match(key)
        if not m or m.group("tool") not in folders() or value is False:
            continue
        kind = m.group("tool")
        if isinstance(value, str):
            tag = value
            if tag not in run.tools or run.tools[tag].tool != kind:
                raise HepError(f"{key} = \"{value}\" names no {kind} tool table", where=f"[tools.{tool.tag}].{key}")
        elif value is True:
            candidates = [t for t, other in run.tools.items() if other.tool == kind]
            if kind in run.tools and run.tools[kind].tool == kind:
                tag = kind
            elif len(candidates) == 1:
                tag = candidates[0]
            elif not candidates:
                raise HepError(f"{key}: there is no {kind} tool table to take the configuration from",
                               where=f"[tools.{tool.tag}].{key}", hint=f"add [tools.{kind}] with tool = \"{kind}\"")
            else:
                raise HepError(f"{key} = true matches several {kind} tables: {', '.join(candidates)}",
                               where=f"[tools.{tool.tag}].{key}", hint=f"name one: {key} = \"<tag>\" (C13)")
        else:
            raise HepError(f"{key} must be true, false or a tool tag", where=f"[tools.{tool.tag}].{key}")
        export = m.group("export")
        folder = folders()[kind]
        declared = folder.spec.get("exports", {})
        if not (export == "card" and folder.card_style != "none") and export not in declared:
            offers = (["card"] if folder.card_style != "none" else []) + list(declared)
            raise HepError(f"{kind} does not export '{export}'", where=f"[tools.{tool.tag}].{key}",
                           hint=did_you_mean(export, offers) or f"{kind} exports: {', '.join(offers) or 'nothing'}")
        out[key] = tag
    return out


def _resolve_chain(run, configuration, point) -> list[list[str]]:
    """Groups with `@quantity` entries replaced by the tool tag the point's value names (V19)."""
    groups = []
    for group in configuration.tools:
        resolved = []
        for member in group:
            if member.startswith("@"):
                name = member[1:]
                if name not in point.choice and name not in configuration.static:
                    raise HepError(f"'{member}' needs {name} swept or static", where=f"[run.{configuration.key}].tools")
                quantity = run.quantities[name]
                index = point.choice.get(name)
                if index is None:
                    index = qmod.select(quantity, configuration.static[name], f"static.{name}")
                member = quantity.values[index]
                if member not in run.tools:
                    raise HepError(f"'@{name}' took the value '{member}', which is not a tool tag",
                                   where=f"[quantities.{name}]", hint="its values must be [tools.<tag>] names (C5)")
            resolved.append(member)
        groups.append(resolved)
    return groups


def _shard(run, configuration, groups_tags: list[list[str]], out: Path):
    """`shards = K` on a table (V31): the table becomes K copies in its group, each reading a share of
    the events (`events.s1.hepmc` … `events.sK.hepmc`) and writing its product under the point's
    output/…/shards/; the folder's merge tool ([shard] merge) runs as its own group right after,
    reading the K products and writing the table's own output_file. The producer deals its events
    among the K interfaces instead of copying them to each (its folder says [outputs] deal = true).

    Seeds follow the generator's cards, not its argv, so a sharded point has the same events as the
    same point unsharded, and its merged product is the same up to rounding.
    Returns (run, configuration, groups, deal, shard products), rewritten for this point only."""
    sharded = [tag for group in groups_tags for tag in group if run.tools[tag].shards > 1]
    if not sharded:
        return run, configuration, groups_tags, {}, set()
    tables = dict(run.tools)
    quantities = dict(run.quantities)
    prelim = {key: list(value) for key, value in configuration.prelim.items()}
    groups = [list(group) for group in groups_tags]
    deal: dict[str, str] = {}
    shard_products: set[str] = set()
    for tag in sharded:
        tool = run.tools[tag]
        where = f"{run.path}: [tools.{tag}].shards"
        folder = folder_of(tool)
        merge = folder.get("shard", "merge")
        if not merge:
            raise HepError(f"a {folder.name} tool cannot be sharded", where=where,
                           hint="its tool folder has no [shard] merge: nothing would put the shares back together")
        if len(tool.input) != 1 or len(tool.output_file) != 1:
            raise HepError("a sharded tool reads one input and writes one output_file", where=where)
        name = tool.input[0]
        kind = "fifo" if name in prelim.get("fifo", []) else "files" if name in prelim.get("files", []) else ""
        if not kind:
            raise HepError(f"'{name}' is not a [prelim] FIFO or file", where=where,
                           hint="a sharded tool reads its events through an agreed interface, which the producer deals")
        producers = [t for group in groups for t in group if name in tables[t].output_file]
        if len(producers) != 1:
            raise HepError(f"'{name}' needs exactly one producer in the chain to be dealt", where=where)
        producer = producers[0]
        if not folder_of(tables[producer]).get("outputs", "deal"):
            raise HepError(f"'{producer}' ({tables[producer].tool}) cannot deal its events among shards", where=where,
                           hint="only a producer whose tool folder says [outputs] deal = true (pythia) can feed a sharded tool")
        head, dot, tail = name.rpartition(".")
        members = [f"{head}.s{i}.{tail}" if dot else f"{name}.s{i}" for i in range(1, tool.shards + 1)]
        prelim[kind] = [m for n in prelim[kind] for m in (members if n == name else [n])]
        deal.update({member: name for member in members})
        tables[producer] = replace(tables[producer], output_file=[m for o in tables[producer].output_file
                                                                  for m in (members if o == name else [o])])
        product = Path(tool.output_file[0])
        copies, parts = [], []
        for i, member in enumerate(members, start=1):
            copy = f"{tag}.{i}"
            if copy in tables:
                raise HepError(f"[tools.{copy}] exists, and it is the name of {tag}'s shard {i}", where=where)
            part = str(out / "shards" / f"{product.stem}.s{i}{product.suffix}")
            tables[copy] = replace(tool, tag=copy, input=[member], output_file=[part], shards=1)
            copies.append(copy)
            parts.append(part)
        shard_products.update(parts)
        quantities = _retarget(quantities, tag, copies)
        joined = f"{tag}.merge"
        tables[joined] = Tool(tag=joined, tool=merge, input=parts, output_file=list(tool.output_file))
        for g, group in enumerate(groups):
            if tag in group:
                at = group.index(tag)
                group[at:at + 1] = copies
                groups.insert(g + 1, [joined])
                break
    return (replace(run, tools=tables, quantities=quantities), replace(configuration, prelim=prelim), groups, deal,
            shard_products)


def _retarget(quantities: dict, tag: str, copies: list[str]) -> dict:
    """A quantity aimed at a sharded table (`target = "rivet/photo_eic"`, `key = {rivet = …}`) is
    aimed at every shard: each one runs the same analysis, with the same options, on its share."""
    out = dict(quantities)
    for name, quantity in quantities.items():
        target = []
        for entry in quantity.target:
            head, sep, rest = entry.partition("/")
            target += [f"{copy}{sep}{rest}" for copy in copies] if head == tag else [entry]
        key = quantity.key
        if isinstance(key, dict) and tag in key:
            key = {**key, **{copy: key[tag] for copy in copies}}
        if target != list(quantity.target) or key is not quantity.key:
            out[name] = replace(quantity, target=target, key=key)
    return out


def plan_point(run, configuration, point, master: dict, *, post: dict | None = None,
               pre: "PointPlan | None" = None) -> PointPlan:
    """The plan of one point. With `post` ({"manifest": Path, "products": {name: [Path]}}) it is a
    stage's (pre or post): no quantities, and an `input` naming a product of the points reads all of
    them. With `pre`, the pre stage's products are inputs the point may name, and its identity is
    part of the point's."""
    out, res = point_dirs(run, configuration, point)
    groups_tags = _resolve_chain(run, configuration, point)
    run, configuration, groups_tags, deal, shard_products = _shard(run, configuration, groups_tags, out)
    chain = [tag for group in groups_tags for tag in group]
    for tag in chain:
        if run.tools[tag].tool not in folders():
            folder_of(run.tools[tag])

    # standard-configuration requests pull in tables that are configured but not run (V21)
    requests = {tag: _export_requests(run, run.tools[tag]) for tag in chain}
    exported = [t for reqs in requests.values() for t in reqs.values() if t not in chain]
    rendered_tags = chain + list(dict.fromkeys(exported))

    # quantities: swept, then static where not swept; who consumes each (C7)
    values = dict(point.choice)
    for name, index in ({} if post else qmod.static_values(run, configuration)).items():
        values.setdefault(name, index)
    selectors = [m[1:] for group in configuration.tools for m in group if m.startswith("@")]
    alternatives = [v for name in selectors if name in run.quantities for v in run.quantities[name].values
                    if isinstance(v, str) and v in run.tools]
    consumers = qmod.consumer_table(run, master, [n for n in values if n not in selectors], rendered_tags, alternatives)
    consumers.update({name: [] for name in selectors if name in values})   # it chooses the tool itself

    plan = PointPlan(point=point, values=values, out=out, res=res, prelim=configuration.prelim,
                     groups=[], rendered={}, interfaces={}, consumers=consumers,
                     threads=configuration.threads, events=configuration.event_count, deal=deal)
    if post is None:                                   # a point, not a pre, post or combined stage
        plan.seed_type, plan.manual_seed = configuration.seed_type, configuration.manual_seed

    # interfaces declared in [prelim] live in the point's output directory
    for kind in ("fifo", "files"):
        for name in configuration.prelim.get(kind, []):
            if name in plan.interfaces:
                raise HepError(f"'{name}' is declared twice in [prelim]", where="[prelim]")
            plan.interfaces[name] = Interface(name, resolve(name, "prelim", root=out, where="[prelim]"),
                                              "fifo" if kind == "fifo" else "file")
    if pre is not None:                               # what the pre stage made, for every point
        plan.upstream = [pre.identity]
        for interface in pre.interfaces.values():
            if interface.kind == "product" and not interface.shard:
                plan.interfaces[interface.name] = Interface(interface.name, interface.path, "pre", producer="")
    if post:
        plan.context["points"] = str(post["manifest"])
        for name, pairs in post["products"].items():
            plan.interfaces[name] = Interface(name, pairs[0][1], "points", paths=[p for _, p in pairs],
                                              names=[n for n, _ in pairs])

    group_of = {tag: g for g, group in enumerate(groups_tags) for tag in group}
    for tag in rendered_tags:
        tool = run.tools[tag]
        folder = folder_of(tool)
        where = f"{run.path}: [tools.{tag}]"
        _check_options(tool, folder, where)
        for pattern in folder.get("checks", "files", []):          # what the tool needs built first
            needed = Path(expand(pattern, {"repo": str(repo_root())}, f"{folder.name}/tool.toml [checks].files"))
            if not needed.exists():
                raise HepError(f"{folder.name} needs {needed}, which does not exist", where=where,
                               hint="hep build (see utils/Env/" + folder.name + "/tool.toml)")
        step = Step(tag=tag, tool=tool, folder=folder, group=group_of.get(tag, -1),
                    exe=executable_of(tool, folder, run.project))
        step.status = tool.status or folder.get("tool", "status", "none")
        if step.status.startswith("filters:"):
            rules = resolve(step.status.split(":", 1)[1], "filters", project=run.project, where=f"{where}.status")
            step.filters = tomllib.loads(rules.read_text(encoding="utf-8")).get("rule", [])
            step.status = "filters"
        elif step.status == "filters":
            step.filters = folder.filters
        step.stall_after = tool.stall_after or 300.0
        step.timeout = tool.timeout
        step.log = out / "logs" / f"{tag}.log"
        plan.rendered[tag] = step
        if step.group >= 0:
            _outputs(plan, step, run)
    for name in shard_products:
        plan.interfaces[name].shard = True
    for tag in chain:
        _inputs(plan, plan.rendered[tag], run)
    _check_connections(plan, run)

    for tag in rendered_tags:
        _render(plan, plan.rendered[tag], run, master)
        _prepare_argv(plan, plan.rendered[tag])
    for tag in chain:
        _argv(plan, plan.rendered[tag], run, requests.get(tag, {}))
        if plan.rendered[tag].prepare_dir is not None:
            plan.rendered[tag].prepare_needed = True   # a chain step always runs its prepare (cached)

    plan.groups = [[plan.rendered[tag] for tag in group] for group in groups_tags]
    return plan


def _outputs(plan: PointPlan, step: Step, run) -> None:
    for name in step.tool.output_file:
        if name in plan.interfaces and plan.interfaces[name].kind == "points":
            raise HepError(f"'{name}' is the name of the points' product", where=f"[tools.{step.tag}].output_file",
                           hint="a post tool writes a new file; it reads the points' products with input = \"" + name + "\"")
        if name in plan.interfaces and plan.interfaces[name].producer:
            raise HepError(f"'{name}' is written by both {plan.interfaces[name].producer} and {step.tag}",
                           where=f"[tools.{step.tag}].output_file", hint="every output has exactly one writer (C6)")
        if name in plan.interfaces:
            interface = plan.interfaces[name]
        else:                                          # not an agreed interface: a product (04 §2)
            final = resolve(name, "output", root=plan.res, where=f"[tools.{step.tag}].output_file")
            interface = Interface(name, final, "product")
            plan.interfaces[name] = interface
            step.products.append((final, final.with_name(final.stem + ".partial" + final.suffix)))
        interface.producer, interface.group = step.tag, step.group
        step.outputs.append(interface)
    if step.folder.get("tool", "produces_events") and step.outputs and step.folder.get("outputs", "sidecar"):
        step.sidecar = Path(expand(step.folder.get("outputs", "sidecar"),
                                   {"output": str(step.outputs[0].path)}, step.folder.name))


def _inputs(plan: PointPlan, step: Step, run) -> None:
    for name in step.tool.input:
        interface = plan.interfaces.get(name)
        if interface is None:                          # a path: bare names under the point's output dir
            path = resolve(name, "input", root=plan.out, where=f"[tools.{step.tag}].input")
            interface = Interface(name, path, "file")
            plan.interfaces[name] = interface
        interface.readers.append(step.tag)
        step.inputs.append(interface)


def _check_connections(plan: PointPlan, run) -> None:
    """C6 (02 §6): FIFOs inside one group, one reader each, never into a non-streamable tool; files
    between groups; every input made by someone earlier or already on disk."""
    for interface in plan.interfaces.values():
        where = f"[prelim] / [tools.*]: '{interface.name}'"
        readers = [plan.rendered[r] for r in interface.readers if r in plan.rendered]
        if interface.kind in ("points", "pre"):        # made before the point starts: pre, or every point
            continue
        if interface.kind == "fifo":
            if not interface.producer:
                raise HepError(f"FIFO '{interface.name}' has no writer", where=where,
                               hint="name it in a tool's output_file; a FIFO nobody writes blocks its reader for ever")
            if len(readers) != 1:
                raise HepError(f"FIFO '{interface.name}' has {len(readers)} readers; a FIFO has exactly one",
                               where=where, hint="fan out with a list output_file on the producer, one FIFO per reader (V16)")
            reader = readers[0]
            if reader.group != interface.group:
                raise HepError(f"FIFO '{interface.name}' connects {interface.producer} and {reader.tag} across groups",
                               where=where, hint=f"put them in one group, [\"{interface.producer}\", \"{reader.tag}\"], "
                                                  "or use a [prelim] file: a later reader leaves the writer blocked (L8)")
            streamable = reader.tool.streamable if reader.tool.streamable is not None else reader.folder.get("tool", "streamable", False)
            if not streamable:
                raise HepError(f"'{reader.tag}' cannot read a FIFO", where=where,
                               hint="its tool folder says streamable = false (Delphes skips a zero-length input, L11); "
                                    "use a [prelim] file and put it in a later group")
        else:
            for reader in readers:
                if interface.producer:
                    if interface.group > reader.group:
                        raise HepError(f"'{reader.tag}' reads '{interface.name}' before {interface.producer} writes it",
                                       where=where, hint="the writer must be in an earlier group")
                    if interface.group == reader.group:
                        raise HepError(f"'{reader.tag}' and {interface.producer} share file '{interface.name}' in one group",
                                       where=where, hint="within a group the interface is a FIFO; between groups a file")
                elif interface.kind == "file" and interface.name not in plan.prelim.get("files", []) \
                        and not interface.path.exists():
                    raise HepError(f"'{reader.tag}' reads '{interface.name}', which nothing writes and does not exist",
                                   where=f"[tools.{reader.tag}].input", hint=f"expected at {interface.path}")


def _render(plan: PointPlan, step: Step, run, master: dict) -> None:
    """The point card (before seeds), extracted config values, flags and Rivet-style options."""
    folder, tool = step.folder, step.tool
    step.identity_parts = {"tag": step.tag, "tool": tool.tool, "exe": str(step.exe)}
    if step.exe.is_file():
        step.identity_parts["exe_sha256"] = sha256_file(step.exe)
    style = folder.card_style
    bools = folder.get("card", "bools", ["true", "false"])
    base_values = _base_values(tool, run, folder) if style == "append" else {}
    lines: list[str] = []
    redundant: list[str] = []          # overrides equal to the base card: rendered, not in the identity
    owners: dict[str, str] = {}
    flags: list[str] = []
    options: dict[str, dict[str, str]] = {}
    config_values: dict[str, Any] = {}
    overrides: list[qmod.Override] = []          # style "render": the values, for render.py
    line_format = folder.get("card", "line", "{key} = {value}")

    def claim(key: str, value: Any, origin: str, fmt: str = "") -> None:
        normal = "".join(key.split()).lower()
        if normal in owners and owners[normal] != origin:
            raise HepError(f"'{key}' is set by both {owners[normal]} and {origin}", where=f"[tools.{step.tag}]",
                           hint="one source per native key (C8): pin it in one place")
        owners[normal] = origin
        overrides.append(qmod.Override(key, value, origin))
        line = line_format.replace("{key}", key).replace("{value}", native(value, bools, fmt))
        lines.append(line)
        if base_values.get(normal) is not None and _same(base_values[normal], native(value, bools, fmt)):
            redundant.append(line)

    def apply(mapping, value: Any, origin: str) -> None:
        if mapping.check:
            qmod.check_provider(mapping.check, value, origin)
        if mapping.form == "key":
            claim(mapping.key, value, origin, mapping.format)
        elif mapping.form == "keys":
            if not isinstance(value, list) or len(value) != len(mapping.key):
                raise HepError(f"{origin}: expected {len(mapping.key)} values for {', '.join(mapping.key)}",
                               where=f"[tools.{step.tag}]")
            for key, item in zip(mapping.key, value):
                claim(key, item, origin, mapping.format)
        elif mapping.form == "flag":
            flags.extend([mapping.key, native(value, bools, mapping.format)])
        elif mapping.form == "option":
            options.setdefault(mapping.analysis, {})[mapping.key] = native(value, ["1", "0"], mapping.format)
        elif mapping.form == "config":
            config_values[mapping.key] = value
        elif mapping.form == "seed":
            step.identity_parts.setdefault("replica", []).append(value)
        elif mapping.form == "render":
            raise HepError(f"{origin}: render mappings arrive with their tool (render.py)", where=f"[tools.{step.tag}]")

    for name in ("events", "threads"):
        value = plan.events if name == "events" else plan.threads
        for mapping in qmod.builtin_mappings(master, run, [step.tag], name):
            apply(mapping, value, f"built-in {name}")
    for name, found in plan.consumers.items():
        quantity = run.quantities[name]
        index = plan.values[name]
        origin = f"[quantities.{name}] = {tag_of(quantity, index)}"
        for mapping in found:
            if mapping.tag == step.tag:
                apply(mapping, quantity.values[index], origin)

    step.identity_parts.update({"flags": flags, "options": options, "config_values": config_values})
    if style in ("append", "render"):
        ext = folder.get("card", "ext", "txt")
        comment = folder.get("card", "comment", "#")
        step.card_base = [resolve(b, "baseconfig", project=run.project, where=f"[tools.{step.tag}].baseconfig")
                          for b in tool.baseconfig]
        for base in step.card_base:
            if not base.is_file():
                raise HepError("base config not found", where=f"[tools.{step.tag}].baseconfig: {base}")
        output_name = (step.outputs[0].path.name if step.outputs          # an export-only step: its table's
                       else Path(tool.output_file[0]).name if tool.output_file else "")
        where_footer = f"{folder.name}/tool.toml [card].footer"
        footer_context = {"output_name": output_name, "tag": step.tag,
                          "input": str(step.inputs[0].path) if step.inputs else ""}
        footer = [expand(line, footer_context, where_footer) for line in folder.get("card", "footer", [])
                  if not all(footer_context.get(n, "x") == "" for n in re.findall(r"\{([a-z_]+)\}", line) or ["-"])]
        header = f"{comment} point card for [tools.{step.tag}], point {plan.point.name}, written by hep run"
        if style == "append":
            step.card_lines = [header, *lines, *footer]
            step.card_point = plan.out / "cards" / f"{step.tag}.point.{ext}"
        else:                                   # render.py writes the whole card: base and values merged
            text = folder.plugin.card([b.read_text(encoding="utf-8") for b in step.card_base], overrides,
                                      {"point": plan.point.name, "tag": step.tag, "output_name": output_name,
                                       "output": str(step.outputs[0].path) if step.outputs else "",
                                       "base_paths": [str(b) for b in step.card_base]})
            step.card_lines = [header, *text.rstrip("\n").splitlines(), *footer]
        step.card_combined = plan.out / "cards" / f"{step.tag}.{ext}"
        step.identity_parts["base_sha256"] = [sha256_file(b) for b in step.card_base]
        step.identity_parts["card"] = [line for line in step.card_lines if line not in redundant]
        _prepare_key(plan, step, run)
    elif style == "prepend":
        raise HepError(f"card style '{style}' arrives with the {folder.name} tool folder (P4 S3)", where=folder.name)
    elif lines:
        raise HepError(f"{folder.name} has no card, but quantities set native keys on it: {', '.join(lines)}",
                       where=f"[tools.{step.tag}]", hint="target an option or a config key instead")

    # analysis-style tools (rivet): analyses with their options
    if "analyses" in tool.extra:
        common = {k: native(v, ["1", "0"]) for k, v in tool.extra.get("options", {}).items()}
        rendered = []
        for analysis in tool.extra["analyses"]:
            base, *inline = analysis.split(":")
            merged = dict(item.partition("=")[::2] for item in inline)
            merged.update(common)
            merged.update(options.get(base, {}))
            rendered.append(":".join([base, *(f"{k}={v}" for k, v in sorted(merged.items()))]))
        unknown = set(options) - {a.split(":")[0] for a in tool.extra["analyses"]}
        if unknown:
            raise HepError(f"options target analyses not run by {step.tag}: {', '.join(sorted(unknown))}",
                           where=f"[tools.{step.tag}]")
        _check_declared_options(step, rendered)
        step.identity_parts["analyses"] = rendered
        step.config_data = {"analyses": rendered}
        for pattern in folder.get("identity", "files", []):
            for analysis in rendered:
                path = Path(expand(pattern, {"repo": str(repo_root()), "exe": str(step.exe),
                                             "analysis": analysis.split(":")[0]}, folder.name))
                if path.is_file():
                    step.identity_parts.setdefault("files_sha256", {})[str(path)] = sha256_file(path)
    step.identity_parts["_flags"] = flags


def _prepare_key(plan: PointPlan, step: Step, run) -> None:
    """[prepare]: a cache entry per card, output/<P>/.cache/<tool>/<key>/. The key is the card before
    seeds, the base cards and the binary, without the lines setting `ignore` keys (the event count,
    say), so every point, replica and rerun with the same physics shares one integration."""
    spec = step.folder.spec.get("prepare")
    if not spec:
        return
    comment = step.folder.get("card", "comment", "#")
    ignore = spec.get("ignore", [])
    if spec.get("key", "card") == "base":        # what is built depends on the base card only (MadGraph)
        step.card_lines_for_key = []
    else:
        step.card_lines_for_key = step.card_lines
    pattern = re.compile(r"\s*(?:set\s+)?(" + "|".join(map(re.escape, ignore)) + r")\s*[:=\s]") if ignore else None
    keyed = [line for line in step.card_lines_for_key
             if not line.startswith(comment) and not (pattern and pattern.match(line))]
    text = "\n".join([step.folder.name, step.identity_parts.get("exe_sha256", str(step.exe)),
                      *step.identity_parts["base_sha256"], *keyed])
    step.prepare_dir = output_root() / run.project / ".cache" / step.folder.name / hashlib.sha256(text.encode()).hexdigest()[:16]
    step.identity_parts["prepare"] = step.prepare_dir.name
    if step.folder.card_style == "render" and hasattr(step.folder.plugin, "prepare_card"):
        ext = step.folder.get("card", "ext", "txt")
        step.prepare_card = plan.out / "cards" / f"{step.tag}.prepare.{ext}"


def _prepare_argv(plan: PointPlan, step: Step) -> None:
    """The prepare command, run in the cache entry: for chain steps and export-only ones alike."""
    if step.prepare_dir is None:
        return
    context = {"repo": str(repo_root()), "exe": str(step.exe), "card": str(step.card_combined or ""),
               "prepared": str(step.prepare_dir), "out": str(plan.out),
               "prepare_card": str(step.prepare_card or step.card_combined or "")}
    argv = []
    for template in step.folder.spec["prepare"].get("argv", []):
        piece = expand(template, context, f"{step.folder.name}/tool.toml [prepare].argv")
        argv.extend(piece if isinstance(piece, list) else [piece] if piece != "" else [])
    step.prepare_argv = argv


def _base_values(tool, run, folder: Folder) -> dict[str, str]:
    """The base cards' `Key = value` settings (last wins), for spotting redundant overrides."""
    comment = folder.get("card", "comment", "#")
    values: dict[str, str] = {}
    for base in tool.baseconfig:
        path = resolve(base, "baseconfig", project=run.project, where=f"[tools.{tool.tag}].baseconfig")
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split(comment, 1)[0].strip()
            if "=" in line:
                key, _, value = line.partition("=")
                values["".join(key.split()).lower()] = value.strip()
    return values


def _same(a: str, b: str) -> bool:
    words = {"on": "1", "true": "1", "yes": "1", "off": "0", "false": "0", "no": "0"}
    a, b = words.get(a.lower(), a.lower()), words.get(b.lower(), b.lower())
    try:
        return float(a) == float(b)
    except ValueError:
        return a == b


def _info_dirs(folder: Folder) -> list[Path]:
    dirs = [Path(expand(d, {"repo": str(repo_root())}, folder.name)) for d in folder.get("checks", "info_dirs", [])]
    command = folder.get("checks", "info_dirs_command")
    if command:
        key = " ".join(command)
        if key not in _VERSIONS:
            try:
                _VERSIONS[key] = subprocess.run(command, capture_output=True, text=True, timeout=30).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                _VERSIONS[key] = ""
        dirs += [Path(d) for d in _VERSIONS[key].split(":") if d]
    return dirs


def _check_declared_options(step: Step, rendered: list[str]) -> None:
    """C9 (L19): each analysis has a .info, and every option it is given is declared there."""
    dirs = _info_dirs(step.folder)
    if not dirs:
        return
    for analysis in rendered:
        name, *options = analysis.split(":")
        info = next((d / f"{name}.info" for d in dirs if (d / f"{name}.info").is_file()), None)
        if info is None:
            raise HepError(f"no analysis '{name}' (no {name}.info)", where=f"[tools.{step.tag}].analyses",
                           hint=f"searched {', '.join(str(d) for d in dirs)}; a project plugin needs `hep build`")
        declared, inside = set(), False
        for raw in info.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"^Options:", raw):
                inside = True
                continue
            if inside:
                match = re.match(r"^\s*-\s*([A-Za-z0-9_]+)=", raw)
                if match:
                    declared.add(match.group(1))
                elif raw.strip() and not raw.startswith((" ", "\t", "-")):
                    break
        for option in options:
            key = option.split("=")[0]
            if key not in declared:
                raise HepError(f"'{name}' does not declare the option {key}", where=f"[tools.{step.tag}]",
                               hint=(f"declared: {', '.join(sorted(declared)) or 'none'} (in {info}). Rivet ignores "
                                     "an undeclared option silently, so the curves would be identical (L19)"))


def _argv(plan: PointPlan, step: Step, run, requests: dict[str, str]) -> None:
    folder, tool = step.folder, step.tool
    context: dict[str, Any] = {
        "repo": str(repo_root()), "out": str(plan.out), "res": str(plan.res), "exe": str(step.exe),
        "threads": plan.threads, "events": plan.events,
        "input": str(step.inputs[0].path) if step.inputs else "",
        "inputs": [str(p) for i in step.inputs for p in (i.paths if i.kind == "points" else [i.path])],
        "named_inputs": [f"{n}={p}" for i in step.inputs if i.kind == "points" for n, p in zip(i.names, i.paths)],
        "input_sidecar": _upstream_sidecar(plan, step),
        "output_name": step.outputs[0].path.name if step.outputs else "",
        "prepared": str(step.prepare_dir or ""),
        "seed": "{seed}",                      # filled in by finalise: seeds derive from the identity
        "output": str(step.outputs[0].path) if step.outputs else "",
        "outputs": _outputs_argument(step, plan.deal),
        "partial:": {"output": str(step.products[0][1]) if step.products else ""},
        "in:": {i.name: str(i.path) for i in step.inputs},
        "file:": {name: str(i.path) for name, i in plan.interfaces.items() if i.kind in ("fifo", "file")},
        "q:": {name: str(run.quantities[name].values[i]) for name, i in plan.values.items()},
        "cards": [str(p) for p in step.card_base] + ([str(step.card_point)] if step.card_point else []),
        "card": str(step.card_combined or ""),
        "analyses": [x for a in step.identity_parts.get("analyses", []) for x in ("-a", a)],
        **plan.context,
    }
    # every option the tool folder declares is a placeholder too: its value, or empty when unset
    for key, rule in folder.spec.get("options", {}).items():
        if key in context:
            continue
        if rule.get("kind") == "flag":                 # { kind = "flag", flag = "-e", default = true }
            context[key] = [rule["flag"]] if tool.extra.get(key, rule.get("default", False)) else []
            continue
        value = tool.extra.get(key, [] if rule.get("kind") == "list" else "")
        context[key] = [str(v) for v in value] if isinstance(value, list) else str(value)
    # standard configurations handed to a custom/module tool (V21, 04 §9.4)
    standard: dict[str, dict] = {}
    for key, tag in requests.items():
        source = plan.rendered[tag]
        export = EXPORT.match(key).group("export")
        declared = source.folder.spec.get("exports", {}).get(export, {})
        if export == "card" or declared.get("alias") == "card":
            parts = [str(p) for p in source.card_base] + ([str(source.card_point)] if source.card_point else [])
            standard[key] = {"tool": source.tool.tool, "tag": tag, "path": str(source.card_combined), "parts": parts}
        else:
            values = {"tool": source.tool.tool, "tag": tag}
            if declared.get("needs_prepare"):          # prepare on demand (04 §9.4)
                if source.prepare_dir is None:
                    raise HepError(f"{source.folder.name} export '{export}' needs a prepare step the tool does not have",
                                   where=f"{source.folder.name}/tool.toml")
                source.prepare_needed = True
            if "path" in declared:
                values["path"] = expand(declared["path"], {"prepared": str(source.prepare_dir or ""),
                                                           "card": str(source.card_combined or "")},
                                        f"{source.folder.name}/tool.toml [exports.{export}]")
            for give in declared.get("gives", []):
                if give == "analyses":
                    values["analyses"] = source.identity_parts.get("analyses", [])
                elif give == "plugin_path":
                    values["plugin_path"] = str(repo_root() / "build" / "Rivet")
                else:
                    raise HepError(f"{source.folder.name} export '{export}' gives unknown '{give}'",
                                   where=f"{source.folder.name}/tool.toml")
            standard[key] = values
        step.identity_parts.setdefault("exports", {})[key] = plan.rendered[tag].identity_parts
    context["std:"] = {k: v.get("path", "") for k, v in standard.items()}

    if tool.tool in ("custom", "module"):
        data = dict(tool.config or {})
        consumed = {k: v for k, v in step.identity_parts.get("config_values", {}).items()}
        quantities_table = {k: v for k, v in consumed.items() if k in run.quantities}
        for key, value in consumed.items():
            if key not in run.quantities:
                target = data
                *head, last = key.split(".")
                for part in head:
                    target = target.setdefault(part, {})
                target[last] = value
        if quantities_table:
            data["quantities"] = quantities_table
        if standard:
            data["standard"] = standard
        if data or tool.config is not None or tool.tool == "module":   # a kit program always takes one
            step.config_path = plan.out / "config" / f"{step.tag}.toml"
            step.config_data = data
            step.identity_parts["config"] = tomli_w.dumps(data)
        context["config"] = str(step.config_path) if step.config_path else ""
        context["arguments"] = [expand(str(a), context, f"[tools.{step.tag}].arguments") for a in tool.arguments]
        context["arguments"] = [x for a in context["arguments"] for x in (a if isinstance(a, list) else [a])]

    argv: list[str] = []
    for template in folder.get("command", "argv", ["{exe}"]):
        piece = expand(template, context, f"{folder.name}/tool.toml [command].argv")
        if isinstance(piece, list):
            argv.extend(piece)
        elif piece != "":
            argv.append(piece)
    argv.extend(step.identity_parts.pop("_flags", []))
    step.argv = argv
    step.env = {k: expand(v, context, f"{folder.name}/tool.toml [command].env")
                for k, v in folder.get("command", "env", {}).items()}
    if folder.get("command", "cwd"):                  # Whizard generates where its library and grids are
        step.cwd = Path(expand(folder.get("command", "cwd"), context, f"{folder.name}/tool.toml [command].cwd"))
    if folder.get("outputs", "written") == "requested":
        step.sidecar_written = plan.events          # it always makes what it is asked for, or fails
    step.identity_parts["argv"] = [a.replace(str(plan.out), "{out}").replace(str(plan.res), "{res}") for a in argv]

    # the count check: a consumer of events reads its count back and compares it with the producer's sidecar
    consumes = tool.consumes_events if tool.consumes_events is not None else folder.get("tool", "consumes_events", False)
    reader = folder.get("outputs", "event_count")
    if consumes and reader and step.products and step.inputs:
        producer = plan.rendered.get(step.inputs[0].producer)
        if producer is not None and producer.sidecar is not None:
            key = str(step.inputs[0].path) if step.inputs[0].name in plan.deal else None   # a shard: its share
            step.count_check = (step.products[0][1], producer.sidecar, reader, key)


def _outputs_argument(step: Step, deal: dict[str, str]) -> str:
    """`{outputs}`: every output, comma-separated; the members of a deal group joined by `+`
    (App_Pythia sends each event to one member of a group, and to every group)."""
    items: list[str] = []
    at: dict[str, int] = {}
    for interface in step.outputs:
        if set(str(interface.path)) & {",", "+"}:
            raise HepError(f"an output path of [tools.{step.tag}] contains ',' or '+', which separate its outputs",
                           where=str(interface.path),
                           hint="rename what puts it there: the run's name or serial, a configuration, a quantity tag, "
                                "or $HEKIT_OUTPUT")
        group = deal.get(interface.name)
        if group is not None and group in at:
            items[at[group]] += "+" + str(interface.path)
            continue
        if group is not None:
            at[group] = len(items)
        items.append(str(interface.path))
    return ",".join(items)


def _upstream_sidecar(plan: PointPlan, step: Step) -> str:
    """The first input's producer sidecar, when it is written before this step starts: a file from
    an earlier group. In one group (a FIFO) it appears only after the stream ends."""
    if not step.inputs or not step.inputs[0].producer:
        return ""
    producer = plan.rendered.get(step.inputs[0].producer)
    if producer is None or producer.sidecar is None or producer.group >= step.group:
        return ""
    return str(producer.sidecar)


def finalise(plan: PointPlan, seed: int) -> None:
    """Write the seed lines into every generator card, and collect the files to write."""
    plan.seed = seed
    seeds = [seed + i for i in range(plan.threads)]
    for step in plan.rendered.values():
        step.argv = [a.replace("{seed}", str(seed)) for a in step.argv]
        if step.card_combined is None:
            continue
        prepared = str(step.prepare_dir or "")
        lines = [line.replace("{seed}", str(seed)).replace("{prepared}", prepared) for line in step.card_lines]
        seed_lines = step.folder.get("card", "seed", [])
        if seed_lines:
            context = {"seed": seed, "seeds": seeds}
            lines += [expand(line, context, step.folder.name) for line in seed_lines]
            if plan.threads > 1:
                lines += [expand(line, context, step.folder.name) for line in step.folder.get("card", "seed_parallel", [])]
        point_text = "\n".join(lines) + "\n"
        if step.card_point is None:                # style "render": the card is whole already
            plan.writes[step.card_combined] = point_text
            if step.prepare_card is not None:
                plan.writes[step.prepare_card] = step.folder.plugin.prepare_card(
                    lines, [b.read_text(encoding="utf-8") for b in step.card_base],
                    {"prepared": prepared, "base_paths": [str(b) for b in step.card_base], "tag": step.tag})
            continue
        combined = "".join(b.read_text(encoding="utf-8") for b in step.card_base) + "\n" + point_text
        plan.writes[step.card_point] = point_text
        plan.writes[step.card_combined] = combined
    for step in plan.rendered.values():
        if step.config_path is not None:
            plan.writes[step.config_path] = tomli_w.dumps(step.config_data or {})


def _unsharded(tag: str, plan: PointPlan) -> str:
    """rivet.3 → rivet.1–10 in --plan, where a quantity reaches every shard alike."""
    head, _, index = tag.rpartition(".")
    count = sum(1 for group in plan.groups for s in group if s.tag.rpartition(".")[0] == head
                and s.tag.rpartition(".")[2].isdigit())
    return f"{head}.1–{count}" if head and index.isdigit() and f"{head}.merge" in plan.rendered else tag


def describe(plan: PointPlan, run) -> list[str]:
    """--plan: the groups, argv, connections and files of one point."""
    drawn = "  (random: drawn again by each run)" if plan.seed_type == "random" and not plan.seed_kept else ""
    lines = [f"point {plan.point.index} {plan.point.name}   identity {plan.identity[:12]}   seed {plan.seed}{drawn}"]
    for name, index in plan.values.items():
        quantity = run.quantities[name]
        where = ", ".join(dict.fromkeys(f"{_unsharded(m.tag, plan)}:{m.key if m.form != 'seed' else 'seed'}"
                                        for m in plan.consumers.get(name, [])))
        lines.append(f"  {name:12s} = {tag_of(quantity, index):14s} → {where}")
    for g, group in enumerate(plan.groups, start=1):
        lines.append(f"  group {g}: {', '.join(s.tag for s in group)}")
        for step in group:
            lines.append(f"    {step.tag}: {' '.join(step.argv)}")
            for interface in step.inputs:
                where = (f"{interface.name} of {len(interface.paths)} point(s)" if interface.kind == "points"
                         else interface.path)
                lines.append(f"      reads  {interface.kind:7s} {where}")
            for interface in step.outputs:
                lines.append(f"      writes {interface.kind:7s} {interface.path}")
    for step in plan.rendered.values():
        if step.prepare_dir is not None and step.prepare_needed:
            state = "cached" if (step.prepare_dir / ".prepared").exists() else "to run"
            lines.append(f"  prepare {step.tag}: {' '.join(step.prepare_argv)}")
            lines.append(f"    in {step.prepare_dir}   ({state})")
    export_only = [t for t, s in plan.rendered.items() if s.group < 0]
    if export_only:
        lines.append(f"  configured, not run (exported): {', '.join(export_only)}")
    return lines
