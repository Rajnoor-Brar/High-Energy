"""Shared TOML parsing, variation sweeps, naming, and plot-input helpers for HEP run tools."""

from __future__ import annotations

import hashlib
import itertools
import math
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    pass


def get_table(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing [{key}] table")
    return value


def get_string(table: dict[str, Any], key: str, section: str, *, required: bool = True,
               default: str = "") -> str:
    value = table.get(key, default)
    if not isinstance(value, str) or (required and not value):
        qualifier = "a non-empty string" if required else "a string"
        raise ConfigError(f"[{section}].{key} must be {qualifier}")
    return value


def get_integer(table: dict[str, Any], key: str, section: str, *, default: int,
                minimum: int = 0, maximum: int | None = None) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigError(f"[{section}].{key} must be an integer no smaller than {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"[{section}].{key} must be no larger than {maximum}")
    return value


def get_boolean(table: dict[str, Any], key: str, section: str, *, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"[{section}].{key} must be true or false")
    return value


def get_choice(table: dict[str, Any], key: str, section: str, choices: tuple[str, ...], default: str) -> str:
    value = table.get(key, default)
    if value not in choices:
        raise ConfigError(f"[{section}].{key} must be one of: {', '.join(choices)}")
    return value


def get_string_list(table: dict[str, Any], key: str, section: str) -> list[str]:
    value = table.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ConfigError(f"[{section}].{key} must be a list of non-empty strings")
    return value


def get_serial(table: dict[str, Any]) -> str:
    value = table.get("serial", "")
    if value == "":
        return ""
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 99:
        raise ConfigError("[rivpyth].serial must be an integer from 0 to 99")
    return f"{value:02d}"


def reject_keys(table: dict[str, Any], section: str, moved: dict[str, str]) -> None:
    for key, replacement in moved.items():
        if key in table:
            raise ConfigError(f"[{section}].{key} was removed; {replacement}")


def reject_unknown(table: dict[str, Any], section: str, known: set[str]) -> None:
    unknown = sorted(set(table) - known)
    if unknown:
        raise ConfigError(f"Unknown key(s) in [{section}]: {', '.join(unknown)}")


PDF_MIGRATION = ('declare [sweep.cmnd.<name>] with type = "pythia", setting = "PDF:pSet", '
                 'values/labels/tags, and list "cmnd.<name>" in [sweep].across')
MOVED_ANALYSIS_KEYS = {
    "pdf_sets": PDF_MIGRATION,
    "pdf_alias": "use [sweep.cmnd.<name>].labels",
    "alias_suffix": "use [sweep.cmnd.<name>].tags",
    "use_pdf": "use [settle.use] (constant) or [sweep].only (one point)",
    "pdf_suffix": "use [sweep].tag_style = \"index\" | \"value\" | \"tag\"",
    "riv_plugin": "use [settle.rivet].plugin (fixed) or a [sweep.rivet.<name>] plugin quantity",
}
MOVED_YODA_KEYS = {"pdf_legend": "use [sweep].yoda_legends = \"label\" | \"tag\" | \"value\""}


def read_config(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"Configuration file not found: {path}") from None
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"Invalid TOML in {path}: {error}") from None

    analysis = get_table(raw, "analysis")
    yoda = get_table(raw, "yoda")
    rivpyth = get_table(raw, "rivpyth")
    reject_keys(analysis, "analysis", MOVED_ANALYSIS_KEYS)
    reject_keys(yoda, "yoda", MOVED_YODA_KEYS)
    config = {
        "config_path": str(path),
        "cmnd_file": get_string(analysis, "cmnd_file", "analysis"),
        "event_count": get_integer(analysis, "event_count", "analysis", default=0),
        "seed": get_integer(analysis, "seed", "analysis", default=0, maximum=900_000_000),
        "plot_merge_type": get_integer(yoda, "plot_merge_type", "yoda", default=1, minimum=1, maximum=2),
        "plot_analysis": get_string(yoda, "plot_analysis", "yoda", required=False),
        "rivet_refs": get_boolean(yoda, "rivet_refs", "yoda", default=False),
        "use_data": get_boolean(yoda, "use_data", "yoda", default=False),
        "data_hist": get_boolean(yoda, "data_hist", "yoda", default=True),
        "data_file": get_string(yoda, "data_file", "yoda", required=False, default=""),
        "data_legend": get_string(yoda, "data_legend", "yoda", required=False, default="Data"),
        "data_reference": get_boolean(yoda, "data_reference", "yoda", default=True),
        "void_empty": get_boolean(yoda, "void_empty", "yoda", default=True),
        "min_entries": get_integer(yoda, "min_entries", "yoda", default=0),
        "auto_range": get_boolean(yoda, "auto_range", "yoda", default=False),
        "range_pad": get_integer(yoda, "range_pad", "yoda", default=0),
        "project": get_string(rivpyth, "project", "rivpyth", required=False, default=""),
        "generator": get_string(rivpyth, "generator", "rivpyth"),
        "serial": get_serial(rivpyth),
        "hepmc_file": get_string(rivpyth, "hepmc_file", "rivpyth", required=False),
        "yoda_file": get_string(rivpyth, "yoda_file", "rivpyth", required=False, default=""),
        "plugin_dir": get_string(rivpyth, "plugin_dir", "rivpyth"),
        "threads": get_integer(rivpyth, "threads", "rivpyth", default=20),
        "path_literal": get_boolean(rivpyth, "path_literal", "rivpyth", default=False),
    }
    config["sweep"] = read_sweep(raw.get("sweep", {}))
    config["settle"] = read_settle(raw.get("settle", {}), config["sweep"])
    config["studies"] = read_studies(raw.get("study", {}), config["sweep"])
    config["study"] = ""
    config["riv_plugin"] = config["settle"].plugin
    if config["path_literal"] and not config["hepmc_file"]:
        raise ConfigError("[rivpyth].hepmc_file is required when path_literal is true")
    if config["hepmc_file"] and not config["path_literal"]:
        raise ConfigError("[rivpyth].hepmc_file is no longer used: each run streams events through a "
                          "temporary FIFO; remove the key (it is only needed with path_literal = true)")
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    if config["use_data"] and not config["data_file"]:
        raise ConfigError("[yoda].data_file is required when [yoda].use_data is true")
    if config["use_data"] and not config["data_hist"] and not config["data_reference"]:
        raise ConfigError("[yoda].data_hist = false requires data_reference = true (data is then only the ratio reference)")
    sweep = config["sweep"]
    if config["plot_merge_type"] == 2 and not (
            sweep.across and all(quantity.type == "seed" for quantity in sweep.across)):
        raise ConfigError("[yoda].plot_merge_type = 2 (yodamerge) only combines statistically equivalent runs; "
                          "every scanned quantity must have type = \"seed\"")
    if not config["riv_plugin"] and not any(q.type == "plugin" for q in sweep.quantities):
        raise ConfigError("[settle.rivet].plugin is required unless a [sweep.rivet.*] plugin quantity sets it")


# ── Variation sweeps ─────────────────────────────────────────────────────────

QUANTITY_TYPES = {"cmnd": ("pythia", "beams", "seed"), "rivet": ("plugin", "option")}
QUANTITY_KEYS = {"type", "setting", "option", "values", "labels", "tags", "use", "in_legend"}
SWEEP_KEYS = {"across", "style", "overlay", "only", "tag_style", "yoda_legends",
              "seed_step", "skip_existing", "cmnd", "rivet"}
SETTLE_KEYS = {"cmnd", "rivet", "use", "tag"}
SAFE_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
SAFE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def format_value(value: Any) -> str:
    """Render a scalar the way a Pythia cmnd line or a legend expects it."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def sanitize(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-") or "x"


def normalize_setting(key: str) -> str:
    return re.sub(r"\s+", "", key).lower()


def check_beams(value: Any, where: str) -> None:
    pair = isinstance(value, list) and len(value) == 2 and all(is_number(item) and item > 0 for item in value)
    if not (pair or (is_number(value) and value > 0)):
        raise ConfigError(f"{where} must be eCM (positive number) or [eA, eB] (two positive numbers)")


def beams_settings(value: Any) -> list[tuple[str, str]]:
    if isinstance(value, list):
        return [("Beams:frameType", "2"), ("Beams:eA", format_value(value[0])),
                ("Beams:eB", format_value(value[1]))]
    return [("Beams:frameType", "1"), ("Beams:eCM", format_value(value))]


def check_seed(value: Any, where: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 900_000_000:
        raise ConfigError(f"{where} must be an integer seed in 1..900000000")


def seed_settings(value: int) -> list[tuple[str, str]]:
    return [("Random:setSeed", "on"), ("Random:seed", str(value))]


def check_option_value(value: Any, where: str) -> None:
    if not is_scalar(value) or ":" in format_value(value) or "=" in format_value(value):
        raise ConfigError(f"{where} must be a scalar without ':' or '='")


@dataclass
class Quantity:
    key: str                  # "cmnd.pdf"
    section: str              # "cmnd" | "rivet"
    name: str                 # "pdf"
    type: str
    values: list[Any]
    labels: list[str]
    tags: list[str]
    use: int                  # one-based constant choice; [settle.use] may replace it
    setting: str = ""
    option: str = ""
    in_legend: bool = True    # false: coupled quantity (e.g. a plugin) left out of legends

    def value_text(self, index: int) -> str:
        value = self.values[index]
        if isinstance(value, list):
            return "x".join(format_value(item) for item in value)
        if isinstance(value, dict):
            return ",".join(f"{key}={format_value(item)}" for key, item in value.items())
        return format_value(value)

    def label(self, index: int) -> str:
        if self.labels:
            return self.labels[index]
        return f"{self.name} = {self.value_text(index)}"

    def tag(self, index: int, style: str) -> str:
        if style == "index":
            return f"{self.name}{index + 1:02d}"
        if style == "tag" and self.tags:
            return self.tags[index]
        return sanitize(self.value_text(index))

    def legend(self, index: int, style: str) -> str:
        if style == "tag":
            return self.tag(index, "tag")
        if style == "value":
            return self.value_text(index)
        return self.label(index)

    def settings(self, index: int) -> list[tuple[str, str]]:
        """Pythia settings contributed by value `index` (cmnd-side quantities only)."""
        value = self.values[index]
        if self.type == "pythia":
            if self.setting:
                return [(self.setting, format_value(value))]
            return [(key, format_value(item)) for key, item in value.items()]
        if self.type == "beams":
            return beams_settings(value)
        if self.type == "seed":
            return seed_settings(value)
        return []

    def find_value(self, selector: Any, where: str) -> int:
        """Zero-based index from a one-based index or a tag (or the value text)."""
        if isinstance(selector, int) and not isinstance(selector, bool):
            if not 1 <= selector <= len(self.values):
                raise ConfigError(f"{where} = {selector} is outside 1..{len(self.values)}")
            return selector - 1
        if isinstance(selector, str):
            for index in range(len(self.values)):
                if selector in (self.tags[index] if self.tags else None, self.value_text(index)):
                    return index
            raise ConfigError(f"{where} = {selector!r} matches no tag or value of {self.key}")
        raise ConfigError(f"{where} must be a one-based index or a tag")


@dataclass
class Sweep:
    quantities: list[Quantity]
    groups: list[list[Quantity]]       # each group moves together; groups form a grid
    overlay: list[Quantity] | None     # group drawn as curves on one page
    only: int
    tag_style: str
    yoda_legends: str
    seed_step: int
    skip_existing: bool

    @property
    def across(self) -> list[Quantity]:
        return [quantity for group in self.groups for quantity in group]

    def find(self, key: str, section: str = "sweep") -> Quantity:
        for quantity in self.quantities:
            if quantity.key == key:
                return quantity
        declared = ", ".join(q.key for q in self.quantities) or "none"
        raise ConfigError(f"[{section}] refers to undeclared quantity '{key}' (declared: {declared})")


@dataclass
class Settle:
    settings: list[tuple[str, str]]    # fixed Pythia settings, in file order
    has_seed: bool                     # a settled seed replaces [analysis].seed
    plugin: str
    options: dict[str, str]            # fixed Rivet analysis options
    tag: str


def read_quantity(section: str, name: str, table: Any) -> Quantity:
    where = f"sweep.{section}.{name}"
    if not isinstance(table, dict):
        raise ConfigError(f"[{where}] must be a table")
    if not SAFE_NAME.fullmatch(name):
        raise ConfigError(f"[{where}]: quantity names must be identifiers")
    reject_unknown(table, where, QUANTITY_KEYS)
    kind = table.get("type")
    if kind not in QUANTITY_TYPES[section]:
        raise ConfigError(f"[{where}].type must be one of: {', '.join(QUANTITY_TYPES[section])}")
    values = table.get("values")
    if not isinstance(values, list) or not values:
        raise ConfigError(f"[{where}].values must be a non-empty list")
    setting = get_string(table, "setting", where, required=False)
    option = get_string(table, "option", where, required=False)
    if setting and kind != "pythia":
        raise ConfigError(f"[{where}].setting is only valid for type = \"pythia\"")
    if option and kind != "option":
        raise ConfigError(f"[{where}].option is only valid for type = \"option\"")

    for position, value in enumerate(values, start=1):
        bad = f"[{where}].values entry {position}"
        if kind == "pythia" and setting:
            if not is_scalar(value):
                raise ConfigError(f"{bad} must be a scalar when setting is given")
        elif kind == "pythia":
            if not isinstance(value, dict) or not value or not all(
                    isinstance(key, str) and ":" in key and is_scalar(item) for key, item in value.items()):
                raise ConfigError(f"{bad} must be a table of \"Group:key\" = scalar "
                                  "(or give [" + where + "].setting)")
        elif kind == "beams":
            check_beams(value, bad)
        elif kind == "seed":
            check_seed(value, bad)
        elif kind == "plugin":
            if not isinstance(value, str) or not SAFE_NAME.fullmatch(value):
                raise ConfigError(f"{bad} must be a Rivet analysis name (use type = \"option\" for options)")
        elif kind == "option":
            check_option_value(value, bad)
    if kind == "option" and not SAFE_NAME.fullmatch(option):
        raise ConfigError(f"[{where}].option must name the Rivet analysis option")

    labels = get_string_list(table, "labels", where)
    tags = get_string_list(table, "tags", where)
    for key, items in (("labels", labels), ("tags", tags)):
        if items and len(items) != len(values):
            raise ConfigError(f"[{where}].{key} must have one entry per value ({len(values)})")
    for tag in tags:
        if not SAFE_TAG.fullmatch(tag):
            raise ConfigError(f"[{where}].tags entries must be filename-safe: {tag!r}")
    if len(set(tags)) != len(tags):
        raise ConfigError(f"[{where}].tags must be unique")
    use = get_integer(table, "use", where, default=0, maximum=len(values))
    return Quantity(key=f"{section}.{name}", section=section, name=name, type=kind, values=values,
                    labels=labels, tags=tags, use=use, setting=setting, option=option,
                    in_legend=get_boolean(table, "in_legend", where, default=True))


def read_sweep(table: Any) -> Sweep:
    if not isinstance(table, dict):
        raise ConfigError("[sweep] must be a table")
    reject_unknown(table, "sweep", SWEEP_KEYS)
    quantities = []
    for section in ("cmnd", "rivet"):
        group = table.get(section, {})
        if not isinstance(group, dict):
            raise ConfigError(f"[sweep.{section}] must be a table of quantities")
        quantities += [read_quantity(section, name, body) for name, body in group.items()]
    options = [q.option for q in quantities if q.type == "option"]
    duplicates = sorted({o for o in options if options.count(o) > 1})
    if duplicates:
        raise ConfigError(f"Rivet option(s) declared by more than one quantity: {', '.join(duplicates)}")
    sweep = Sweep(
        quantities=quantities, groups=[], overlay=None,
        only=get_integer(table, "only", "sweep", default=0),
        tag_style=get_choice(table, "tag_style", "sweep", ("tag", "value", "index"), "tag"),
        yoda_legends=get_choice(table, "yoda_legends", "sweep", ("label", "tag", "value"), "label"),
        seed_step=get_integer(table, "seed_step", "sweep", default=1),
        skip_existing=get_boolean(table, "skip_existing", "sweep", default=False),
    )
    across = table.get("across", [])
    check_across(across, "[sweep].across")
    style = table.get("style")
    if style is not None:
        if style not in ("together", "grid"):
            raise ConfigError("[sweep].style must be together or grid")
        if any(isinstance(entry, list) for entry in across):
            raise ConfigError("[sweep].style only applies to a flat across list; "
                              "with groups, lists move together and groups form a grid")
    set_groups(sweep, flat_groups(across, style), table.get("overlay"))
    return sweep


def flat_groups(across: list[Any], style: str | None) -> list[list[str]]:
    """Normalise `across` into groups; the flat form honours the legacy `style`."""
    if style == "together" and across:
        return [list(across)]
    return [entry if isinstance(entry, list) else [entry] for entry in across]


def set_groups(sweep: Sweep, groups: list[list[str]], overlay: Any = None, section: str = "sweep") -> None:
    """(Re)select the scanned groups; used by the TOML reader and the --across override."""
    keys = [key for group in groups for key in group]
    if len(set(keys)) != len(keys):
        raise ConfigError(f"[{section}].across lists a quantity twice")
    sweep.groups = [[sweep.find(key, section) for key in group] for group in groups]
    for group in sweep.groups:
        lengths = {len(quantity.values) for quantity in group}
        if len(lengths) > 1:
            detail = ", ".join(f"{q.key}={len(q.values)}" for q in group)
            raise ConfigError(f"Coupled quantities need equal value counts ({detail})")
    if overlay is not None and not isinstance(overlay, str):
        raise ConfigError("[sweep].overlay must be a quantity key")
    sweep.overlay = sweep.groups[-1] if sweep.groups else None
    if overlay:
        quantity = sweep.find(overlay, section)
        matches = [group for group in sweep.groups if quantity in group]
        if not matches:
            raise ConfigError(f"[sweep].overlay '{overlay}' must be listed in [sweep].across")
        sweep.overlay = matches[0]


def parse_across(text: str) -> list[list[str]]:
    """CLI form: ',' separates groups, '+' couples quantities inside a group."""
    groups = [[key for key in part.split("+") if key] for part in text.split(",")]
    if any(not group for group in groups):
        raise ConfigError("--across: empty group (use 'a+b,c')")
    return groups


def read_settle(table: Any, sweep: Sweep) -> Settle:
    if not isinstance(table, dict):
        raise ConfigError("[settle] must be a table")
    reject_unknown(table, "settle", SETTLE_KEYS)

    settings: list[tuple[str, str]] = []
    has_seed = False
    cmnd = table.get("cmnd", {})
    if not isinstance(cmnd, dict):
        raise ConfigError("[settle.cmnd] must be a table")
    for key, value in cmnd.items():
        where = f"[settle.cmnd].{key}"
        if ":" in key:
            if not is_scalar(value):
                raise ConfigError(f"{where} must be a scalar")
            settings.append((key, format_value(value)))
        elif key == "beams":
            check_beams(value, where)
            settings += beams_settings(value)
        elif key == "seed":
            check_seed(value, where)
            settings += seed_settings(value)
            has_seed = True
        else:
            raise ConfigError(f"{where}: use a \"Group:key\" Pythia setting or a shorthand (beams, seed)")

    rivet = table.get("rivet", {})
    if not isinstance(rivet, dict):
        raise ConfigError("[settle.rivet] must be a table")
    reject_unknown(rivet, "settle.rivet", {"plugin", "options"})
    plugin = get_string(rivet, "plugin", "settle.rivet", required=False)
    if plugin and not SAFE_NAME.fullmatch(plugin):
        raise ConfigError("[settle.rivet].plugin must be a Rivet analysis name (options go in [settle.rivet].options)")
    raw_options = rivet.get("options", {})
    if not isinstance(raw_options, dict):
        raise ConfigError("[settle.rivet].options must be a table of NAME = value")
    options = {}
    for name, value in raw_options.items():
        if not SAFE_NAME.fullmatch(name):
            raise ConfigError(f"[settle.rivet].options: invalid option name {name!r}")
        check_option_value(value, f"[settle.rivet].options.{name}")
        options[name] = format_value(value)

    use = table.get("use", {})
    if not isinstance(use, dict):
        raise ConfigError("[settle.use] must be a table of \"section.quantity\" = index or tag")
    for key, selector in use.items():
        quantity = sweep.find(key, "settle.use")
        quantity.use = quantity.find_value(selector, f"[settle.use].\"{key}\"") + 1

    tag = get_string(table, "tag", "settle", required=False)
    if tag and not SAFE_TAG.fullmatch(tag):
        raise ConfigError("[settle].tag must be filename-safe")
    return Settle(settings=settings, has_seed=has_seed, plugin=plugin, options=options, tag=tag)


STUDY_KEYS = {"description", "across", "style", "overlay", "pin"}


def check_across(across: Any, where: str) -> None:
    if not isinstance(across, list) or not all(
            isinstance(entry, str) or (isinstance(entry, list) and entry and all(isinstance(k, str) for k in entry))
            for entry in across):
        raise ConfigError(f"{where} must be a list of quantity keys or lists of keys (coupled groups)")


def read_studies(table: Any, sweep: Sweep) -> dict[str, dict[str, Any]]:
    """[study.<name>] presets: a named scan (across/style/overlay) plus pins, checked at load time."""
    if not isinstance(table, dict):
        raise ConfigError("[study] must contain [study.<name>] tables")
    studies = {}
    for name, body in table.items():
        where = f"study.{name}"
        if not isinstance(body, dict):
            raise ConfigError(f"[{where}] must be a table")
        reject_unknown(body, where, STUDY_KEYS)
        get_string(body, "description", where, required=False)
        across = body.get("across", [])
        check_across(across, f"[{where}].across")
        for key in (k for entry in across for k in (entry if isinstance(entry, list) else [entry])):
            sweep.find(key, where)
        style = body.get("style")
        if style is not None and (style not in ("together", "grid") or any(isinstance(e, list) for e in across)):
            raise ConfigError(f"[{where}].style must be together or grid, and only with a flat across list")
        overlay = body.get("overlay")
        if overlay is not None and (not isinstance(overlay, str) or not any(
                overlay == k for entry in across for k in (entry if isinstance(entry, list) else [entry]))):
            raise ConfigError(f"[{where}].overlay must be a quantity listed in its across")
        pins = body.get("pin", {})
        if not isinstance(pins, dict):
            raise ConfigError(f"[{where}].pin must be a table of \"section.quantity\" = index or tag")
        for key, selector in pins.items():
            sweep.find(key, f"{where}.pin").find_value(selector, f"[{where}.pin].\"{key}\"")
        studies[name] = body
    return studies


def parse_pin(text: str) -> tuple[str, Any]:
    """CLI form KEY=SELECTOR; an all-digit selector is a one-based index, anything else a tag."""
    key, separator, selector = text.partition("=")
    if not separator or not key or not selector:
        raise ConfigError(f"--pin expects section.quantity=tag-or-index, got {text!r}")
    return key, int(selector) if selector.isdigit() else selector


def apply_pins(sweep: Sweep, pins: dict[str, Any], where: str) -> None:
    for key, selector in pins.items():
        quantity = sweep.find(key, where)
        quantity.use = quantity.find_value(selector, f"{where} {key}") + 1


def apply_study(config: dict[str, Any], name: str) -> None:
    studies = config["studies"]
    if name not in studies:
        available = ", ".join(sorted(studies)) or "none"
        raise ConfigError(f"Unknown study '{name}' (available: {available})")
    body = studies[name]
    sweep: Sweep = config["sweep"]
    apply_pins(sweep, body.get("pin", {}), f"[study.{name}.pin]")
    set_groups(sweep, flat_groups(body.get("across", []), body.get("style")), body.get("overlay"), f"study.{name}")
    config["study"] = name


def apply_overrides(config: dict[str, Any], across: str | None, style: str | None,
                    overlay: str | None = None, study: str | None = None,
                    pins: list[str] | None = None) -> None:
    """Command-line selection, applied in order: --study, --pin, then --across/--style/--overlay.

    A study replaces [sweep].across/style/overlay and adds its pins on top of [settle.use];
    a kept overlay survives an --across override while its quantity is still scanned.
    """
    sweep: Sweep = config["sweep"]
    if study:
        apply_study(config, study)
    if pins:
        apply_pins(sweep, dict(parse_pin(text) for text in pins), "--pin")
    if across is None and style is None and overlay is None:
        validate_config(config)
        return
    if across is not None:
        groups = parse_across(across)
        if style is not None:
            if any(len(group) > 1 for group in groups):
                raise ConfigError("--style only applies to a flat --across list (no '+')")
            groups = flat_groups([key for group in groups for key in group], style)
    else:
        keys = [q.key for q in sweep.across]
        groups = flat_groups(keys, style)
    if overlay is None:
        overlay_keys = {q.key for q in sweep.overlay} if sweep.overlay else set()
        overlay = next((key for group in groups for key in group if key in overlay_keys), None)
    set_groups(sweep, groups, overlay, "--across")
    validate_config(config)


@dataclass
class Point:
    number: int                               # one-based position in the expansion
    choice: dict[str, int]                    # quantity key -> zero-based value index (applied only)
    settings: list[tuple[str, str, str]]      # (key, value, origin) Pythia lines in application order
    analysis: str                             # Rivet analysis incl. ":OPT=VAL" options (sorted, as Rivet does)
    plugin: str                               # analysis name without options
    suffix: str                               # filename suffix from applied quantities (+ settle tag)
    legend: str                               # legend text from the scanned quantities
    page: tuple[tuple[str, int], ...] = field(default_factory=tuple)   # page key (non-overlay groups)


def expand_points(config: dict[str, Any], index: int | None = None) -> list[Point]:
    """Resolve the sweep into fully specified run points (optionally just one, one-based)."""
    sweep: Sweep = config["sweep"]
    ranges = [range(len(group[0].values)) for group in sweep.groups]
    points = []
    for number, combo in enumerate(itertools.product(*ranges), start=1):
        scanned = {quantity.key: value for group, value in zip(sweep.groups, combo) for quantity in group}
        choice = {}
        for quantity in sweep.quantities:
            if quantity.key in scanned:
                choice[quantity.key] = scanned[quantity.key]
            elif quantity.use:
                choice[quantity.key] = quantity.use - 1
        points.append(build_point(config, number, choice))

    names = [point.suffix for point in points]
    if len(set(names)) != len(names):
        raise ConfigError("Sweep points do not have unique names; add distinct tags")

    selected = index if index is not None else (sweep.only or None)
    if selected is not None:
        if not 1 <= selected <= len(points):
            raise ConfigError(f"Point index {selected} is outside the sweep (1-{len(points)})")
        points = [points[selected - 1]]
    if len(points) > 1 and config["path_literal"]:
        raise ConfigError("A sweep with several points requires path_literal = false")
    return points


def build_point(config: dict[str, Any], number: int, choice: dict[str, int]) -> Point:
    sweep: Sweep = config["sweep"]
    settle: Settle = config["settle"]
    settings: list[tuple[str, str, str]] = []
    owners: dict[str, str] = {}

    def claim(key: str, value: str, origin: str) -> None:
        normalized = normalize_setting(key)
        if normalized in owners and owners[normalized] != origin:
            raise ConfigError(f"Pythia setting '{key}' is set by both {owners[normalized]} and {origin}"
                              " (declare it as a quantity and pin it with [settle.use] instead)")
        owners[normalized] = origin
        settings.append((key, value, origin))

    if config["event_count"]:
        claim("Main:numberOfEvents", str(config["event_count"]), "[analysis].event_count")
    if config["threads"]:
        claim("Parallelism:numThreads", str(config["threads"]), "[rivpyth].threads")

    seed_quantity = any(sweep.find(key).type == "seed" for key in choice)
    base_seed = config["seed"]
    if base_seed and not seed_quantity and not settle.has_seed:
        base_seed += (number - 1) * sweep.seed_step
        if base_seed > 900_000_000:
            raise ConfigError("[analysis].seed plus sweep offset exceeds 900000000")
        for key, value in seed_settings(base_seed):
            claim(key, value, "[analysis].seed")

    for key, value in settle.settings:
        claim(key, value, "[settle.cmnd]")

    plugin = settle.plugin
    options = dict(settle.options)
    tags: list[str] = []
    for quantity in sweep.quantities:
        if quantity.key not in choice:
            continue
        value_index = choice[quantity.key]
        for key, value in quantity.settings(value_index):
            claim(key, value, quantity.key)
        if quantity.type == "plugin":
            plugin = quantity.values[value_index]
        elif quantity.type == "option":
            options[quantity.option] = format_value(quantity.values[value_index])   # beats [settle.rivet]
        tags.append(quantity.tag(value_index, sweep.tag_style))
    if settle.tag:
        tags.append(settle.tag)

    if not plugin:
        raise ConfigError("No Rivet analysis resolved for a sweep point")
    legend_quantities = [q for q in sweep.across if q.in_legend]
    legend = ", ".join(q.legend(choice[q.key], sweep.yoda_legends) for q in legend_quantities)
    page = tuple((q.key, choice[q.key]) for group in sweep.groups if group is not sweep.overlay for q in group)
    analysis = ":".join([plugin, *(f"{name}={value}" for name, value in sorted(options.items()))])
    return Point(number=number, choice=choice, settings=settings, analysis=analysis, plugin=plugin,
                 suffix="_".join(tags), legend=legend, page=page)


def constant_suffix(config: dict[str, Any]) -> str:
    """Tags of the quantities held constant (applied but not scanned), plus the settle tag."""
    sweep: Sweep = config["sweep"]
    parts = [q.tag(q.use - 1, sweep.tag_style) for q in sweep.quantities if q.use and q not in sweep.across]
    if config["settle"].tag:
        parts.append(config["settle"].tag)
    return "_".join(parts)


def page_suffix(config: dict[str, Any], page: tuple[tuple[str, int], ...]) -> str:
    """Name of one plot page: constant tags, the page's fixed group values, then the curve quantity names."""
    sweep: Sweep = config["sweep"]
    parts = [constant_suffix(config)]
    parts += [sweep.find(key).tag(value, sweep.tag_style) for key, value in page]
    # "by_<curve quantities>" keeps page names distinct from point names (and merged yodas from point yodas)
    parts.append("by_" + "_".join(quantity.name for quantity in (sweep.overlay or [])))
    return "_".join(part for part in parts if part)


def curve_legend(config: dict[str, Any], point: Point) -> str:
    """Legend for one curve: the overlay group's labels when groups form a grid, else all scanned labels."""
    sweep: Sweep = config["sweep"]
    if len(sweep.groups) > 1 and sweep.overlay:
        shown = [q for q in sweep.overlay if q.in_legend] or sweep.overlay[:1]
        return ", ".join(q.legend(point.choice[q.key], sweep.yoda_legends) for q in shown)
    return point.legend or point.suffix or Path(config["yoda_file"] or point.plugin).stem


def group_pages(points: list[Point]) -> dict[tuple[tuple[str, int], ...], list[Point]]:
    pages: dict[tuple[tuple[str, int], ...], list[Point]] = {}
    for point in points:
        pages.setdefault(point.page, []).append(point)
    return pages


# ── Paths and naming ─────────────────────────────────────────────────────────

def resolve_path(value: str, project: str, root: str, literal: bool) -> str:
    if literal:
        return value
    if Path(value).is_absolute() or Path(project).is_absolute():
        raise ConfigError("Non-literal paths must be relative")
    return str(Path(root) / project / value)


def run_filename(filename: str, serial: str, suffix: str) -> str:
    path = Path(filename)
    name = f"{serial}_{path.name}" if serial else path.name
    if suffix:
        extension = path.suffix
        stem = name[:-len(extension)] if extension else name
        name = f"{stem}_{suffix}{extension}"
    return str(path.with_name(name))


def resolve_yoda_file(config: dict[str, Any], suffix: str = "") -> str:
    if config["path_literal"]:
        if not config["yoda_file"]:
            raise ConfigError("[rivpyth].yoda_file is required when path_literal is true")
        return config["yoda_file"]
    filename = config["yoda_file"] or f"{config['riv_plugin'] or 'rivet'}.yoda"
    if not filename.endswith(".yoda"):
        filename += ".yoda"
    if Path(filename).name != filename:
        raise ConfigError("[rivpyth].yoda_file must be a filename when path_literal is false")
    return str(Path("results") / config["project"] / run_filename(filename, config["serial"], suffix))


def execution_plan(config: dict[str, Any], point: Point) -> dict[str, str]:
    literal = config["path_literal"]
    yoda_file = resolve_yoda_file(config, point.suffix)
    point_cmnd = Path(yoda_file).with_suffix(".cmnd") if literal else \
        Path(yoda_file).parent / "cmnd" / (Path(yoda_file).stem + ".cmnd")
    return {
        "generator": resolve_path(config["generator"], config["project"], "output", literal),
        "base_cmnd": resolve_path(config["cmnd_file"], config["project"], "configs", literal),
        "point_cmnd": str(point_cmnd),
        # Non-literal runs stream through a FIFO in a private temporary directory (set by rivpyth).
        "hepmc_file": config["hepmc_file"] if literal else "",
        "yoda_file": yoda_file,
        "plugin_dir": resolve_path(config["plugin_dir"], config["project"], "output", literal),
        "analysis": point.analysis,
    }


def write_point_cmnd(config: dict[str, Any], plan: dict[str, str], point: Point) -> None:
    """Write the point cmnd: run control and sweep overrides, read by the generator after the base.

    The header records the base file's SHA-256 so a later edit of the base is detectable;
    base + point cmnd together reproduce the run.
    """
    base = Path(plan["base_cmnd"])
    try:
        digest = hashlib.sha256(base.read_bytes()).hexdigest()
    except OSError as error:
        raise ConfigError(f"Cannot read base cmnd file {base}: {error.strerror}") from None
    lines = ["! rivpyth point cmnd (generated) — applied after the base cmnd; later settings win",
             f"! run config : {config['config_path']}",
             f"! base cmnd  : {base}",
             f"! base sha256: {digest}",
             f"! point      : {point.number} {point.suffix or '(base)'}",
             f"! analysis   : {point.analysis}"]
    origin = None
    for key, value, source in point.settings:
        if source != origin:
            lines += ["", f"! from {source}"]
            origin = source
        lines.append(f"{key} = {value}")
    destination = Path(plan["point_cmnd"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n")


def plot_file_for(config: dict[str, Any], analysis: str) -> Path | None:
    """Project .plot file for an analysis; None lets rivet-mkhtml use installed plot files."""
    path = Path("sources") / config["project"] / f"{analysis}.plot"
    return path if path.is_file() else None


def common_analysis(config: dict[str, Any], points: list[Point]) -> str:
    return config["plot_analysis"] or points[0].plugin


def unify_yodas(points: list[Point], yodas: list[Path], analysis: str, workdir: Path) -> list[Path]:
    """Copy yodas whose analysis differs from `analysis`, renaming their objects so they overlay."""
    import yoda

    unified = []
    for point, path in zip(points, yodas):
        if point.plugin == analysis:
            unified.append(path)
            continue
        objects = []
        for obj_path, obj in read_yoda(path).items():
            prefix = "/REF" if obj_path.startswith("/REF/") else ""
            parts = obj_path.removeprefix(prefix).split("/", 2)
            if len(parts) == 3 and parts[1].split(":", 1)[0] == point.plugin:
                parts[1] = analysis + parts[1][len(point.plugin):]
                obj.setPath(prefix + "/".join(parts))
            objects.append(obj)
        destination = workdir / f"{point.number:03d}_{path.name}"
        yoda.write(objects, str(destination))
        unified.append(destination)
    return unified


def void_bins(config: dict[str, Any], yodas: list[Path], workdir: Path) -> list[Path]:
    """Blank bins that carry no information, consistently across the curves of one page.

    A bin becomes a void (NaN value, no errors) in every curve when
      - [yoda].void_empty and the bin is exactly zero in all curves, or
      - [yoda].min_entries > 0 and any curve has fewer raw entries there
        (from the /RAW/... histogram Rivet stores next to each finalized object).
    rivet-mkhtml then leaves gaps instead of drawing 0/0 = 1 +- 1 in the ratio panel.
    Only 1D binned estimates (finalized Rivet histograms) are touched.
    """
    import yoda

    if not config["void_empty"] and not config["min_entries"]:
        return yodas
    contents = [read_yoda(path) for path in yodas]

    def plot_key(obj_path: str) -> str:
        analysis, name = split_object_path(obj_path)
        return f"/{analysis.split(':', 1)[0]}/{name}"   # options do not separate plots

    empty: dict[str, list[bool]] = {}    # plot key -> bin is zero in every curve so far
    sparse: dict[str, list[bool]] = {}   # plot key -> bin is below min_entries in some curve
    for objects in contents:
        for obj_path, obj in objects.items():
            if obj_path.startswith(("/REF/", "/RAW/")) or split_object_path(obj_path) is None \
                    or type(obj).__name__ != "BinnedEstimate1D":
                continue
            key = plot_key(obj_path)
            values = [float(value) for value in obj.vals()]
            zero = [value == 0.0 for value in values]
            if key in empty and len(empty[key]) == len(zero):
                empty[key] = [a and b for a, b in zip(empty[key], zero)]
            else:
                empty.setdefault(key, zero)
            raw = objects.get("/RAW" + obj_path)
            if config["min_entries"] and raw is not None and raw.numBins() == obj.numBins():
                low = [bin_.numEntries() < config["min_entries"] for bin_ in raw.bins()]
                previous = sparse.get(key, [False] * len(low))
                sparse[key] = [a or b for a, b in zip(previous, low)]

    voids = {}
    for key, zero in empty.items():
        mask = zero if config["void_empty"] else [False] * len(zero)
        if key in sparse and len(sparse[key]) == len(mask):
            mask = [a or b for a, b in zip(mask, sparse[key])]
        if any(mask):
            voids[key] = mask

    result = []
    for position, (path, objects) in enumerate(zip(yodas, contents)):
        changed = False
        for obj_path, obj in objects.items():
            if obj_path.startswith(("/REF/", "/RAW/")) or split_object_path(obj_path) is None:
                continue
            mask = voids.get(plot_key(obj_path))
            if mask is None or type(obj).__name__ != "BinnedEstimate1D" or obj.numBins() != len(mask):
                continue
            for index, blank in enumerate(mask, start=1):
                if blank:
                    obj.bin(index).setVal(float("nan"))
                    obj.bin(index).rmErrs()
                    changed = True
        if changed:
            destination = workdir / f"void_{position:03d}_{path.name}"
            yoda.write(list(objects.values()), str(destination))
            result.append(destination)
        else:
            result.append(path)
    voided = sum(sum(mask) for mask in voids.values())
    if voided:
        rule = "empty" + (f" or < {config['min_entries']} entries" if config["min_entries"] else "")
        print(f"voided {voided} bins ({rule}) in {len(voids)} histograms", file=sys.stderr)
    return result


def auto_range_plot(config: dict[str, Any], analysis: str, yodas: list[Path], workdir: Path) -> Path | None:
    """Write a .plot file clipping each 1D plot's x axis to the bins that have content.

    The span covers every bin with a finite, non-zero value in any of `yodas` (curves after
    void_bins, plus the data file if any), widened by [yoda].range_pad bins on each side.
    Passed to rivet-mkhtml after the project .plot file, so it overrides only XMin/XMax.
    """
    if not config["auto_range"]:
        return None
    spans: dict[str, tuple[float, float]] = {}
    pad = config["range_pad"]
    for path in yodas:
        for obj_path, obj in read_yoda(path).items():
            if obj_path.startswith("/RAW/") or type(obj).__name__ != "BinnedEstimate1D":
                continue
            parsed = split_object_path(obj_path)
            if parsed is None or parsed[0].split(":", 1)[0] != analysis:
                continue
            values = [float(value) for value in obj.vals()]
            filled = [i for i, value in enumerate(values) if math.isfinite(value) and value != 0.0]
            if not filled:
                continue
            edges = [float(edge) for edge in obj.xEdges()]
            first = max(filled[0] - pad, 0)
            last = min(filled[-1] + pad, len(values) - 1)
            low, high = edges[first], edges[last + 1]
            key = f"/{analysis}/{parsed[1]}"
            if key in spans:
                low, high = min(low, spans[key][0]), max(high, spans[key][1])
            spans[key] = (low, high)
    if not spans:
        return None
    blocks = [f"# BEGIN PLOT {key}\nXMin={low:g}\nXMax={high:g}\n# END PLOT\n"
              for key, (low, high) in sorted(spans.items())]
    destination = workdir / "auto_range.plot"
    destination.write_text("\n".join(blocks))
    return destination


# ── Yoda data handling ───────────────────────────────────────────────────────

def read_yoda(path: Path) -> dict[str, Any]:
    try:
        import yoda
    except ImportError as error:
        raise ConfigError("Python Yoda bindings are required for data-file handling") from error
    try:
        return yoda.read(str(path))
    except Exception as error:
        raise ConfigError(f"Cannot read Yoda file {path}: {error}") from None


def is_reference(obj: Any, path: str) -> bool:
    if path.startswith("/REF/"):
        return True
    return obj.hasAnnotation("IsRef") and str(obj.annotation("IsRef")) not in {"0", "false", "False"}


def split_object_path(path: str) -> tuple[str, str] | None:
    """Return (analysis, histogram name) for a plottable object path, else None."""
    parts = path.removeprefix("/REF").split("/", 2)
    if len(parts) < 3 or not parts[1] or not parts[2]:
        return None
    if parts[1] in {"TMP", "RAW"} or parts[1].startswith("_") or parts[2].startswith("_"):
        return None
    return parts[1], parts[2]


def edge_index(edges: list[float], value: float) -> int | None:
    for index, edge in enumerate(edges):
        if math.isclose(edge, value, rel_tol=1e-9, abs_tol=1e-12):
            return index
    return None


def align_to_edges(obj: Any, mc_edges: list[float]) -> Any | None:
    """Trim a 1D data object to its longest run of bins whose edges are all MC edges.

    rivet-mkhtml rebins MC onto the reference binning, which only works when every
    reference edge is also an MC edge; otherwise YODA's rebinning indexes past the end.
    Returns obj unchanged when already aligned, a trimmed clone, or None if nothing aligns.
    """
    import yoda

    data_edges = [float(edge) for edge in obj.xEdges()]
    aligned = [edge_index(mc_edges, edge) is not None for edge in data_edges]
    if all(aligned):
        return obj
    best, start = (0, 0), None
    for index, ok in enumerate(aligned + [False]):
        if ok and start is None:
            start = index
        elif not ok and start is not None:
            if index - start > best[1] - best[0]:
                best = (start, index)
            start = None
    first, last = best
    if last - first < 2:
        return None
    trimmed = yoda.BinnedEstimate1D(data_edges[first:last], obj.path(), obj.title())
    for key in obj.annotations():
        if key not in {"Path", "Type", "Title"}:
            trimmed.setAnnotation(key, obj.annotation(key))
    for number in range(1, last - first):
        trimmed.set(number, obj.bin(first + number))
    return trimmed


def remap_data_yoda(config: dict[str, Any], compared_yodas: list[Path], analysis: str,
                    destination: Path) -> None:
    """Write a copy of the data file whose objects live under the Rivet plugin's analysis name.

    The data file carries its own analysis name (e.g. /REF/ZEUS_2012_I1116258/d01-x01-y01),
    which rivet-mkhtml would plot on a separate page. Renaming each object to
    /[REF/]<analysis>/<histogram> puts data and MC on the same plots. MC objects of
    option variants (/<analysis>:OPT=VAL/...) share the same reference.
    """
    import yoda

    compared: dict[str, list[float] | None] = {}
    for path in compared_yodas:
        for obj_path, obj in read_yoda(path).items():
            parsed = split_object_path(obj_path)
            if parsed and parsed[0].split(":", 1)[0] == analysis and not obj_path.startswith("/REF/"):
                try:
                    compared.setdefault(parsed[1], [float(edge) for edge in obj.xEdges()])
                except (AttributeError, TypeError):
                    compared.setdefault(parsed[1], None)
    if not compared:
        raise ConfigError(f"Selected Yoda output has no /{analysis}/ histograms")

    remapped = []
    for obj_path, obj in read_yoda(Path(config["data_file"])).items():
        parsed = split_object_path(obj_path)
        if parsed is None or parsed[1] not in compared:
            continue
        if config["data_reference"]:
            if not is_reference(obj, obj_path):
                continue
            obj.setPath(f"/REF/{analysis}/{parsed[1]}")
            obj.setAnnotation("IsRef", 1)
        else:
            obj.setPath(f"/{analysis}/{parsed[1]}")
            if obj.hasAnnotation("IsRef"):
                obj.rmAnnotation("IsRef")
        mc_edges = compared[parsed[1]]
        if mc_edges is not None and hasattr(obj, "xEdges"):
            original = [float(edge) for edge in obj.xEdges()]
            if not config["data_reference"]:
                # A plain (non-reference) curve is forced onto the first MC curve's bins,
                # so it only draws when the binning matches exactly.
                if len(original) != len(mc_edges) or any(
                        edge_index(mc_edges, edge) is None for edge in original):
                    print(f"warning: data {parsed[1]} skipped: binning differs from MC "
                          "(use data_reference = true to overlay it)", file=sys.stderr)
                    continue
            obj = align_to_edges(obj, mc_edges)
            if obj is None:
                print(f"warning: data {parsed[1]} skipped: no bin edges {original} match the MC binning",
                      file=sys.stderr)
                continue
            kept = [float(edge) for edge in obj.xEdges()]
            if kept != original:
                print(f"warning: data {parsed[1]} trimmed to [{kept[0]:g}, {kept[-1]:g}] "
                      f"(edges {original} vs MC binning)", file=sys.stderr)
        if not config["data_hist"]:
            # Keep the curve as ratio denominator but do not draw it in the main panel
            obj.setAnnotation("MainPanel", 0)
        remapped.append(obj)

    if not remapped:
        kind = "reference (IsRef) histograms" if config["data_reference"] else "histograms"
        raise ConfigError(f"[yoda].data_file has no {kind} that can be overlaid on /{analysis}/ "
                          "(histogram names or binning differ; see warnings above)")
    yoda.write(remapped, str(destination))


def plot_arguments(config: dict[str, Any], curves: list[tuple[Path, str | None]], analysis: str,
                   workdir: Path) -> list[str]:
    """Build rivet-mkhtml input arguments for MC curves plus optional data.

    curves holds (yoda file, legend title or None), already unified onto `analysis`.
    workdir receives the remapped data file and must outlive the rivet-mkhtml call.
    """
    arguments = ["--rmopts"] + ([] if config["rivet_refs"] else ["--no-rivet-refs"])
    inputs = [f"{path}:Title={title.replace(':', ' ')}" if title else str(path) for path, title in curves]
    if not config["use_data"]:
        return [*arguments, *inputs]

    data_file = Path(config["data_file"])
    if not data_file.is_file():
        raise ConfigError(f"[yoda].data_file not found: {data_file}")
    data_yoda = workdir / f"{analysis}_data.yoda"
    remap_data_yoda(config, [path for path, _ in curves], analysis, data_yoda)

    if config["data_reference"]:
        arguments += ["--reflabel", config["data_legend"]]
        data_input = str(data_yoda)
    else:
        data_input = f"{data_yoda}:Title={config['data_legend']}"

    if config["data_hist"]:
        return [*arguments, *inputs, data_input]

    # The hidden reference curve still owns a legend label, which would shift every
    # entry by one; list the MC curves explicitly so only drawn curves are labelled.
    names = [f"curve{index}" for index in range(1, len(inputs) + 1)]
    inputs = [f"{entry}:Name={name}" for entry, name in zip(inputs, names)]
    return [*arguments, *inputs, data_input, f"PLOT:LegendOnly={' '.join(names)}"]
