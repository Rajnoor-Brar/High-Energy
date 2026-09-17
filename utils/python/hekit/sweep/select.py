"""Choosing what varies: across groups, overlay, settle, studies and pins (03 §4).

Precedence follows 03 §2: the file's `[sweep]`, then `--study`, then `[settle.use]` and the study's
`pin`, then `--pin`, then the `--across` / `--style` / `--overlay` overrides. Validation runs **after**
all of it (00/B7): the legacy tools validated the file and then let a study change the scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import Any

from ..errors import HepError, did_you_mean
from . import quantity as qt


@dataclass
class Selection:
    """The resolved answer to "what varies, what is fixed, and what is drawn together"."""

    #: Scanned groups, in order; the quantities inside one group move together (coupled by index).
    groups: list[list[str]] = dataclass_field(default_factory=list)
    #: The group drawn as curves on one page; the other groups become pages.
    overlay: list[str] = dataclass_field(default_factory=list)
    #: quantity name → zero-based value index, for quantities that are applied but not scanned.
    uses: dict[str, int] = dataclass_field(default_factory=dict)
    #: Where each pin came from, for provenance and error messages.
    origins: dict[str, str] = dataclass_field(default_factory=dict)
    study: str = ""
    only: int = 0

    @property
    def scanned(self) -> list[str]:
        return [name for group in self.groups for name in group]

    def is_scanned(self, name: str) -> bool:
        return name in self.scanned


def parse_across(text: str) -> list[list[str]]:
    """CLI form: ',' separates groups, '+' couples quantities inside a group."""
    groups = [[name.strip() for name in part.split("+") if name.strip()] for part in text.split(",")]
    if not groups or any(not group for group in groups):
        raise HepError(f"--across {text!r} has an empty group", where="--across",
                       hint="for example 'energies+beams,pdf'")
    return groups


def normalise_across(entries: Any, style: str, where: str) -> list[list[str]]:
    """`[sweep].across` / a study's `across` into groups.

    A list entry that is itself a list is a coupled group. A string entry may use '+' to couple, which
    keeps the TOML readable: `across = ["energies+beams", "pdf"]`.
    """
    groups: list[list[str]] = []
    for entry in entries or []:
        if isinstance(entry, list):
            groups.append([str(name).strip() for name in entry])
        else:
            groups.append([name.strip() for name in str(entry).split("+") if name.strip()])
    if any(not group for group in groups):
        raise HepError("an across entry is empty", where=where)
    if style:
        if any(len(group) > 1 for group in groups):
            raise HepError("style applies only to a flat across list", where=where,
                           hint="with coupled groups ('a+b'), lists already say what moves together")
        flat = [name for group in groups for name in group]
        groups = [flat] if style == "together" and flat else [[name] for name in flat]
    return groups


def _check_groups(config: Any, groups: list[list[str]], where: str) -> None:
    seen: set[str] = set()
    for group in groups:
        lengths = {}
        for name in group:
            quantity = config.quantity(name)
            if name in seen:
                raise HepError(f"'{name}' is scanned twice", where=where)
            seen.add(name)
            lengths[name] = len(quantity.values)
        if len(set(lengths.values())) > 1:
            detail = ", ".join(f"{name}={count}" for name, count in lengths.items())
            raise HepError(f"coupled quantities need equal value counts ({detail})", where=where,
                           hint="separate them into their own groups to form a grid instead")


def _pick_overlay(config: Any, groups: list[list[str]], wanted: str, where: str) -> list[str]:
    """The group drawn as curves: the named quantity's group, else the last group."""
    if not groups:
        return []
    if not wanted:
        return list(groups[-1])
    config.quantity(wanted)
    for group in groups:
        if wanted in group:
            return list(group)
    raise HepError(f"overlay '{wanted}' is not scanned", where=where,
                   hint=f"across lists: {', '.join(name for group in groups for name in group) or 'nothing'}")


def _apply_pins(config: Any, selection: Selection, pins: dict[str, Any], where: str) -> None:
    for name, selector in pins.items():
        quantity = config.quantity(name)
        selection.uses[name] = qt.resolve_selector(quantity, selector, where)
        selection.origins[name] = where


