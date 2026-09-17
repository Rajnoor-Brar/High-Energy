"""Turning a selection into fully specified points (03 §4).

A `Point` says everything about one run except the seed and the hash (P1-S04) and the native card text
(P1-S05). Generation-side values stay structured — beams, energies, events, native settings — so that
each adapter renders them in its own language.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from ..errors import HepError
from . import quantity as qt
from .select import Selection


@dataclass(frozen=True)
class Assignment:
    """One native setting the point asks for, and who asked."""

    key: str
    value: Any
    origin: str


@dataclass
class Point:
    """One run of one event sample with one set of analyses."""

    number: int                                   # 1-based position in this expansion
    name: str                                     # run name plus the tags of the applied quantities
    suffix: str                                   # just the tags
    #: the name of the *events* this point needs: the analysis-side tags are left out, because an
    #: option variant analyses the same sample (03 §4)
    generation_name: str = ""
    #: quantity name → zero-based value index, for every applied quantity
    choice: dict[str, int] = dataclass_field(default_factory=dict)
    #: native generator settings, in application order
    settings: list[Assignment] = dataclass_field(default_factory=list)
    beams: list[int] | None = None                # PDG ids [A, B]
    energies: Any = None                          # [E_A, E_B] or a scalar √s
    events: int | None = None
    seed: int | None = None                       # only when a seed quantity is applied
    cards: list[str] = dataclass_field(default_factory=list)      # extra native fragments
    generator: dict[str, Any] | None = None       # tool/card override from a `generator` quantity
    analyses: list[str] = dataclass_field(default_factory=list)   # "NAME:OPT=VALUE:…"
    legend: str = ""
    page: tuple[tuple[str, int], ...] = ()
    #: the analysis-side choices only, used to group points that share one generation (03 §4)
    analysis_choice: dict[str, int] = dataclass_field(default_factory=dict)

    @property
    def generation_choice(self) -> dict[str, int]:
        return {name: index for name, index in self.choice.items() if name not in self.analysis_choice}


def _claim(settings: list[Assignment], owners: dict[str, str], key: str, value: Any, origin: str) -> None:
    """Record one native setting; two different sources setting the same key is an error."""
    normalised = "".join(key.split()).lower()
    if normalised in owners and owners[normalised] != origin:
        raise HepError(f"native setting '{key}' is set by both {owners[normalised]} and {origin}",
                       hint="declare it as a quantity and pin it, so one source owns it")
    owners[normalised] = origin
    settings.append(Assignment(key, value, origin))


def _setting_key(quantity: Any, tool: str) -> str:
    """The native key for a `setting` quantity under the active tool (03 §3)."""
    if isinstance(quantity.key, dict):
        key = quantity.key.get(tool)
        if key is None:
            raise HepError(f"[quantity.{quantity.name}] has no key for tool '{tool}'",
                           hint=f"keys given for: {', '.join(sorted(quantity.key))}")
        return str(key)
    return str(quantity.key)


def _analysis_entries(config: Any, options: dict[str, dict[str, Any]], analyses: list[str]) -> list[str]:
    """Analysis names with their options, sorted the way Rivet writes them."""
    entries = []
    for name in analyses:
        base, *declared = name.split(":")
        merged = {}
        for piece in declared:                      # options written into [rivet].analyses itself
            key, _, value = piece.partition("=")
            merged[key] = value
        merged.update({key: qt.text_value(value) for key, value in options.get("", {}).items()})
        merged.update({key: qt.text_value(value) for key, value in options.get(base, {}).items()})
        entries.append(":".join([base, *(f"{key}={value}" for key, value in sorted(merged.items()))]))
    return entries


def build_point(config: Any, selection: Selection, number: int, choice: dict[str, int]) -> Point:
    """One point from a set of value choices."""
    settings: list[Assignment] = []
    owners: dict[str, str] = {}
    tool = config.generator.tool
    style = config.output.tag_style

    beams = list(config.beams.ids) if config.beams.ids else None
    energies = config.beams.energies
    events = config.run.events or None
    seed: int | None = None
    cards: list[str] = []
    generator: dict[str, Any] | None = None
    # option target "" means every analysis
    options: dict[str, dict[str, Any]] = {"": dict(config.rivet.options)}
    analyses = list(config.rivet.analyses)

    for key, value in config.settle.gen.items():
        _claim(settings, owners, key, value, "[settle.gen]")
    for key, value in config.settle.ana.items():
        options[""][key] = value

    tags: list[str] = []
    generation_tags: list[str] = []
    analysis_choice: dict[str, int] = {}
    for name, quantity in config.quantities.items():       # catalogue order
        if name not in choice:
            continue
        index = choice[name]
        value = quantity.values[index]
        origin = f"[quantity.{name}]"
        if quantity.type == "setting":
            _claim(settings, owners, _setting_key(quantity, tool), value, origin)
        elif quantity.type == "beams":
            if quantity.side:
                beams = list(beams or [0, 0])
                beams[0 if quantity.side == "a" else 1] = value
            else:
                beams = list(value)
        elif quantity.type == "energies":
            energies = value
        elif quantity.type == "seed":
            seed = value
        elif quantity.type == "events":
            events = value
        elif quantity.type == "card":
            cards.append(value)
        elif quantity.type == "generator":
            generator = dict(value)
            tool = generator.get("tool", tool)
        elif quantity.type == "analysis":
            analyses = [value]
            analysis_choice[name] = index
        elif quantity.type == "option":
            options.setdefault(quantity.target, {})[quantity.option] = value
            analysis_choice[name] = index
        rendered_tag = qt.tag(quantity, index, style)
        tags.append(rendered_tag)
        if name not in analysis_choice:
            generation_tags.append(rendered_tag)

    if config.settle.tag:
        tags.append(config.settle.tag)
        generation_tags.append(config.settle.tag)

    suffix = "_".join(part for part in tags if part)
    generation_suffix = "_".join(part for part in generation_tags if part)
    stem = config.run.name
    legend_quantities = [name for name in selection.scanned if config.quantities[name].in_legend]
    legend = ", ".join(qt.legend(config.quantities[name], choice[name], config.plot.legends)
                       for name in legend_quantities)
    page = tuple((name, choice[name]) for group in selection.groups
                 if group != selection.overlay for name in group)
    return Point(
        number=number,
        name="_".join(part for part in (stem, suffix) if part) or stem or "point",
        suffix=suffix,
        generation_name="_".join(part for part in (stem, generation_suffix) if part) or stem or "point",
        choice=dict(choice),
        settings=settings,
        beams=beams,
        energies=energies,
        events=events,
        seed=seed,
        cards=cards,
        generator=generator,
        analyses=_analysis_entries(config, options, analyses),
        legend=legend,
        page=page,
        analysis_choice=analysis_choice,
    )


def expand(config: Any, selection: Selection, index: int | None = None) -> list[Point]:
    """Every point of the selection, or just one (1-based)."""
    ranges = [range(len(config.quantity(group[0]).values)) for group in selection.groups]
    points: list[Point] = []
    for number, combination in enumerate(itertools.product(*ranges), start=1):
        choice = dict(selection.uses)
        for group, value_index in zip(selection.groups, combination):
            for name in group:
                choice[name] = value_index
        points.append(build_point(config, selection, number, choice))

    names = [point.name for point in points]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise HepError(f"these points share a name: {', '.join(duplicates)}", where=str(config.path),
                       hint="give the scanned quantities distinct tags, or set [output] tag_style = \"index\"")

    wanted = index if index is not None else (selection.only or None)
    if wanted is not None:
        if not 1 <= wanted <= len(points):
            raise HepError(f"point {wanted} is outside the scan (1..{len(points)})", where=str(config.path))
        return [points[wanted - 1]]
    return points
