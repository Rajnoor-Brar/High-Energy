"""Quantities: the master TOML, static values, and who consumes what (rank 1).

docs/04_Config_Reference.md §3 and §8. A quantity renders nothing by itself. It reaches a tool
through a mapping:
  * from the master TOML, by tool type: [quantities.<tool>.compatible_quantities].<q>;
  * or from the quantity's own `key` table ({<tag or tool> = key});
  * or explicitly through `target` = "<tag>", "<tag>/<analysis>" (a Rivet analysis option) or
    "<tag>/seed" (a replica: it only changes the seed).

A quantity that is active (swept, or given a static value) and reaches no tool is an error (rule
C7), because a value that changes a directory name and nothing else is the silent failure v1 kept
finding (00/B14, 00/B40).
"""

from __future__ import annotations

import copy
import functools
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

from .errors import HepError, did_you_mean
from .paths import repo_root, resolve

@functools.cache
def vocabulary() -> dict:
    """utils/Env/quantities.toml: what each quantity name means, for every tool (V58)."""
    path = repo_root() / "utils" / "Env" / "quantities.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise HepError(f"cannot read the quantity vocabulary: {error}", where=str(path)) from None


#: The built-in quantities: the runner provides them, and they need no consumer (04 §8.3).
BUILTIN = tuple(name for name, entry in vocabulary().items() if entry.get("builtin"))


class Override(NamedTuple):
    """One value a tool receives, and who asked. A NamedTuple, so it unpacks either way (L26)."""
    key: str
    value: Any
    origin: str


@dataclass(frozen=True)
class Mapping:
    """How one quantity reaches one tool."""
    tag: str
    form: str            # key | keys | flag | render | config | option | seed
    key: Any = None      # the native key(s), flag, render function, config key or option name
    format: str = ""
    analysis: str = ""   # for form = option
    check: str = ""      # a provider check on the value (C10), e.g. "lhapdf"


