"""Generator adapters: each renders the generic plan into one tool's own language (04).

An adapter answers three questions about its tool — what does it call this setting, what does its
card look like, and what processes does it need — and nothing else in `hekit` learns which tool is
running. The parts that are the same for every tool live in `base` (beams, event counts, FIFO wiring,
where an executable comes from) and `cache` (the prepare cache), so a new generator is a card dialect
rather than a new pipeline.

Pythia runs in-process and a store replay has no tool at all; Sherpa, Whizard, MadGraph and Herwig
arrive in P7-S03 onward. `registry` holds the list of what exists, so the config schema and this
package cannot disagree about it.
"""

from __future__ import annotations

from typing import Any

from . import pythia
from . import sherpa
from . import whizard
from .registry import (ADAPTERS, KNOWN_TOOLS, adapter_for, implemented, register, tools,
                       unregister)

register("pythia", pythia, description=KNOWN_TOOLS["pythia"])
register("sherpa", sherpa, description=KNOWN_TOOLS["sherpa"])
register("whizard", whizard, description=KNOWN_TOOLS["whizard"])

__all__ = ["ADAPTERS", "KNOWN_TOOLS", "adapter_for", "defaults_for", "implemented", "register",
           "tools", "unregister"]


def defaults_for(tool: str, text: str) -> dict[str, str]:
    """What a native card already sets, as `normalised key → value text` (used by the identity hash)."""
    adapter = ADAPTERS.get(tool)
    reader = getattr(adapter, "card_defaults", None)
    return reader(text) if reader is not None else {}
