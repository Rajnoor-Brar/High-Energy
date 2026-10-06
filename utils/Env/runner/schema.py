"""The run TOML's schema: utils/Env/schema/run.toml, and checking a table against it (rank 0).

docs/04_Config_Reference.md. Every key's type, allowed values, smallest value, default, inheritance and
whether it takes "default" is written once, in run.toml (V55); config.py and plot.py check their tables
here, and the editor schema (`make schema`) and the reference's key lists come from the same file.

"default" means "keep it as it is": in a child it is the parent's value, at the top level nothing is set
and the tool decides. Only a key whose entry says `default_ok` takes it.
"""

from __future__ import annotations

import functools
import json
import tomllib
from pathlib import Path
from typing import Any

from .errors import HepError, did_you_mean
from .paths import repo_root

DEFAULT = "default"
TYPES = {"int": int, "float": (int, float), "str": str, "bool": bool, "list": list, "table": dict}
NAMES = {"int": "an integer", "float": "a number", "str": "a string", "bool": "true or false", "list": "a list",
         "table": "a table"}
#: The tables of run.toml that describe keys (the rest, [sections], describe the file).
TABLES = ("config", "run", "configuration", "prelim", "quantity", "tool", "plot", "figure", "data")
#: A figure's own keys: the rest are what it sets for its pages.
FIGURE_OWN = ("class", "type", "name", "objects", "labels", "over", "configurations", "op", "x", "y", "pages", "columns")


def path() -> Path:
    return repo_root() / "utils" / "Env" / "schema" / "run.toml"