def _read(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise HepError(f"not valid TOML: {error}", where=str(path)) from None


@functools.cache
def _folders_master() -> dict:
    """Every tool folder's quantities.toml, as one master: {quantities: {<tool>: {compatible_quantities}}}.
    A folder maps only names the vocabulary has (V58)."""
    master: dict = {"quantities": {}}
    known = vocabulary()
    for path in sorted((repo_root() / "utils" / "Env").glob("*/quantities.toml")):
        table = _read(path)
        unknown = [name for name in table if name not in known]
        if unknown:
            raise HepError(f"{path.parent.name} maps {', '.join(unknown)}, which the vocabulary does not have",
                           where=str(path), hint="add it to utils/Env/quantities.toml, with its shape")
        master["quantities"][path.parent.name] = {"compatible_quantities": table}
    return master


def load_master(project: str, master_toml: str | None) -> dict:
    """The tool folders' mappings (utils/Env/<tool>/quantities.toml), overlaid key by key by the project's
    master if [master].master_toml names one ([quantities.<tool>.compatible_quantities], as before)."""
    master = copy.deepcopy(_folders_master())
    read = _read
    if master_toml:
        overlay_path = resolve(master_toml, "master", project=project, where="[master].master_toml")
        if not overlay_path.exists():
            raise HepError("the project master TOML does not exist", where=str(overlay_path))
        overlay = read(overlay_path)
        for tool, table in overlay.get("quantities", {}).items():
            target = master.setdefault("quantities", {}).setdefault(tool, {}).setdefault("compatible_quantities", {})
            target.update(table.get("compatible_quantities", {}))
    return master


def compatible(master: dict, tool_type: str) -> dict:
    return master.get("quantities", {}).get(tool_type, {}).get("compatible_quantities", {})


def select(quantity, selector: Any, where: str) -> int:
    """A static value or --points selector → a value index: a tag, then an exact value, then #N."""
    if isinstance(selector, str):
        if selector in quantity.tags:
            return quantity.tags.index(selector)
        if selector.startswith("#") and selector[1:].isdigit():
            index = int(selector[1:]) - 1
            if 0 <= index < len(quantity.values):
                return index
            raise HepError(f"{selector} is outside 1..{len(quantity.values)}", where=where)
    for index, value in enumerate(quantity.values):
        if value == selector or (isinstance(value, (int, float)) and isinstance(selector, (int, float))
                                 and not isinstance(value, bool) and float(value) == float(selector)):
            return index
    choices = quantity.tags or [str(v) for v in quantity.values]
    raise HepError(f"'{selector}' is not a value of [quantities.{quantity.name}]", where=where,
                   hint=did_you_mean(str(selector), choices) or f"tags: {', '.join(choices)}")


def static_values(run, configuration) -> dict[str, int]:
    """quantity → value index for every static value (file-wide, then the configuration's own)."""
    out = {}
    for name, selector in configuration.static.items():
        out[name] = select(run.quantities[name], selector, f"{run.path}: static.{name}")
    return out


def mappings(run, master: dict, name: str, tags: list[str], configured: set = frozenset()) -> list[Mapping]:
    """Every way quantity `name` reaches the tools `tags` of this configuration. `configured`: the tags whose
    folder writes a config file ([tool] config_file: custom, module), where a target lands as a config key."""
    quantity = run.quantities[name]
    out: list[Mapping] = []
    if quantity.target:
        for target in quantity.target:
            tag, _, rest = target.partition("/")
            if tag not in run.tools:
                raise HepError(f"target '{target}' names no tool table", where=f"{run.path}: [quantities.{name}].target",
                               hint=did_you_mean(tag, run.tools))
            if tag not in tags:
                continue
            tool = run.tools[tag]
            key = quantity.key.get(tag, quantity.key.get(tool.tool)) if isinstance(quantity.key, dict) else quantity.key
            if rest == "seed":
                out.append(Mapping(tag, "seed"))
            elif rest:
                if not key:
                    raise HepError(f"target '{target}' is an analysis option: give its name in key",
                                   where=f"{run.path}: [quantities.{name}]")
                out.append(Mapping(tag, "option", key, quantity.format, analysis=rest))
            elif tag in configured:
                out.append(Mapping(tag, "config", key or name, quantity.format))
            elif key:
                out.append(Mapping(tag, "key", key, quantity.format))
            elif name in compatible(master, tool.tool):
                out.append(_from_master(tag, compatible(master, tool.tool)[name], f"master: {tool.tool}.{name}"))
            else:
                raise HepError(f"target '{target}': no key, and the master has no mapping of '{name}' for {tool.tool}",
                               where=f"{run.path}: [quantities.{name}]", hint="give key = \"<native key>\"")
        return out
    if isinstance(quantity.key, str):
        raise HepError("a string key needs a target", where=f"{run.path}: [quantities.{name}].key",
                       hint="write key = { <tool or tag> = \"...\" }, or add target = \"<tag>\"")
    for tag in tags:
        tool = run.tools[tag]
        if isinstance(quantity.key, dict) and (tag in quantity.key or tool.tool in quantity.key):
            out.append(Mapping(tag, "key", quantity.key.get(tag, quantity.key.get(tool.tool)), quantity.format))
        elif name in compatible(master, tool.tool):
            out.append(_from_master(tag, compatible(master, tool.tool)[name], f"master: {tool.tool}.{name}"))
        elif name in tool.consumes:
            out.append(Mapping(tag, "config", name, quantity.format))
    return out


def _from_master(tag: str, entry: dict, where: str) -> Mapping:
    forms = [f for f in ("key", "keys", "flag", "render") if f in entry]
    if len(forms) != 1:
        raise HepError("a master mapping takes exactly one of key, keys, flag, render", where=where)
    return Mapping(tag, forms[0], entry[forms[0]], entry.get("format", ""), check=entry.get("check", ""))


def builtin_mappings(master: dict, run, tags: list[str], name: str) -> list[Mapping]:
    """events/threads reach a tool only through the master (they need no consumer)."""
    return [_from_master(tag, compatible(master, run.tools[tag].tool)[name], f"master: {run.tools[tag].tool}.{name}")
            for tag in tags if name in compatible(master, run.tools[tag].tool)]


def consumer_table(run, master: dict, active: list[str], tags: list[str],
                   alternatives: list[str] = (), configured: set = frozenset()) -> dict[str, list[Mapping]]:
    """quantity → mappings, and rule C7: an active quantity must reach at least one tool.

    In a chain that chooses a tool by a quantity (`"@generator"`, V19), a value that only another
    alternative consumes (Sherpa's BEAMS, say, on a Herwig point) is accepted with no mapping here:
    it reaches a tool in this configuration, just not in this point's chain."""
    table = {}
    for name in active:
        found = mappings(run, master, name, tags, configured)
        if not found and alternatives and mappings(run, master, name, list(alternatives), configured):
            table[name] = []
            continue
        if not found:
            raise HepError(f"[quantities.{name}] is set but no tool in this chain consumes it",
                           where=f"{run.path}: [quantities.{name}]",
                           hint=f"tools here: {', '.join(tags)}. Give it a target, a key = {{tool = ...}}, "
                                "a master mapping, or drop it: a value that changes nothing is refused (C7)")
        table[name] = found
    return table


# ── shapes: a vocabulary quantity's values (V58) ─────────────────────────────────────────────

def _fits(value, shape) -> bool:
    if isinstance(shape, list):
        return isinstance(value, list) and len(value) == len(shape) and all(_fits(v, s) for v, s in zip(value, shape))
    for kind in shape.split("|"):
        if isinstance(value, bool):
            if kind == "bool":
                return True
            continue
        if kind == "float" and isinstance(value, (int, float)):
            return True
        if kind == "int" and isinstance(value, int):
            return True
        if kind == "pdg" and isinstance(value, int) and value != 0:
            return True
        if kind == "str" and isinstance(value, str):
            return True
    return False


def _shape_text(shape) -> str:
    names = {"float": "a number", "int": "an integer", "pdg": "a PDG id", "str": "a string", "bool": "true or false"}
    if isinstance(shape, list):
        return f"a list of {len(shape)}: [{', '.join(_shape_text(s) for s in shape)}]"
    return " or ".join(names[k] for k in shape.split("|"))


def check_shapes(quantity, where: str) -> None:
    """A quantity the vocabulary names takes values of its shape (V58): `energies = [[275, 18]]`, not
    `[275, 18]` or `[[275]]`. A quantity it does not name is the user's own, unchecked."""
    entry = vocabulary().get(quantity.name)
    if entry is None:
        return
    for place, value in enumerate(quantity.values, start=1):
        if not _fits(value, entry["shape"]):
            unit = f" in {entry['unit']}" if entry.get("unit") else ""
            raise HepError(f"[quantities.{quantity.name}] value {place} is {value!r}, not {_shape_text(entry['shape'])}{unit}",
                           where=where, hint=entry.get("doc", ""))


# ── providers: things a value needs installed (02 §4, category 1) ─────────────────────────────

@functools.cache
def _provider(name: str):
    """utils/Env/<name>/provider.py (V60): a provider's checks, loaded by name."""
    import importlib.util
    path = repo_root() / "utils" / "Env" / name / "provider.py"
    if not path.is_file():
        raise HepError(f"no provider '{name}'", hint=f"expected {path}")
    spec = importlib.util.spec_from_file_location(f"hep_provider_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_provider(kind: str, value, where: str) -> None:
    """Refuse at plan time a value whose provider is missing (C10): `check = "<provider>:<form>"` in a tool
    folder's quantities.toml, e.g. "lhapdf:pythia" (utils/Env/lhapdf/provider.py)."""
    provider, _, form = kind.partition(":")
    if not form:
        raise HepError(f"a provider check is '<provider>:<form>', not '{kind}'", where=where)
    _provider(provider).check(form, value, where)
