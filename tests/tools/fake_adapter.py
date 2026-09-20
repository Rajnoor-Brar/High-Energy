"""The adapter for `tests/tools/fake_generator.py` (P7-S01).

It is a module with module-level functions, exactly like `hekit.adapters.pythia`, because that is
what the protocol of 04 §1 looks like in practice. It exists so the framework can be tested end to
end without Sherpa installed — and so the shape a real adapter has to fill in is written down
somewhere executable rather than only in prose.

It is deliberately minimal: a real adapter's work is in `render`, translating the plan's quantities
into its tool's own card language, and the fake has no card language at all.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "utils" / "python"))

from hekit.adapters import base                                          # noqa: E402

NAME = "fake"
VERSION = "1.0"

#: A FIFO between two processes on one machine: compressing it spends CPU to save nothing.
STREAM_COMPRESSION = "none"

#: Where the events really come from, and how short to fall. Read from the environment rather than
#: set by hand, because the test drives `hep` as a subprocess and these have to cross that boundary.
STORE = Path(os.environ.get("HEKIT_FAKE_STORE", ""))
SHORT_BY = int(os.environ.get("HEKIT_FAKE_SHORT_BY", "0") or 0)

SCRIPT = REPO / "tests" / "tools" / "fake_generator.py"


def probe(config: Any = None) -> base.Capabilities:
    return base.Capabilities(tool=NAME, available=SCRIPT.is_file(), version=VERSION,
                             executable=str(SCRIPT), hepmc=True, seeds=True, prepare=True,
                             detail="" if SCRIPT.is_file() else "the fake generator script is gone")


def card_defaults(text: str) -> dict[str, str]:
    """The fake has no card language, so a card contributes nothing to the identity hash."""
    return {}


def check_card(text: str, where: str) -> None:
    """A base card may not set what the plan owns (04 §8). The fake has no card keys of its own."""
    base.check_beam_keys(NAME, card_defaults(text), where=where)


def check_overrides(point: Any, where: str) -> None:
    """Same rule, applied to the point's `setting` quantities rather than to the base card."""
    base.check_beam_keys(NAME, [name for name, _, _ in getattr(point, "settings", ())], where=where)


def frame_warning(point: Any) -> str:
    return ""


def render_card(point: Any, *, seeds: Any, threads: int, card_path: str = "", card_sha: str = "",
                identity_hash: str = "", origin: str = "", **_: Any) -> str:
    """The point card.

    The seed and the event count are on it *and are ignored by the prepare hash* — that is the whole
    mechanism of the cache (04 §1), so the fake writes them to exercise it rather than leaving them
    out and making the test pass for the wrong reason.
    """
    settings = "\n".join(f"{name} = {value}" for name, value, _ in getattr(point, "settings", ()))
    return (f"# fake point card for {getattr(point, 'name', '')}\n"
            f"# identity {identity_hash}\n"
            f"seed = {getattr(seeds, 'point', 0)}\n"
            f"events = {getattr(point, 'events', 0)}\n"
            f"beams = {' '.join(str(entry) for entry in getattr(point, 'beams', ()))}\n"
            f"energies = {' '.join(str(entry) for entry in getattr(point, 'energies', ()))}\n"
            f"{settings}\n")


def validate(config: Any, group: Any) -> None:
    base.check_beam_keys(NAME, card_defaults(getattr(group, "card", "") or ""), where="fake card")


def render(config: Any, group: Any, workdir: Path) -> base.Cards:
    return base.Cards(paths=[], text=getattr(group, "card", "") or "")


def prepare(config: Any, group: Any, cache: Path) -> list[base.Stage]:
    """One cacheable stage. Seed-independent by construction: it is not given the seed."""
    return [base.Stage(
        name="fake-prepare", role="prepare",
        argv=[sys.executable, str(SCRIPT), "--prepare", str(cache)],
        parser=NAME, produces=[Path(cache) / "grid.dat"],
        note="integration grid, cached across seeds")]


def generate(config: Any, group: Any, fifo: Path) -> base.Stage:
    events = int(getattr(config.run, "events", 0) or 0)
    return base.Stage(
        name="fake-generate", role="generate",
        argv=[sys.executable, str(SCRIPT), "--store", str(STORE), "--out", str(fifo),
              "--events", str(max(0, events - SHORT_BY))],
        parser=NAME, note="writes HepMC3 into the FIFO")
