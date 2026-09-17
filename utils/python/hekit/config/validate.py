"""Checks that need more than one key (03 §6).

Everything here runs in `hep plan`, before any process starts. Messages name the file, the key and the
way out. Warnings are collected on the config rather than printed, so the caller decides how to show them.
"""

from __future__ import annotations

import re
from typing import Any

from ..errors import HepError, did_you_mean
from . import load as ld
from . import schema as sch

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SAFE_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

#: Schema-1 sections and where their contents went (03 §6).
SCHEMA_1_SECTIONS = {
    "analysis": "[run] plus [generator].card",
    "yoda": "[plot] and [plot.data]",
    "rivpyth": "[run].threads, [rivet].paths and [run].name",
}


def require_schema(resolved: ld.Resolved, path: Any) -> None:
    """`schema = 2` must be present; a schema-1 file gets a migration hint instead of key errors."""
    declared = resolved.values.get(("schema",))
    if declared == sch.SCHEMA_VERSION:
        return
    old = sorted(section for section in SCHEMA_1_SECTIONS
                 if any(key[0] == section for key in resolved.values))
    if declared is None and old:
        raise HepError(
            f"this looks like a schema-1 file ({', '.join('[' + name + ']' for name in old)})",
            where=str(path),
            hint=f"run 'hep config migrate {path}'; " +
                 "; ".join(f"[{name}] → {target}" for name, target in SCHEMA_1_SECTIONS.items() if name in old))
    if declared is None:
        raise HepError("missing 'schema = 2'", where=str(path),
                       hint="every run TOML starts with schema = 2")
    raise HepError(f"unsupported schema version {declared!r}", where=str(path),
                   hint=f"this hekit reads schema {sch.SCHEMA_VERSION}")


def check_name(name: str, family: str, where: str) -> None:
    if not NAME.fullmatch(name):
        raise HepError(f"'{name}' is not a valid {family} name", where=where,
                       hint="use letters, digits and underscores, starting with a letter")


def check_quantity(quantity: Any, where: str) -> None:
    """The shape of one catalogue entry; what it *means* is P1-S03."""
    label = f"[quantity.{quantity.name}]"
    if not quantity.type:
        raise HepError(f"{label} needs a type", where=where,
                       hint="one of: " + ", ".join(sch.QUANTITY.fields["type"].choices))
    if not quantity.values:
        raise HepError(f"{label} needs a non-empty values list", where=where)
    count = len(quantity.values)
    for key in ("labels", "tags"):
        items = getattr(quantity, key)
        if items and len(items) != count:
            raise HepError(f"{label} {key} has {len(items)} entries for {count} values", where=where)
    for tag in quantity.tags:
        if not SAFE_TAG.fullmatch(tag):
            raise HepError(f"{label} tag {tag!r} is not filename-safe", where=where,
                           hint="letters, digits, dot, dash and underscore; must start with a letter or digit")
    if len(set(quantity.tags)) != len(quantity.tags):
        raise HepError(f"{label} tags must be unique", where=where)
    if quantity.use > count:
        raise HepError(f"{label} use = {quantity.use} is outside 1..{count}", where=where)

    if quantity.side and quantity.type != "beams":
        raise HepError(f"{label} side applies only to type = \"beams\"", where=where)
    if quantity.option and quantity.type != "option":
        raise HepError(f"{label} option applies only to type = \"option\"", where=where)
    if quantity.type == "option" and not quantity.option:
        raise HepError(f"{label} needs the option name", where=where,
                       hint="option = \"R\", as the analysis declares it")
    if quantity.type == "setting" and quantity.key is None:
        raise HepError(f"{label} needs a key", where=where,
                       hint='key = "PDF:pSet", or a per-tool table key = { pythia = "PDF:pSet" }')
    if quantity.key is not None and quantity.type not in {"setting", "generator"}:
        raise HepError(f"{label} key applies only to type = \"setting\"", where=where)
    if isinstance(quantity.key, dict):
        for tool in quantity.key:
            if tool not in sch.GENERATOR.fields["tool"].choices:
                raise HepError(f"{label} key has no such tool '{tool}'", where=where,
                               hint=did_you_mean(tool, sch.GENERATOR.fields["tool"].choices))

    if quantity.type == "beams":
        for value in quantity.values:
            _check_beam_value(value, quantity.side, f"{label} values", where)
    if quantity.type == "energies":
        for value in quantity.values:
            _check_energy_value(value, f"{label} values", where)
    if quantity.type == "seed":
        for value in quantity.values:
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 900_000_000:
                raise HepError(f"{label} seeds must be integers in 1..900000000", where=where)
    if quantity.type == "events":
        for value in quantity.values:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise HepError(f"{label} event counts must be positive integers", where=where)
    if quantity.type == "generator":
        for value in quantity.values:
            if not isinstance(value, dict) or "tool" not in value:
                raise HepError(f"{label} values must be tables with a tool", where=where,
                               hint='values = [{ tool = "pythia", card = "a.cmnd" }, …]')
            if value["tool"] not in sch.GENERATOR.fields["tool"].choices:
                raise HepError(f"{label} has no such tool '{value['tool']}'", where=where,
                               hint=did_you_mean(value["tool"], sch.GENERATOR.fields["tool"].choices))
    if quantity.type == "option":
        for value in quantity.values:
            text = str(value)
            if isinstance(value, (list, dict)) or ":" in text or "=" in text:
                raise HepError(f"{label} option values must be scalars without ':' or '='", where=where)