@functools.cache
def spec() -> dict:
    try:
        return tomllib.loads(path().read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise HepError(f"cannot read the schema: {error}", where=str(path())) from None


def keys(table: str) -> dict[str, dict]:
    """The keys of one schema table: name → its entry. A figure's are every [plot] key marked `page`, as
    a child has them ("default" is [plot]'s value; no default of its own), then its own."""
    if table == "figure":
        inherited = {k: {f: v for f, v in e.items() if f not in ("default", "page")} | {"default_ok": True,
                         "doc": f"as [plot].{k}, for these pages"}
                     for k, e in spec().get("plot", {}).items() if e.get("page")}
        return inherited | spec().get(table, {})
    return spec().get(table, {})


def sections() -> tuple[str, ...]:
    return tuple(spec()["sections"]["order"])


def default(table: str, key: str, fallback: Any = None) -> Any:
    return keys(table).get(key, {}).get("default", fallback)


def type_name(kinds: str) -> str:
    return " or ".join(NAMES[k] for k in kinds.split("|"))


def _is(value, kinds: str) -> bool:
    for kind in kinds.split("|"):
        if isinstance(value, bool) and kind != "bool":
            continue                                       # true is not an integer here
        if isinstance(value, TYPES[kind]):
            return True
    return False


def check(values: dict, table: str, where: str, *, subtables: bool = False, extra: bool = False,
          only: tuple[str, ...] = ()) -> dict:
    """Unknown keys are errors (C1) and known keys have their type, choices and bounds. Returns the keys
    the schema does not know when `extra` (a tool's folder options); `subtables` lets a table-valued key
    the schema does not know through (a configuration inside [run]); `only` restricts the known keys."""
    known = {k: v for k, v in keys(table).items() if not only or k in only}
    extras = {}
    for key, value in values.items():
        entry = known.get(key)
        if entry is None:
            if subtables and isinstance(value, dict):
                continue
            if extra:
                extras[key] = value
                continue
            raise HepError(f"unknown key '{key}'", where=where,
                           hint=did_you_mean(key, known) or f"known keys: {', '.join(known)}")
        if subtables and isinstance(value, dict) and "table" not in entry["type"].split("|"):
            continue                                       # a configuration named like a key ([run.threads])
        check_value(key, value, entry, f"{where}.{key}" if not where.endswith("]") else f"{where}.{key}")
    return extras


def check_value(key: str, value, entry: dict, where: str) -> None:
    kinds = entry["type"]
    if value == DEFAULT and entry.get("default_ok"):
        return
    if value == DEFAULT and "str" not in kinds.split("|"):
        raise HepError(f"'{key}' does not take \"default\"", where=where,
                       hint=f"give it {type_name(kinds)}, or leave it out")
    if not _is(value, kinds):
        if isinstance(value, bool):
            raise HepError(f"'{key}' must be {type_name(kinds)}, not true/false", where=where)
        raise HepError(f"'{key}' must be {type_name(kinds)}", where=where, hint=f"got {value!r}")
    items = entry.get("items")
    members = value if isinstance(value, list) else [value]
    if items and isinstance(value, list):
        for item in value:
            if not _is(item, items):
                raise HepError(f"'{key}' entries must be {type_name(items)}", where=where, hint=f"got {item!r}")
    choices = entry.get("choices")
    if choices:
        for item in members:                     # a choice may be false (normalise = "area" | false, V68)
            if isinstance(item, (str, bool)) and not any(type(item) is type(c) and item == c for c in choices):
                shown = ", ".join(c if isinstance(c, str) else str(c).lower() for c in choices)
                raise HepError(f"{key} must be one of {shown}, not {item!r}", where=where,
                               hint=did_you_mean(item, [c for c in choices if isinstance(c, str)]) if isinstance(item, str) else None)
    if "min" in entry and _is(value, "float") and value < entry["min"]:
        raise HepError(f"'{key}' must be at least {entry['min']}", where=where, hint=f"got {value!r}")


# ── the editor schema (F6) ───────────────────────────────────────────────────────────────────

def _json_type(kinds: str) -> list[str]:
    return [{"int": "integer", "float": "number", "str": "string", "bool": "boolean", "list": "array",
             "table": "object"}[k] for k in kinds.split("|")]


def _json_key(entry: dict) -> dict:
    out: dict = {"description": "\n\n".join(t for t in (entry.get("doc", ""), entry.get("notes", "")) if t)}
    types = _json_type(entry["type"])
    one = {"type": types if len(types) > 1 else types[0]}
    if "min" in entry:
        one["minimum"] = entry["min"]
    if entry.get("choices") and "array" not in types:
        one["enum"] = entry["choices"]
    if entry.get("items"):
        one["items"] = {"type": _json_type(entry["items"])[0], **({"enum": entry["choices"]} if entry.get("choices") else {})}
    out.update(one if not entry.get("default_ok") else {"anyOf": [one, {"const": DEFAULT}]})
    if "default" in entry:
        out["default"] = entry["default"]
    return out


def _object(table: str, open_: bool = False) -> dict:
    properties = {k: _json_key(v) for k, v in keys(table).items()}
    required = [k for k, v in keys(table).items() if v.get("required")]
    return {"type": "object", "properties": properties, **({"required": required} if required else {}),
            "additionalProperties": open_}


def json_schema() -> dict:
    """run.schema.json: the run TOML for an editor (Even Better TOML / Taplo, `#:schema` or settings)."""
    configuration = _object("configuration")
    run = _object("run")
    run["properties"]["cfgs"] = {"type": "object", "additionalProperties": configuration}   # [run.cfgs.<cfg>] (V98)
    run["properties"]["defaults"] = configuration
    figure = _object("figure")
    plot = _object("plot")
    plot["properties"]["figures"] = {"type": "object", "additionalProperties": figure}
    plot["properties"]["data"] = _object("data")
    plot["properties"]["data"]["properties"]["map"] = {"type": "object", "additionalProperties": {"type": "string"}}
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "hep run TOML (generated from utils/Env/schema/run.toml)",
        "type": "object",
        "properties": {
            "config": _object("config"), "run": run, "prelim": _object("prelim"),
            "static": {"type": "object", "description": "quantity = a tag, a value or \"#N\""},
            "tools": {"type": "object", "additionalProperties": _object("tool", open_=True)},
            "quantities": {"type": "object", "additionalProperties": _object("quantity")},
            "plot": plot,
        },
        "required": ["run"],
        "additionalProperties": False,
    }


def write_json_schema(target: Path | None = None) -> Path:
    target = target or path().with_name("run.schema.json")
    target.write_text(json.dumps(json_schema(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":                                  # make schema
    print(write_json_schema())
