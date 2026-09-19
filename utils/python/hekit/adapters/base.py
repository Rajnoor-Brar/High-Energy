"""What every generator adapter has in common (04 §1, §8).

An adapter answers three questions about one tool — what does it call this setting, what does its
card look like, and what processes does it need — and the rest of `hekit` never learns which tool it
is talking to. The parts that are *not* tool-specific live here, because getting them wrong once per
generator is how five adapters become five slightly different pipelines:

* **beams are resolved by the planner, never by a card** (04 §8). Every tool has its own spelling of
  "beam A's PDG code", and every one of them is a clash error. The rule is shared; only the spelling
  list is per-tool.
* **an external generator emits exactly `run.events`**, and the FIFO reader counts them. A generator
  that stops early is not a shorter result, it is a failed one.
* **executables come from `tools.<name>.exe` and then `PATH`** — never an absolute path baked into
  the repo (04 §8, N6).
* **a stage is data**: argv, env, cwd, a log, a progress parser and what it should produce. The
  supervisor (06) runs every stage the same way, and an adapter never spawns anything itself.

The FIFO is the seam. An external generator writes HepMC3 into it and `hep-run` reads it with
`Source::Stream` (P5-S02), which is the same reader a store replay uses — so an external generator
costs no new event path, only a new way of starting a process.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..errors import HepError

#: Beam keys that a raw `setting` quantity may not write, per tool (04 §8). The planner owns beams;
#: a card that sets them silently overrides the point's own identity.
BEAM_KEYS: dict[str, tuple[str, ...]] = {
    "pythia": ("beams:ida", "beams:idb", "beams:ecm", "beams:ea", "beams:eb", "beams:frametype"),
    "sherpa": ("beams", "beam_1", "beam_2", "beam_energies", "beam_energy_1", "beam_energy_2"),
    "whizard": ("beams", "sqrts", "beams_momentum"),
    "herwig": ("lpp1", "lpp2", "ebeam1", "ebeam2"),
    "madgraph": ("lpp1", "lpp2", "ebeam1", "ebeam2"),
}

#: The filename an external generator writes its events into, inside the point directory.
FIFO_NAME = "events.hepmc"


@dataclass
class Capabilities:
    """What `probe()` found on this machine. Goes into provenance (04 §8)."""

    tool: str
    available: bool = False
    version: str = ""
    executable: str = ""
    hepmc: bool = False               # can it write HepMC3 events?
    native_rivet: bool = False        # does it run Rivet itself? (we use our own sink anyway)
    threads: bool = False             # can one process use several threads?
    seeds: bool = False               # can the seed be set from outside?
    prepare: bool = False             # does it have a cacheable, seed-independent step?
    detail: str = ""                  # why it is unavailable, when it is

    def require(self) -> None:
        if not self.available:
            raise HepError(f"{self.tool} is not available on this machine",
                           hint=self.detail or f"set `tools.{self.tool}.exe` in the machine file, "
                                               "or put it on PATH; `hep doctor` reports what it finds")


@dataclass
class Cards:
    """What `render()` wrote: the files the tool will read, in order, and their hashes."""

    paths: list[Path] = field(default_factory=list)
    text: str = ""                    # the point card, for the identity hash and provenance
    digests: dict[str, str] = field(default_factory=dict)


@dataclass
class Stage:
    """One process, as data (04 §1). The supervisor runs it; the adapter never spawns anything."""

    name: str
    role: str = "generate"            # generate | analyse | prepare | detector
    argv: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path | None = None
    log: Path | None = None
    parser: str = ""                  # tool name for the progress parser (06 §4); "" = spinner
    timeout: float = 0.0              # 0 = no limit
    produces: list[Path] = field(default_factory=list)
    #: Files to write before this stage is spawned, as (path, text). For a tool whose one card
    #: cannot serve two stages: Whizard's base ends in `simulate`, and its `--execute` runs *before*
    #: the card rather than after, so the integration needs a card of its own.
    writes: list[tuple[str, str]] = field(default_factory=list)
    note: str = ""

    def to_plan_stage(self) -> Any:
        """The planner's lighter `Stage`, which is what `hep plan` shows."""
        from ..plan.model import Stage as PlanStage

        return PlanStage(name=self.name, role=self.role,
                         command=[str(entry) for entry in self.argv], note=self.note,
                         cwd=str(self.cwd) if self.cwd else "", env=dict(self.env),
                         writes=[(str(path), text) for path, text in self.writes])