def _check_beam_value(value: Any, side: str, label: str, where: str) -> None:
    """A beams value is a PDG id pair, or one id when `side` says which beam varies."""
    def is_id(item: Any) -> bool:
        return isinstance(item, int) and not isinstance(item, bool) and item != 0

    if isinstance(value, str):
        raise HepError(f"{label}: particle names are not accepted, use PDG ids", where=where,
                       hint="e- is 11, e+ is -11, p is 2212, gamma is 22")
    if side:
        if not is_id(value):
            raise HepError(f"{label}: with side = \"{side}\" each value is one PDG id", where=where,
                           hint="for example values = [11, -11]")
        return
    if not (isinstance(value, list) and len(value) == 2 and all(is_id(item) for item in value)):
        raise HepError(f"{label}: each value is [idA, idB] of non-zero PDG ids", where=where,
                       hint='or set side = "a"/"b" and give single ids')


def _check_energy_value(value: Any, label: str, where: str) -> None:
    def positive(item: Any) -> bool:
        return isinstance(item, (int, float)) and not isinstance(item, bool) and item > 0

    if isinstance(value, list):
        if len(value) != 2 or not all(positive(item) for item in value):
            raise HepError(f"{label}: an energy pair is [E_A, E_B], both positive (GeV)", where=where)
        return
    if not positive(value):
        raise HepError(f"{label}: an energy is [E_A, E_B] or a positive √s (GeV)", where=where)


def _mentioned_quantities(entries: Any) -> list[str]:
    """Quantity names in an `across` list, without interpreting the grouping (that is P1-S03)."""
    names: list[str] = []
    for entry in entries or []:
        pieces = entry if isinstance(entry, list) else [entry]
        for piece in pieces:
            names.extend(part.strip() for part in str(piece).replace(",", "+").split("+") if part.strip())
    return names


