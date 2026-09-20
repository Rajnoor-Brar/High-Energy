"""Pythia: card parsing, rendering and validation (04 §3).

The base card is never touched. Everything the plan decides goes into a generated **point card** that
Pythia reads after it, so later settings win — the base + point design that already works, with the
header made honest: it records the base card's sha256, where the point came from, and its identity.
"""

from __future__ import annotations

import re
from typing import Any

from ..errors import HepError
from ..sweep.quantity import text_value

NAME = "pythia"

#: `Key:name = value`, with `!` or `#` starting a comment.
SETTING = re.compile(r"^\s*([A-Za-z0-9_:]+)\s*=\s*([^!#]*)")

#: Keys the plan owns; a card or an override that sets them is a planning error (04 §3).
RESERVED = {
    "beams:ida": "[beams] ids",
    "beams:idb": "[beams] ids",
    "beams:ecm": "[beams] energies",
    "beams:ea": "[beams] energies",
    "beams:eb": "[beams] energies",
    "beams:frametype": "[beams] ids and energies",
    "main:numberofevents": "[run] events",
    "parallelism:numthreads": "[run] threads",
    "parallelism:seeds": "[run] seed (the seed block is derived from the point identity)",
    "random:seed": "[run] seed",
    "random:setseed": "[run] seed",
}
#: Set by the sink concurrency mode, never by a user card (04 §3, 05 §3).
FORBIDDEN_IN_CARD = {"parallelism:processasync": "the concurrency mode is chosen by hep, not by the card"}


def normalise_key(key: str) -> str:
    return "".join(str(key).split()).lower()


def card_defaults(text: str) -> dict[str, str]:
    """Every setting a card applies, as `normalised key → value text` (later lines win)."""
    defaults: dict[str, str] = {}
    for line in text.splitlines():
        match = SETTING.match(line)
        if match and match.group(2).strip():
            defaults[normalise_key(match.group(1))] = match.group(2).strip()
    return defaults


def card_value(value: Any) -> str:
    """One value as Pythia writes it: on/off for booleans, lossless for numbers (00/B9)."""
    return text_value(value)


def check_card(text: str, where: str) -> None:
    """A base card may not set what the plan owns."""
    for key in card_defaults(text):
        if key in FORBIDDEN_IN_CARD:
            raise HepError(f"the base card sets {key}", where=where, hint=FORBIDDEN_IN_CARD[key])


def check_overrides(point: Any, where: str) -> None:
    """A quantity or `[settle.gen]` may not set what the plan owns (04 §3)."""
    for assignment in point.settings:
        key = normalise_key(assignment.key)
        if key in RESERVED:
            raise HepError(f"'{assignment.key}' is set by {assignment.origin}, but hep owns it",
                           where=where, hint=f"use {RESERVED[key]} instead")
        if key in FORBIDDEN_IN_CARD:
            raise HepError(f"'{assignment.key}' is set by {assignment.origin}", where=where,
                           hint=FORBIDDEN_IN_CARD[key])


def beam_settings(point: Any) -> list[tuple[str, Any, str]]:
    """`[beams]` as Pythia settings (04 §3), with the frame type implied by the energies."""
    rendered: list[tuple[str, Any, str]] = []
    if point.beams:
        rendered.append(("Beams:idA", point.beams[0], "[beams] ids"))
        rendered.append(("Beams:idB", point.beams[1], "[beams] ids"))
    energies = point.energies
    if energies is None:
        return rendered
    if isinstance(energies, list):
        rendered.append(("Beams:frameType", 2, "[beams] energies"))
        rendered.append(("Beams:eA", energies[0], "[beams] energies"))
        rendered.append(("Beams:eB", energies[1], "[beams] energies"))
    else:
        rendered.append(("Beams:frameType", 1, "[beams] energies"))
        rendered.append(("Beams:eCM", energies, "[beams] energies"))
    return rendered


def frame_warning(point: Any) -> str:
    """A scalar √s with different beams generates in the CM frame, which shifts η (04 §3)."""
    if point.energies is not None and not isinstance(point.energies, list) \
            and point.beams and len(set(point.beams)) > 1:
        return (f"{point.name}: energies is a single √s with beams {point.beams}, so events are "
                "generated in the CM frame; lab-frame η observables shift")
    return ""


def run_settings(point: Any, seeds: Any, threads: int) -> list[tuple[str, Any, str]]:
    """Run control the plan owns (04 §3)."""
    rendered: list[tuple[str, Any, str]] = []
    if point.events:
        rendered.append(("Main:numberOfEvents", point.events, "[run] events"))
    if threads:
        rendered.append(("Parallelism:numThreads", threads, "[run] threads"))
    rendered.append(("Random:setSeed", True, "[run] seed"))
    rendered.append(("Random:seed", seeds.point, "identity seed"))
    if threads and threads > 1:
        # one disjoint seed per instance, so neighbouring points never share a stream (00/B2)
        rendered.append(("Parallelism:seeds", ",".join(str(seed) for seed in seeds.instances),
                         "identity seed block"))
    rendered.append(("Next:numberCount", 0, "progress comes from the status stream"))
    rendered.append(("Init:showChangedSettings", True, "recorded in logs/generate.log"))
    return rendered


def render_card(point: Any, *, seeds: Any, threads: int, card_path: str, card_sha: str,
                identity_hash: str, origin: str, **_: Any) -> str:
    """The point card: header, run control, beams, then the overrides grouped by origin.

    `**_` swallows what only an external adapter needs — where its FIFO is, which Rivet mode is in
    force — because the planner hands every adapter the same context and Pythia's events never leave
    the process.
    """
    lines = [
        "! hekit point card (generated) — read after the base card, so these settings win",
        f"! origin     : {origin}",
        f"! base card  : {card_path}",
        f"! base sha256: {card_sha}",
        f"! point      : {point.name}",
        f"! identity   : {identity_hash}",
        f"! analyses   : {', '.join(point.analyses) or 'none'}",
    ]
    groups: list[tuple[str, list[tuple[str, Any, str]]]] = [
        ("run control", run_settings(point, seeds, threads)),
        ("beams", beam_settings(point)),
    ]
    overrides: dict[str, list[tuple[str, Any, str]]] = {}
    for assignment in point.settings:
        overrides.setdefault(assignment.origin, []).append(
            (assignment.key, assignment.value, assignment.origin))
    groups += list(overrides.items())

    for title, settings in groups:
        if not settings:
            continue
        lines += ["", f"! from {title}"]
        lines += [f"{key} = {card_value(value)}" for key, value, _ in settings]
    return "\n".join(lines) + "\n"
