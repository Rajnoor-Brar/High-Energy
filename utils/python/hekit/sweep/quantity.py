"""What one catalogue entry contributes: text, tags, legends and selection (03 §3).

The schema has already checked the shape of a `[quantity.<name>]` table (P1-S02); this module gives it
behaviour. Values stay Python objects for as long as possible: the native card syntax is the adapter's
business (P1-S05), so nothing here formats a card line.
"""

from __future__ import annotations

from typing import Any

from ..errors import HepError, did_you_mean

#: Types that change the generated events, and types that only change the analysis (03 §3).
GENERATION_TYPES = frozenset({"setting", "beams", "energies", "seed", "card", "generator", "events"})
ANALYSIS_TYPES = frozenset({"analysis", "option"})

#: A selector prefixed like this is a 1-based index into the values (D-B22).
INDEX_PREFIX = "#"


def text_value(value: Any) -> str:
    """A value as text, losslessly (00/B9).

    The legacy tools used `%g`, which silently rounded: 0.123456789 became 0.123457, and two distinct
    values could end up with the same tag and the same file name. `repr` keeps every float exactly,
    integers stay integers, and booleans read as on/off the way a physicist writes them in a card.
    """
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        # repr is the shortest text that round-trips; 3.0 stays "3.0", 0.1+0.2 stays visible
        return repr(value)
    if isinstance(value, list):
        return "x".join(text_value(item) for item in value)
    if isinstance(value, dict):
        return ",".join(f"{key}={text_value(item)}" for key, item in sorted(value.items()))
    return str(value)


def sanitise(text: str) -> str:
    """Filename-safe form of a value text, for a tag that has no declared tag."""
    import re

    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-") or "x"


def value_text(quantity: Any, index: int) -> str:
    return text_value(quantity.values[index])


def label(quantity: Any, index: int) -> str:
    if quantity.labels:
        return quantity.labels[index]
    return f"{quantity.name} = {value_text(quantity, index)}"


def tag(quantity: Any, index: int, style: str) -> str:
    """The piece of a point name this value contributes."""
    if style == "index":
        return f"{quantity.name}{index + 1:02d}"
    if style == "tag" and quantity.tags:
        return quantity.tags[index]
    return sanitise(value_text(quantity, index))


def legend(quantity: Any, index: int, style: str) -> str:
    if style == "tag":
        return tag(quantity, index, "tag")
    if style == "value":
        return value_text(quantity, index)
    return label(quantity, index)


def is_generation(quantity: Any) -> bool:
    return quantity.type in GENERATION_TYPES


def as_number(value: Any) -> float | None:
    """The value as a float when it is numeric (or numeric text), else None. Booleans are not numbers."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def resolve_selector(quantity: Any, selector: Any, where: str) -> int:
    """Zero-based index of the value a pin names (00/B22).

    Resolution order, in this order and no other:
    1. a declared **tag**;
    2. an exact **value** — as text, and numerically when both sides are numbers, so 6, 6.0 and "6"
       all find a stored 6.0;
    3. `"#N"`, an explicit 1-based **index**.

    The legacy rule ("all digits means an index") made numeric values impossible to pin: `--pin
    pthatmin=6` selected the sixth entry rather than the value 6. Indices now need the `#` prefix, and a
    selector that matches nothing says so, listing the tags and values that exist.
    """
    if isinstance(selector, str) and selector.startswith(INDEX_PREFIX):
        return _index_selector(quantity, selector[len(INDEX_PREFIX):], where)
    if quantity.tags and selector in quantity.tags:
        return quantity.tags.index(selector)
    wanted, number = text_value(selector), as_number(selector)
    for index, value in enumerate(quantity.values):
        if value_text(quantity, index) == wanted:
            return index
        # 6 finds a stored 6.0: a physicist writes the value, not its spelling
        if number is not None and as_number(value) == number:
            return index
    tags = ", ".join(quantity.tags) if quantity.tags else "none"
    values = ", ".join(value_text(quantity, index) for index in range(len(quantity.values)))
    hint = did_you_mean(str(selector), [*quantity.tags, values.split(", ")[0]])
    raise HepError(f"{selector!r} matches no tag or value of '{quantity.name}'", where=where,
                   hint=(hint + " " if hint else "") +
                        f"tags: {tags}; values: {values}; or an index as '{INDEX_PREFIX}N'")


def _index_selector(quantity: Any, text: str, where: str) -> int:
    count = len(quantity.values)
    try:
        number = int(text)
    except ValueError:
        raise HepError(f"'{INDEX_PREFIX}{text}' is not an index of '{quantity.name}'", where=where,
                       hint=f"use {INDEX_PREFIX}1 … {INDEX_PREFIX}{count}") from None
    if not 1 <= number <= count:
        raise HepError(f"index {number} is outside 1..{count} for '{quantity.name}'", where=where)
    return number - 1


def use_index(quantity: Any) -> int | None:
    """Zero-based index applied when the quantity is not scanned, or None to leave the card alone."""
    return quantity.use - 1 if quantity.use else None