def cross_check(config: Any) -> None:
    """Checks across sections; appends to `config.warnings` where a value is legal but suspicious."""
    where = str(config.path)
    generator, beams = config.generator, config.beams

    # generator wiring
    if generator.tool == "store":
        if not generator.input:
            raise HepError("[generator] tool = \"store\" needs input", where=where,
                           hint="input = a point name, 'sha256:…', or a path to an events/ directory")
        if generator.card:
            raise HepError("[generator] a store replays recorded events, so card does not apply", where=where)
    else:
        if generator.input:
            raise HepError(f"[generator] input applies only to tool = \"store\", not \"{generator.tool}\"",
                           where=where)
        if not generator.card:
            raise HepError(f"[generator] tool = \"{generator.tool}\" needs its native card", where=where,
                           hint="card = \"photo_ep.cmnd\", relative to this file")
    if generator.shower and generator.tool != "madgraph":
        raise HepError("[generator] shower applies only to tool = \"madgraph\"", where=where)

    # beams
    if beams.ids:
        for item in beams.ids:
            if item == 0:
                raise HepError("[beams] ids must be non-zero PDG ids", where=where)
    if beams.energies is not None:
        _check_energy_value(beams.energies, "[beams] energies", where)
        if not isinstance(beams.energies, list) and beams.ids and len(set(beams.ids)) > 1:
            config.warnings.append(
                "[beams] a scalar energy is √s in the CM frame, but the beams differ "
                f"({beams.ids}): events are generated in the CM frame, so lab-frame η observables shift")

    # analyses and sinks
    if config.rivet.mode == "native" and generator.tool != "sherpa":
        raise HepError("[rivet] mode = \"native\" is only available for Sherpa", where=where,
                       hint="use the in-process sink: mode = \"inprocess\"")
    if not isinstance(config.rivet.xsec, str):
        if isinstance(config.rivet.xsec, bool) or not isinstance(config.rivet.xsec, (int, float)) \
                or config.rivet.xsec <= 0:
            raise HepError("[rivet] xsec must be \"generator\" or a positive cross-section in pb", where=where)
    elif config.rivet.xsec != "generator":
        raise HepError(f"[rivet] xsec {config.rivet.xsec!r} is not understood", where=where,
                       hint="\"generator\", or a number in pb")
    if not config.rivet.analyses and not config.module_sinks and not config.store.enabled \
            and not any(quantity.type == "analysis" for quantity in config.quantities.values()):
        raise HepError("nothing would consume the events", where=where,
                       hint="set [rivet].analyses, add a [[sinks.module]], or enable [store]")

    # plotting
    swept = _mentioned_quantities(config.sweep.across)
    for name in swept:
        config.quantity(name)
    if config.sweep.overlay:
        config.quantity(config.sweep.overlay)
        if config.sweep.overlay not in swept:
            raise HepError(f"[sweep] overlay '{config.sweep.overlay}' is not in across", where=where,
                           hint=f"across lists: {', '.join(swept) or 'nothing'}")
    if config.plot.merge == "yodamerge":
        kinds = {config.quantity(name).type for name in swept}
        if not swept or kinds != {"seed"}:
            raise HepError("[plot] merge = \"yodamerge\" only combines statistically equivalent runs",
                           where=where, hint="every scanned quantity must have type = \"seed\"")
    if config.plot.data.show is False and config.plot.data.reference is False and config.plot.data.file:
        raise HepError("[plot.data] show = false needs reference = true", where=where,
                       hint="otherwise the data is neither drawn nor used as the ratio denominator")
    if config.plot.data.file and not config.plot.data.map:
        config.warnings.append(
            "[plot.data] no map: reference objects are matched by histogram name only, which overlays "
            "unrelated observables that happen to share a name (00/B5)")

    # studies
    for study in config.studies.values():
        for name in _mentioned_quantities(study.across):
            config.quantity(name)
        if study.overlay:
            config.quantity(study.overlay)
            if study.overlay not in _mentioned_quantities(study.across):
                raise HepError(f"[study.{study.name}] overlay '{study.overlay}' is not in its own across",
                               where=where, hint=f"its across lists: "
                                                 f"{', '.join(_mentioned_quantities(study.across)) or 'nothing'}")
        for name in study.pin:
            config.quantity(name)
    for name in config.settle.use:
        config.quantity(name)

    # processing
    for fit in config.proc_fits:
        if fit["range"] and fit["range"][0] >= fit["range"][1]:
            raise HepError(f"[[proc.fit]] {fit['name']}: range must be [low, high] with low < high", where=where)
    for hist in config.proc_hists:
        if hist["bins"]:
            count, low, high = hist["bins"]
            if count <= 0 or low >= high:
                raise HepError(f"[[proc.hist]] {hist['name']}: bins are [n, low, high] with n > 0 and low < high",
                               where=where)
