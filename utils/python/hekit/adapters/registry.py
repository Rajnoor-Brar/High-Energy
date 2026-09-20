"""Which generators exist, and which of them have an adapter yet (04 §2).

A leaf module on purpose: it imports nothing from `hekit` but the error type, so both the config
schema and the adapter package can read the tool list from **one** place. It used to be written out
twice — once as `[generator].tool`'s `choices` and once as the `ADAPTERS` dict — and the two could
disagree about what was possible.

`register()` is how an adapter announces itself; it is also how a test plugs in a fake generator to
exercise the framework without needing Sherpa installed.
"""

from __future__ import annotations

from typing import Any

from ..errors import HepError, did_you_mean

#: Every generator the design knows about (04 §2), whether or not its adapter is written. A config
#: naming one of these is valid; a config naming one without an adapter fails later, and says which
#: step brings it.
#: The order is the capability matrix's, not alphabetical: it is the order a reader should meet them
#: in, and it is what `[generator].tool`'s documented choices show.
KNOWN_TOOLS: dict[str, str] = {
    "pythia": "Pythia 8, in-process (P2-S04)",
    "sherpa": "Sherpa, subprocess writing HepMC3 (P7-S03)",
    "herwig": "Herwig, subprocess; needs ThePEG --with-hepmc (P7-S07)",
    "whizard": "Whizard, subprocess writing HepMC3 (P7-S04)",
    "madgraph": "MadGraph LHE, showered by Pythia (P7-S05)",
    "store": "replay a HepMC3 event store (P5-S02)",
}

#: tool name → the module or object implementing the adapter protocol (04 §1).
ADAPTERS: dict[str, Any] = {}


def register(tool: str, adapter: Any, *, description: str = "") -> None:
    """Make `tool` usable. Adding a tool the design does not list is allowed — that is what lets a
    test exercise the framework — and it becomes a valid `[generator].tool` at the same moment."""
    ADAPTERS[tool] = adapter
    KNOWN_TOOLS.setdefault(tool, description or f"{tool} adapter")


def unregister(tool: str) -> None:
    """Undo a `register`, so a test cannot leak a fake tool into the next one."""
    ADAPTERS.pop(tool, None)
    KNOWN_TOOLS.pop(tool, None)


def tools() -> tuple[str, ...]:
    """Every valid `[generator].tool`, in the order KNOWN_TOOLS declares them."""
    return tuple(KNOWN_TOOLS)


def implemented() -> tuple[str, ...]:
    return tuple(sorted(ADAPTERS))


def adapter_for(tool: str) -> Any:
    """The adapter for a tool, or an error that says whether it is unknown or merely not written."""
    if tool in ADAPTERS:
        return ADAPTERS[tool]
    if tool in KNOWN_TOOLS:
        raise HepError(f"the '{tool}' adapter is not written yet",
                       hint=f"{KNOWN_TOOLS[tool]}; available now: {', '.join(implemented())}")
    raise HepError(f"no generator called '{tool}'",
                   hint=did_you_mean(tool, KNOWN_TOOLS) or f"one of: {', '.join(tools())}")
