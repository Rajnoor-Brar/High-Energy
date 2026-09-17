"""Generator adapters: each renders the generic plan into one tool's own language (04).

Only Pythia is implemented here (P1-S05). Sherpa, Whizard, MadGraph, Herwig and the store source arrive
in P5 and P7; they plug in through `ADAPTERS` and the same three questions: what does this tool call
this setting, what does its card look like, and what does its stage chain look like.
"""

from __future__ import annotations

from typing import Any

from ..errors import HepError, did_you_mean
from . import pythia

#: tool name → adapter module
ADAPTERS: dict[str, Any] = {"pythia": pythia}


def adapter_for(tool: str) -> Any:
    try:
        return ADAPTERS[tool]
    except KeyError:
        raise HepError(f"no adapter for generator '{tool}' yet",
                       hint=did_you_mean(tool, ADAPTERS) or
                            f"available now: {', '.join(sorted(ADAPTERS))}; the others arrive in P5 and P7"
                       ) from None


def defaults_for(tool: str, text: str) -> dict[str, str]:
    """What a native card already sets, as `normalised key → value text` (used by the identity hash)."""
    adapter = ADAPTERS.get(tool)
    return adapter.card_defaults(text) if adapter is not None else {}
