"""Reading, layering and validating a run TOML (03 §1–2, §6).

Order of work:
1. every file is read with `tomllib` and scanned separately for line numbers (`tomllib` does not report
   them), so each value can name where it came from;
2. the layers are flattened to leaf paths and merged in precedence order — tables merge deeply, arrays
   and scalars replace;
3. every leaf is checked against its `Field`, and unknown keys are errors with a did-you-mean hint;
4. the section dataclasses are built.

Sweep semantics (static, studies, pins, expansion) are not here: they act on the loaded config in P1-S03.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any

from ..errors import HepError, did_you_mean
from . import schema as sch
from .fields import Field, check, check_scalar

#: `[table]` or `[[array]]` header
HEADER = re.compile(r"^\s*(\[\[?)\s*([^\]]+?)\s*\]\]?\s*(?:#.*)?$")
#: `key = …`, bare or quoted
ASSIGN = re.compile(r"""^\s*((?:[A-Za-z0-9_.-]+|"[^"]*"|'[^']*'))\s*=""")

MACHINE_FILE = Path.home() / ".config" / "hekit" / "machine.toml"

Path_ = tuple[str, ...]


def _split_key(raw: str) -> Path_:
    """`a."b.c".d` → ("a", "b.c", "d")"""
    parts: list[str] = []
    for piece in re.findall(r'"[^"]*"|\'[^\']*\'|[^.]+', raw):
        piece = piece.strip()
        if piece[:1] in {'"', "'"} and piece[:1] == piece[-1:]:
            parts.append(piece[1:-1])
        else:
            parts.append(piece)
    return tuple(part for part in parts if part)


def scan_origins(text: str, label: str) -> dict[Path_, str]:
    """key path → "label:line" for every assignment in a TOML text.

    A line scanner, not a parser: it follows table headers and records the line of each key's own
    assignment. That is what an error message or `--explain` needs; the values themselves come from
    `tomllib`. Repeated `[[array]]` headers index from 1.
    """
    origins: dict[Path_, str] = {}
    prefix: Path_ = ()
    array_counts: dict[Path_, int] = {}
    in_multiline = False
    quote = ""
    for number, line in enumerate(text.splitlines(), start=1):
        if in_multiline:
            if quote in line:
                in_multiline = False
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        header = HEADER.match(line)
        if header is not None:
            path = _split_key(header.group(2))
            if header.group(1) == "[[":
                array_counts[path] = array_counts.get(path, 0) + 1
                prefix = path + (str(array_counts[path]),)
            else:
                prefix = path
            origins.setdefault(prefix, f"{label}:{number}")
            continue
        assign = ASSIGN.match(line)
        if assign is not None:
            origins[prefix + _split_key(assign.group(1))] = f"{label}:{number}"
        for mark in ('"""', "'''"):
            if line.count(mark) == 1:
                in_multiline, quote = True, mark
    return origins


def is_single_value(path: Path_) -> bool:
    """True when the schema says this path holds one value, so an inline table must stay whole.

    `[quantity.pdf].key = { pythia = "PDF:pSet" }` is one value; `[rivet].options` and `[static.gen]`
    are free tables whose keys layer independently, so those are descended into.
    """
    section, inside = sch.section_of(path)
    if section is None or not inside:
        return False
    spec = section.field(inside[0])
    if spec is None or len(inside) != 1:
        return False
    return not spec.free


def flatten(data: Any, prefix: Path_ = ()) -> dict[Path_, Any]:
    """Tables become leaf paths; lists and single-value fields stay whole, because they replace."""
    flat: dict[Path_, Any] = {}
    for key, value in data.items():
        path = prefix + (str(key),)
        if isinstance(value, dict) and not is_single_value(path):
            nested = flatten(value, path)
            flat.update(nested or {path: {}})
        else:
            flat[path] = value
    return flat


@dataclass
class Layer:
    """One source of values: the built-in defaults, the machine file, an extends file, the file, the CLI."""

    name: str
    values: dict[Path_, Any]
    origins: dict[Path_, str]


