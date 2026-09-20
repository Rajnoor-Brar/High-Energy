"""Field descriptions and the value checks built on them.

A `Field` is the single source of truth for a configuration key: its type, default, range, allowed
values and documentation. The section dataclasses in `schema.py` are generated from these tables, and
`hep config reference` and `hep config init` (P1-S06) read the same tables, so documentation cannot
drift from behaviour.

Checks are deliberately strict (01 N4): a wrong type or an out-of-range value is an error naming the
file, the key and what was expected. Integers are range-checked before use, so a negative thread count
is rejected rather than wrapping (an old `utils` defect).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from ..errors import HepError

#: Duration strings used by `[terminal]`: "500ms", "30s", "5m", "1h", or a plain number of seconds.
DURATION = re.compile(r"^(?P<amount>\d+(?:\.\d+)?)(?P<unit>ms|s|m|h)?$")
_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, None: 1.0}


@dataclass(frozen=True)
class Field:
    """One configuration key.

    `kind` is the value shape, not a Python type, so error messages can speak the user's language:
    `int`, `number` (int or float), `str`, `bool`, `duration`, `list`, `table`, `any`.
    `item` is the element shape of a list. `free` marks a table whose keys the user invents
    (native card settings, analysis options, a data map); its values are still checked.
    """

    kind: str
    default: Any = None
    doc: str = ""
    minimum: float | None = None
    maximum: float | None = None
    #: Allowed values, or a callable returning them. A callable is for a list that is not fixed at
    #: import time: `[generator].tool` reads the adapter registry, which a plugin (or a test) can
    #: add to after this module has been imported.
    choices: tuple[Any, ...] | Any = ()
    item: str = ""
    free: bool = False
    required: bool = False
    since: int = 2
    #: Value shapes accepted for a free table's values.
    value_kind: str = "any"

    def allowed(self) -> tuple[Any, ...]:
        """`choices`, resolved now rather than when this field was declared."""
        if callable(self.choices):
            return tuple(self.choices())
        return tuple(self.choices)

    def default_value(self) -> Any:
        if self.kind == "list":
            return list(self.default or [])
        if self.kind == "table":
            return dict(self.default or {})
        return self.default

    def describe(self) -> str:
        """One-line summary for the generated reference and for error hints."""
        parts = [self.kind]
        if self.item:
            parts.append(f"of {self.item}")
        allowed = self.allowed()
        if allowed:
            parts.append("one of " + ", ".join(repr(choice) for choice in allowed))
        if self.minimum is not None:
            parts.append(f"≥ {self.minimum:g}")
        if self.maximum is not None:
            parts.append(f"≤ {self.maximum:g}")
        return " ".join(parts)


def parse_duration(value: Any, where: str) -> float:
    """Seconds from a duration string or a number."""
    if isinstance(value, bool):
        raise HepError("must be a duration like '500ms', '30s', '5m'", where=where)
    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        match = DURATION.match(str(value).strip())
        if match is None:
            raise HepError(f"{value!r} is not a duration", where=where,
                           hint="use a number of seconds or a suffix: 500ms, 30s, 5m, 1h")
        seconds = float(match.group("amount")) * _UNIT_SECONDS[match.group("unit")]
    if seconds < 0:
        raise HepError("a duration cannot be negative", where=where)
    return seconds


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    return {int: "int", float: "float", str: "str", list: "list", dict: "table"}.get(type(value), type(value).__name__)


def check_scalar(kind: str, value: Any, where: str) -> Any:
    """One value of shape `kind`, or a HepError saying what was expected."""
    if kind == "any":
        return value
    if kind == "bool":
        if not isinstance(value, bool):
            raise HepError(f"must be true or false, not {_type_name(value)}", where=where)
        return value
    if kind == "int":
        # bool is an int in Python; in a config it is a different thing and must not slip through
        if isinstance(value, bool) or not isinstance(value, int):
            raise HepError(f"must be an integer, not {_type_name(value)}", where=where)
        return value
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HepError(f"must be a number, not {_type_name(value)}", where=where)
        return value
    if kind == "str":
        if not isinstance(value, str):
            raise HepError(f"must be a string, not {_type_name(value)}", where=where)
        return value
    if kind == "duration":
        return parse_duration(value, where)
    if kind == "scalar":
        if isinstance(value, (list, dict)):
            raise HepError(f"must be a single value, not a {_type_name(value)}", where=where)
        return value
    if kind == "table":
        if not isinstance(value, dict):
            raise HepError(f"must be a table, not {_type_name(value)}", where=where)
        return value
    if kind == "list":
        if not isinstance(value, list):
            raise HepError(f"must be a list, not {_type_name(value)}", where=where)
        return value
    raise AssertionError(f"unknown field kind {kind!r}")   # pragma: no cover - programming error


def check(spec: Field, value: Any, where: str) -> Any:
    """Check one configuration value against its field description and return it.

    The type is always checked. Choices and ranges are not applied to the field's own default, because
    several keys use an "unset" default that is deliberately outside them: `[sweep].style = ""` names no
    style, and `[beams].ids = []` means "not given" while a given list must hold exactly two ids. What
    makes an unset value unacceptable is the rule that needs it, which lives in `validate.py`.
    """
    if spec.kind == "list":
        items = check_scalar("list", value, where)
        checked = [check_scalar(spec.item or "any", item, f"{where}[{index}]")
                   for index, item in enumerate(items, start=1)]
        if checked != spec.default_value():
            _range_checked(spec, checked, where)
        return checked
    if spec.kind == "table":
        table = check_scalar("table", value, where)
        return {key: check_scalar(spec.value_kind, item, f"{where}.{key}") for key, item in table.items()}
    checked = check_scalar(spec.kind, value, where)
    if checked == spec.default_value() and not isinstance(checked, bool):
        return checked
    choices = spec.allowed()
    if choices and checked not in choices:
        allowed = ", ".join(repr(choice) for choice in choices)
        raise HepError(f"{checked!r} is not allowed", where=where, hint=f"use one of: {allowed}")
    _range_checked(spec, checked, where)
    return checked


def _range_checked(spec: Field, value: Any, where: str) -> None:
    if spec.kind == "list":
        if spec.minimum is not None and len(value) < spec.minimum:
            raise HepError(f"needs at least {spec.minimum:g} entries", where=where)
        if spec.maximum is not None and len(value) > spec.maximum:
            raise HepError(f"takes at most {spec.maximum:g} entries", where=where)
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return
    if spec.minimum is not None and value < spec.minimum:
        raise HepError(f"must be ≥ {spec.minimum:g}, not {value:g}", where=where)
    if spec.maximum is not None and value > spec.maximum:
        raise HepError(f"must be ≤ {spec.maximum:g}, not {value:g}", where=where)


@dataclass
class Section:
    """A group of fields: one TOML table, a list of tables, or a family of named tables."""

    name: str
    fields: dict[str, Field]
    #: "table" ([run]), "array" ([[sinks.module]]), "named" ([quantity.<name>])
    shape: str = "table"
    doc: str = ""
    #: machine.toml may set these keys (dotted, relative to the section); () means none
    machine_keys: tuple[str, ...] = ()
    #: accept keys the schema does not name, checked by the owner of the section
    free_keys: bool = False
    #: extra nested sections, e.g. [plot.data] under [plot]
    subsections: dict[str, "Section"] = dataclass_field(default_factory=dict)

    def field(self, key: str) -> Field | None:
        return self.fields.get(key)