def parse_pin(text: str) -> tuple[str, Any]:
    """`--pin name=selector`; the selector stays text, so tags, values and '#N' all work (00/B22)."""
    name, separator, selector = text.partition("=")
    if not separator or not name.strip() or not selector.strip():
        raise HepError(f"--pin expects quantity=tag-or-value, got {text!r}", where="--pin",
                       hint="for example --pin energies=18x275, --pin pthatmin=6, --pin pdf=#2")
    return name.strip(), selector.strip()


def select(config: Any, *, study: str | None = None, pins: tuple[str, ...] = (),
           across: str | None = None, style: str | None = None, overlay: str | None = None,
           only: int | None = None) -> Selection:
    """Resolve the scan for one command invocation.

    `--overlay` alone never re-groups the scan (00/B6): the legacy tools rebuilt the groups from a flat
    list of names whenever any of these options was given, which silently uncoupled `a+b` groups.
    """
    where = str(config.path)
    selection = Selection(only=config.sweep.only if only is None else only)

    # 1. the file's own scan
    groups = normalise_across(config.sweep.across, config.sweep.style, f"{where} [sweep].across")
    wanted_overlay = config.sweep.overlay

    # 2. the study replaces the scan and adds its pins
    if study:
        chosen = config.studies.get(study)
        if chosen is None:
            raise HepError(f"unknown study '{study}'", where=where,
                           hint=did_you_mean(study, config.studies) or
                                f"available: {', '.join(sorted(config.studies)) or 'none'}")
        groups = normalise_across(chosen.across, chosen.style, f"{where} [study.{study}].across")
        wanted_overlay = chosen.overlay
        selection.study = study

    # 3. catalogue defaults, then the file's pins, then the study's
    for name, quantity in config.quantities.items():
        index = qt.use_index(quantity)
        if index is not None:
            selection.uses[name] = index
            selection.origins[name] = f"[quantity.{name}].use"
    _apply_pins(config, selection, config.settle.use, f"{where} [settle.use]")
    if study:
        _apply_pins(config, selection, config.studies[study].pin, f"{where} [study.{study}].pin")

    # 4. command-line pins
    if pins:
        _apply_pins(config, selection, dict(parse_pin(text) for text in pins), "--pin")

    # 5. command-line scan overrides
    if across is not None:
        groups = parse_across(across)
        if style:
            groups = normalise_across([name for group in groups for name in group], style, "--across")
    elif style:
        groups = normalise_across([name for group in groups for name in group], style, "--style")
    if overlay is not None:
        wanted_overlay = overlay

    _check_groups(config, groups, f"{where} across")
    selection.groups = groups
    selection.overlay = _pick_overlay(config, groups, wanted_overlay, f"{where} overlay")

    # a scanned quantity is never also pinned
    for name in selection.scanned:
        selection.uses.pop(name, None)
        selection.origins.pop(name, None)

    validate_selection(config, selection)
    return selection


def validate_selection(config: Any, selection: Selection) -> None:
    """Rules that depend on the selection, re-checked after study and pins (00/B7)."""
    where = str(config.path)
    if config.plot.merge == "yodamerge":
        kinds = {config.quantity(name).type for name in selection.scanned}
        if kinds != {"seed"}:
            raise HepError("[plot] merge = \"yodamerge\" only combines statistically equivalent runs",
                           where=where,
                           hint=f"every scanned quantity must have type = \"seed\"; this scan has "
                                f"{', '.join(sorted(kinds)) or 'none'}")
    if selection.only and not 1 <= selection.only <= expected_point_count(config, selection):
        raise HepError(f"[sweep] only = {selection.only} is outside the scan "
                       f"(1..{expected_point_count(config, selection)})", where=where)
    sides = [name for name in selection.scanned + list(selection.uses)
             if config.quantity(name).type == "beams"]
    if len(sides) > 1:
        with_side = [name for name in sides if config.quantity(name).side]
        if with_side and len(sides) > len(with_side):
            raise HepError("a one-sided beams quantity clashes with a pair-valued one "
                           f"({', '.join(sides)})", where=where,
                           hint="give every beams quantity a side, or use a single pair-valued quantity")


def expected_point_count(config: Any, selection: Selection) -> int:
    count = 1
    for group in selection.groups:
        count *= len(config.quantity(group[0]).values)
    return count