@dataclass
class Resolved:
    """The merged values with, for every path, the chain of layers that set it."""

    values: dict[Path_, Any] = dataclass_field(default_factory=dict)
    origins: dict[Path_, str] = dataclass_field(default_factory=dict)
    chains: dict[Path_, list[tuple[str, str, Any]]] = dataclass_field(default_factory=dict)

    def apply(self, layer: Layer) -> None:
        for path, value in layer.values.items():
            origin = layer.origins.get(path, layer.name)
            self.values[path] = value
            self.origins[path] = origin
            self.chains.setdefault(path, []).append((layer.name, origin, value))

    def explain(self, dotted: str) -> list[tuple[str, str, Any]]:
        """Every layer that set a key, oldest first — what `hep plan --explain` prints."""
        path = _split_key(dotted)
        if path not in self.chains:
            known = [".".join(item) for item in sorted(self.chains)]
            raise HepError(f"no value for '{dotted}'", hint=did_you_mean(dotted, known) or "see hep config reference")
        return self.chains[path]


def read_file(path: Path, *, label: str | None = None) -> Layer:
    """One TOML file as a layer."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HepError(f"configuration file not found: {path}") from None
    except OSError as error:
        raise HepError(f"cannot read {path}: {error.strerror}") from None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise HepError(f"invalid TOML: {error}", where=str(path)) from None
    name = label or str(path)
    return Layer(name, flatten(data), scan_origins(text, name))


def defaults_layer() -> Layer:
    """The built-in defaults, so that every key has a value and an origin."""
    values: dict[Path_, Any] = {}
    for name, section in sch.SECTIONS.items():
        if section.shape != "table":
            continue
        for key, spec in section.fields.items():
            values[_split_key(name) + (key,)] = spec.default_value()
        for sub_name, subsection in section.subsections.items():
            for key, spec in subsection.fields.items():
                values[_split_key(name) + (sub_name, key)] = spec.default_value()
    for key, spec in sch.TOP_LEVEL.items():
        if key != "schema":
            values[(key,)] = spec.default_value()
    return Layer("default", values, {})


def machine_layer(path: Path | None) -> Layer | None:
    """The machine file, restricted to the allow-listed keys (03 §2)."""
    if path is None or not path.is_file():
        return None
    layer = read_file(path, label=str(path))
    for key_path in layer.values:
        section, inside = sch.section_of(key_path)
        allowed = section.machine_keys if section else ()
        if section is None or not inside or ".".join(inside) not in allowed:
            raise HepError(
                f"a machine file may not set '{'.'.join(key_path)}'",
                where=layer.origins.get(key_path, str(path)),
                hint="machine files may only set: "
                     + ", ".join(f"{name}.{key}" for name in sch.MACHINE_SECTIONS
                                 for key in sch.SECTIONS[name].machine_keys))
    return layer


def extends_layers(path: Path, seen: list[Path] | None = None) -> list[Layer]:
    """The `extends` chain of one file, left to right, depth first; cycles are an error."""
    seen = list(seen or [])
    resolved = path.resolve()
    if resolved in seen:
        chain = " → ".join(str(item) for item in [*seen, resolved])
        raise HepError("extends forms a cycle", where=str(path), hint=chain)
    seen.append(resolved)
    layer = read_file(path)
    layers: list[Layer] = []
    for entry in layer.values.get(("extends",), []) or []:
        if not isinstance(entry, str):
            raise HepError("extends entries must be file paths", where=layer.origins.get(("extends",), str(path)))
        parent = (path.parent / entry).resolve()
        layers.extend(extends_layers(parent, seen))
    layers.append(layer)
    return layers


def set_layer(assignments: tuple[str, ...]) -> Layer:
    """`--set key=value`, parsed as TOML so that types survive (03 §2)."""
    values: dict[Path_, Any] = {}
    origins: dict[Path_, str] = {}
    for assignment in assignments:
        key, separator, raw = assignment.partition("=")
        if not separator or not key.strip():
            raise HepError(f"--set expects key=value, got {assignment!r}",
                           hint="for example --set run.threads=4")
        try:
            parsed = tomllib.loads(f"value = {raw.strip()}")["value"]
        except tomllib.TOMLDecodeError:
            parsed = raw.strip()            # a bare word is a string
        path = _split_key(key.strip())
        values[path] = parsed
        origins[path] = "cli"
    return Layer("cli", values, origins)


# ── validation ───────────────────────────────────────────────────────────────

def _known_keys(section: sch.Section) -> list[str]:
    return sorted(section.fields) + sorted(section.subsections)


def resolve_field(path: Path_, where: str) -> tuple[Field, str]:
    """The field a leaf path belongs to, and the label to use in messages.

    Raises for an unknown section, an unknown key, or nesting inside a key that is not a free table.
    """
    if len(path) == 1:
        spec = sch.TOP_LEVEL.get(path[0])
        if spec is None:
            if path[0] in sch.SECTIONS:
                raise HepError(f"[{path[0]}] must be a table", where=where)
            raise HepError(f"unknown key '{path[0]}'", where=where,
                           hint=did_you_mean(path[0], [*sch.TOP_LEVEL, *sch.SECTIONS]))
        return spec, f"[{path[0]}]" if False else path[0]

    section, inside = sch.section_of(path)
    if section is None:
        raise HepError(f"unknown section '{path[0]}'", where=where,
                       hint=did_you_mean(path[0], [*sch.SECTIONS, *sch.TOP_LEVEL]))
    label = f"[{section.name}]"
    if section.shape == "named":
        label = f"[{section.name}.{path[1]}]" if len(path) > 1 else label
        if not inside:
            raise HepError(f"{label} must be a table of keys", where=where)
    if not inside:
        raise HepError(f"{label} must be a table", where=where)

    spec = section.field(inside[0])
    if spec is None:
        # a study may override any section: [study.x.run] events = …
        if section is sch.STUDY and inside[0] in sch.SECTIONS:
            nested, rest = sch.section_of(inside)
            if nested is None or not rest:
                raise HepError(f"{label} override of '{inside[0]}' must set keys", where=where)
            nested_spec = nested.field(rest[0])
            if nested_spec is None:
                raise HepError(f"unknown key '{rest[0]}' in {label}.{inside[0]}", where=where,
                               hint=did_you_mean(rest[0], _known_keys(nested)))
            return nested_spec, f"{label}.{inside[0]} {rest[0]}"
        raise HepError(f"unknown key '{inside[0]}' in {label}", where=where,
                       hint=did_you_mean(inside[0], _known_keys(section)))
    if len(inside) > 1:
        if not spec.free:
            raise HepError(f"{label} {inside[0]} does not take nested keys", where=where)
        if len(inside) > 2:
            raise HepError(f"{label} {inside[0]}.{inside[1]} does not take nested keys", where=where)
        return Field(spec.value_kind, doc=spec.doc), f"{label} {inside[0]}.{inside[1]}"
    return spec, f"{label} {inside[0]}"


def check_array_section(section: sch.Section, entries: Any, where: str) -> list[dict[str, Any]]:
    """Every table of a `[[section]]` array, against that section's fields."""
    label = f"[[{section.name}]]"
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise HepError(f"{label} must be a list of tables", where=where)
    checked = []
    for index, entry in enumerate(entries, start=1):
        values = {}
        for key, value in entry.items():
            spec = section.field(key)
            if spec is None:
                raise HepError(f"unknown key '{key}' in {label} #{index}", where=where,
                               hint=did_you_mean(key, _known_keys(section)))
            if spec.free:
                values[key] = {name: check_scalar(spec.value_kind, item, f"{label} {key}.{name}")
                               for name, item in check_scalar("table", value, f"{label} {key}").items()}
            else:
                values[key] = check(spec, value, f"{label} #{index} {key}")
        for key, spec in section.fields.items():
            if spec.required and not values.get(key):
                raise HepError(f"{label} #{index} needs '{key}'", where=where, hint=spec.doc)
            values.setdefault(key, spec.default_value())
        checked.append(values)
    return checked
