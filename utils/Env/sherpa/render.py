"""utils/Env/sherpa/render.py — Sherpa's point card: the base YAML deep-merged with the point's
values, written whole (docs/06_Internals.md §16, L12).

Sherpa's card is a tree, so "base plus overrides" is a merge, not v1's append-and-last-wins. A key
names a path into it, `EPA:Q2Max`, and may index a list, `PDF_SET[0]` (Sherpa's lists are per
beam: an override replaces one entry, never appends). The card on disk is the card that ran.

* `MPI_PDF_SET` follows `PDF_SET`: Sherpa's MPI reads its own key and falls back to a compiled
  default that is not installed here (v1, P7-S02). An override of `PDF_SET` moves `MPI_PDF_SET`
  with it when the two agreed before, and a card without `MPI_PDF_SET` gets a copy.
* The plan owns the run control: a base card setting BEAMS, BEAM_ENERGIES, RANDOM_SEED, EVENTS,
  EVENT_OUTPUT or RESULT_DIRECTORY is refused, so a point never silently inherits one.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import yaml

from runner.errors import HepError

_STEP = re.compile(r"^(?P<name>[^\[\]]+)(?:\[(?P<index>\d+)\])?$")


def merge(base: dict, other: dict) -> dict:
    """Deep merge: a mapping recurses, anything else (a list included) replaces."""
    out = copy.deepcopy(base)
    for key, value in other.items():
        out[key] = merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else copy.deepcopy(value)
    return out


def assign(document: dict, path: str, value: Any, origin: str = "") -> None:
    """`EPA:Q2Max = 1` or `PDF_SET[0] = X` inside the tree, making mappings on the way."""
    steps = [s for s in re.split(r"[:.]", path) if s]
    node: Any = document
    for i, step in enumerate(steps):
        match = _STEP.match(step)
        if not match:
            raise HepError(f"'{path}' is not a Sherpa key path", where=origin)
        name, index, last = match["name"], match["index"], i == len(steps) - 1
        if index is None:
            if last:
                node[name] = value
            else:
                node = node.setdefault(name, {})
                if not isinstance(node, dict):
                    raise HepError(f"'{path}': {name} is not a mapping in the card", where=origin)
            continue
        entries = node.get(name)
        if not isinstance(entries, list) or int(index) >= len(entries):
            raise HepError(f"'{path}': the card has no {name}[{index}]", where=origin,
                           hint=f"{name} must be a list in the base card with an entry {index}")
        if last:
            entries[int(index)] = value
        else:
            node = entries[int(index)]


def card(bases: list[str], overrides: list, context: dict) -> str:
    """The whole card before seeds: the bases merged in order, then the overrides."""
    document: dict = {}
    for text in bases:
        loaded = yaml.safe_load(text) or {}
        if not isinstance(loaded, dict):
            raise HepError("a Sherpa base card must be a YAML mapping", where=context.get("tag", "sherpa"))
        owned = [k for k in loaded if k in context["owned"]]
        if owned:
            raise HepError(f"the base card sets {', '.join(owned)}, which the plan owns",
                           where=f"[tools.{context.get('tag', 'sherpa')}].baseconfig",
                           hint="beams, energies, seed, events and outputs come from quantities and the runner (L12)")
        document = merge(document, loaded)
    for key, value, origin in overrides:               # the runner's Override, unpacked (L26)
        if key == "sqrts":                               # symmetric beams: Sherpa wants each beam's energy
            key, value = "BEAM_ENERGIES", [float(value) / 2, float(value) / 2]
        before = copy.deepcopy(document.get("PDF_SET"))
        assign(document, key, value, origin)
        if key.startswith("PDF_SET"):
            if "MPI_PDF_SET" not in document or document.get("MPI_PDF_SET") == before:
                document["MPI_PDF_SET"] = copy.deepcopy(document["PDF_SET"])
    return yaml.safe_dump(document, sort_keys=False, default_flow_style=None, width=100)