@runtime_checkable
class Adapter(Protocol):
    """04 §1. Adapters are modules, so these are module-level functions rather than methods.

    **Every one of these takes `**extra`.** The planner hands the same context to all adapters —
    where the FIFO is, which Rivet mode is in force, the base card's text — and an adapter ignores
    what it does not need. Without it, adding one adapter's needs breaks every other adapter.
    """

    tool: str

    def probe(self, config: Any) -> Capabilities: ...
    def validate(self, config: Any, group: Any) -> None: ...
    def render(self, config: Any, group: Any, workdir: Path) -> Cards: ...
    def prepare(self, config: Any, group: Any, cache: Path) -> list[Stage]: ...
    def generate(self, config: Any, group: Any, fifo: Path) -> Stage: ...


# ── the shared rules ─────────────────────────────────────────────────────────

def executable_for(tool: str, config: Any) -> str:
    """`tools.<tool>.exe` from the machine file, else the tool's own name on `PATH` (04 §8).

    Never an absolute path from the repo: the same config has to work on a different machine (N6).
    """
    declared = ""
    tools = getattr(config, "tools", None)
    if tools is not None:
        entry = tools.get(tool) if isinstance(tools, dict) else getattr(tools, tool, None)
        declared = (entry.get("exe") if isinstance(entry, dict) else getattr(entry, "exe", "")) or ""
    if declared:
        return str(declared)
    found = shutil.which(tool)
    return found or tool


def check_beam_keys(tool: str, keys: Any, *, where: str = "") -> None:
    """Refuse a raw setting that writes beams: the planner owns them (04 §8).

    `keys` is anything iterable of key names — a rendered card's keys, or a quantity's.
    """
    reserved = set(BEAM_KEYS.get(tool, ()))
    if not reserved:
        return
    clashing = sorted({str(key) for key in keys if str(key).strip().lower() in reserved})
    if not clashing:
        return
    raise HepError(
        f"{', '.join(clashing)} sets the beams, which the plan owns" + (f" ({where})" if where else ""),
        hint="use the [beams] section or a `beams`/`energies` quantity; a raw setting would make the "
             "point's name and hash disagree with the events it produced (04 §8)")


def check_event_count(expected: int, produced: int, *, tool: str) -> None:
    """An external generator must emit exactly what was asked for (04 §8).

    A short stream is a failure, not a smaller sample: σ was measured for the full run, so a YODA
    normalised with it and filled with fewer events is wrong by exactly the fraction missing.
    """
    if expected <= 0 or produced == expected:
        return
    # Signed from the run's point of view: a run that is 50 events short reads "-50", not "+50".
    raise HepError(
        f"{tool} produced {produced} of the {expected} events that were asked for "
        f"({produced - expected:+d})",
        hint="the generator's log says why it stopped; a short stream cannot be normalised with the "
             "cross-section of the full run")


def fifo_path(directory: Path) -> Path:
    return Path(directory) / FIFO_NAME


def make_fifo(path: Path) -> Path:
    """Create the named pipe an external generator writes into, replacing a stale one.

    In the point directory, not `/tmp`: a fixed shared path is how two runs corrupted each other's
    events in the legacy pipeline (00/B19).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        path.unlink()
    os.mkfifo(path)
    return path


def stream_source(fifo: Path, *, compression: str = "none", queue: int = 0) -> dict[str, Any]:
    """The `[source]` block that makes `hep-run` read a FIFO with `Source::Stream` (04 §8, 11 §4).

    A stream is a store with one shard and no index, so σ, beams and weights come from the events
    themselves — the last event's `GenCrossSection` being the generator's final estimate, since there
    is only one producer.
    """
    store: dict[str, Any] = {"dir": str(Path(fifo).parent), "compression": compression,
                             "shards": [], "workers": []}
    if queue:
        store["queue"] = queue
    return {"kind": "stream", "inputs": [str(fifo)], "store": store}
