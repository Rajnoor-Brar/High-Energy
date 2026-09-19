"""Looking at events (06 §5).

"Presentability when going over events" is guideline 2, and this is the part of it that replaces
Pythia's fixed-width `event.list()`: a table you can read, with particle names instead of PDG codes,
colour by role, and the mother/daughter links that make a shower legible.

Where the events come from is deliberately uniform: a **store** (11), any HepMC3 file, or a config —
and a config is turned into the other two by generating a few events into a temporary store. One
renderer, one data path, and no second implementation of "what is an event".

Compressed shards are streamed through `zstd -dc` / `gzip -dc` into HepMC3's own ASCII reader, cut off
after the events asked for: `pyHepMC3` has no compressed reader, and decompressing a 100 GB shard to
look at three events would be the wrong trade.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from ..errors import HepError

#: HepMC3 status codes that matter for reading an event (the rest are generator-specific).
BEAM, FINAL, DECAYED, DOCUMENTATION = 4, 1, 2, 3

ROLE_STYLE = {"beam": "magenta", "hard": "bold cyan", "final": "green", "shower": "dim"}

SUFFIXES = {".gz": ["gzip", "-dc"], ".zst": ["zstd", "-dc"], ".zstd": ["zstd", "-dc"],
            ".xz": ["xz", "-dc"]}


@dataclass
class Particle:
    """One particle of an event, as the table shows it."""

    index: int
    pid: int
    status: int
    px: float = 0.0
    py: float = 0.0
    pz: float = 0.0
    energy: float = 0.0
    mass: float = 0.0
    mothers: list[int] = field(default_factory=list)
    daughters: list[int] = field(default_factory=list)

    @property
    def pt(self) -> float:
        return math.hypot(self.px, self.py)

    @property
    def eta(self) -> float:
        momentum = math.sqrt(self.px ** 2 + self.py ** 2 + self.pz ** 2)
        if momentum <= abs(self.pz):
            return math.copysign(float("inf"), self.pz)
        return 0.5 * math.log((momentum + self.pz) / (momentum - self.pz))

    @property
    def phi(self) -> float:
        return math.atan2(self.py, self.px)

    @property
    def role(self) -> str:
        if self.status == BEAM:
            return "beam"
        if self.status == FINAL:
            return "final"
        if self.status in {DECAYED, DOCUMENTATION} and not self.mothers:
            return "hard"
        if self.status == DOCUMENTATION:
            return "hard"
        return "shower"

    @property
    def name(self) -> str:
        return pdg_name(self.pid)


@dataclass
class Event:
    number: int
    particles: list[Particle] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    xsec_pb: float | None = None

    def final_state(self) -> list[Particle]:
        return [particle for particle in self.particles if particle.status == FINAL]

    def hard_process(self) -> list[Particle]:
        """The beams and whatever came straight out of them — the two lines of physics in an event."""
        return [particle for particle in self.particles
                if particle.role in {"beam", "hard"} or particle.status == DOCUMENTATION]


def pdg_name(pid: int) -> str:
    """`211` → `pi+`. Falls back to the number, which is still better than nothing."""
    try:
        from particle import Particle as PDGParticle

        return PDGParticle.from_pdgid(pid).name
    except Exception:                                  # noqa: BLE001 - a name is a convenience
        return str(pid)


# ── reading ──────────────────────────────────────────────────────────────────

def _decompressor(path: Path) -> list[str] | None:
    command = SUFFIXES.get(path.suffix.lower())
    if command is None:
        return None
    if shutil.which(command[0]) is None:
        raise HepError(f"{path.name} needs {command[0]} to read", hint="install it, or store "
                                                                       "uncompressed events")
    return command


def _prefix(path: Path, events: int) -> Path:
    """Stream a compressed file until `events` events have gone by, into a temporary ASCII file."""
    command = _decompressor(path)
    if command is None:
        return path

    handle = tempfile.NamedTemporaryFile("wb", suffix=".hepmc", delete=False)
    seen = 0
    with subprocess.Popen([*command, str(path)], stdout=subprocess.PIPE) as process:
        assert process.stdout is not None
        for line in process.stdout:
            handle.write(line)
            if line.startswith(b"E "):
                seen += 1
                if seen > events:                      # one past, so the last event is complete
                    break
        process.kill()
    handle.close()
    return Path(handle.name)


def read_events(source: Path | str, limit: int = 3) -> list[Event]:
    """Up to `limit` events from a store directory or a HepMC3 file."""
    path = Path(source)
    if path.is_dir():
        path = _first_shard(path)
    if not path.is_file():
        raise HepError(f"no events to read at {source}")

    readable = _prefix(path, limit)
    try:
        return list(_read_ascii(readable, limit))
    finally:
        if readable != path:
            readable.unlink(missing_ok=True)


def _first_shard(directory: Path) -> Path:
    """A store's first shard: every shard is a valid sample on its own (11 §1)."""
    from ..store import index as index_module

    try:
        index = index_module.read(directory)
    except HepError:
        shards = sorted(directory.glob("events.*.hepmc*"))
        if not shards:
            raise
        return shards[0]
    if not index.shards:
        raise HepError(f"the store at {directory} has no shards")
    return directory / index.shards[0].file


def _read_ascii(path: Path, limit: int) -> Iterator[Event]:
    try:
        from pyHepMC3 import HepMC3
    except ImportError as error:                       # pragma: no cover - part of the venv
        raise HepError("reading events needs pyHepMC3",
                       hint="`hep doctor` reports what is importable") from error

    reader = HepMC3.ReaderAscii(str(path))
    if reader.failed():
        raise HepError(f"cannot read {path}")
    try:
        for _ in range(limit):
            event = HepMC3.GenEvent()
            reader.read_event(event)
            if reader.failed():
                break
            yield _convert(event)
    finally:
        reader.close()


def _convert(event: Any) -> Event:
    found = Event(number=event.event_number())
    try:
        found.weights = list(event.weights())
    except Exception:                                  # pragma: no cover - an event with no weights
        found.weights = []
    cross = event.cross_section()
    if cross is not None:
        try:
            found.xsec_pb = cross.xsec()
        except Exception:                              # pragma: no cover
            found.xsec_pb = None

    for particle in event.particles():
        momentum = particle.momentum()
        record = Particle(index=particle.id(), pid=particle.pid(), status=particle.status(),
                          px=momentum.px(), py=momentum.py(), pz=momentum.pz(),
                          energy=momentum.e(), mass=particle.generated_mass())
        production = particle.production_vertex()
        if production is not None:
            record.mothers = [entry.id() for entry in production.particles_in()]
        decay = particle.end_vertex()
        if decay is not None:
            record.daughters = [entry.id() for entry in decay.particles_out()]
        found.particles.append(record)
    found.particles.sort(key=lambda entry: entry.index)
    return found


# ── rendering ────────────────────────────────────────────────────────────────

def table_for(event: Event, particles: list[Particle], *, title: str = ""):
    """The table of 06 §5: index, name, status, mothers → daughters, pT, η, φ, m."""
    from rich.table import Table
    from rich.text import Text

    from . import theme

    table = Table(title=title or f"event {event.number}", title_justify="left", box=None,
                  pad_edge=False)
    for name, justify in (("#", "right"), ("particle", "left"), ("status", "right"),
                          ("mothers", "left"), ("daughters", "left"), ("pT", "right"),
                          ("eta", "right"), ("phi", "right"), ("m", "right")):
        table.add_column(name, justify=justify)

    for particle in particles:
        style = ROLE_STYLE.get(particle.role, "")
        table.add_row(
            str(particle.index),
            Text(theme.t(particle.name), style=style),
            str(particle.status),
            ",".join(str(entry) for entry in particle.mothers) or "—",
            ",".join(str(entry) for entry in particle.daughters[:6])
            + ("…" if len(particle.daughters) > 6 else "") or "—",
            f"{particle.pt:.2f}",
            "—" if math.isinf(particle.eta) else f"{particle.eta:+.2f}",
            f"{particle.phi:+.2f}",
            f"{particle.mass:.3f}")
    return table


def tree_for(event: Event, particles: list[Particle]):
    """The decay tree: each beam, and what came out of it."""
    from rich.tree import Tree

    from . import theme

    by_index = {particle.index: particle for particle in event.particles}
    shown = {particle.index for particle in particles}
    root = Tree(theme.t(f"event {event.number}"))
    seen: set[int] = set()

    def add(node, particle: Particle, depth: int = 0) -> None:
        if particle.index in seen or depth > 12:
            return
        seen.add(particle.index)
        label = (f"{particle.index} [{ROLE_STYLE.get(particle.role, '')}]"
                 f"{theme.t(particle.name)}[/] "
                 f"pT {particle.pt:.2f}")
        child = node.add(label)
        for index in particle.daughters:
            daughter = by_index.get(index)
            if daughter is not None and (not shown or index in shown or daughter.status == FINAL):
                add(child, daughter, depth + 1)

    for particle in event.particles:
        if particle.status == BEAM:
            add(root, particle)
    if not seen:                                       # no beams recorded: show what there is
        for particle in particles[:20]:
            add(root, particle)
    return root


def select(event: Event, *, final: bool = False, hard: bool = False,
           limit: int = 0) -> list[Particle]:
    if final:
        chosen = event.final_state()
    elif hard:
        chosen = event.hard_process()
    else:
        chosen = list(event.particles)
    return chosen[:limit] if limit else chosen


def summary_of(event: Event) -> str:
    final = len(event.final_state())
    weight = event.weights[0] if event.weights else 1.0
    text = f"{len(event.particles)} particles, {final} final, weight {weight:g}"
    if event.xsec_pb:
        # The generator's *running* estimate at this event, not the run's merged value — that lives
        # in the store's index (11 §4), and confusing the two is how a plot gets normalised wrongly.
        text += f", sigma(so far) {event.xsec_pb:.4g} pb"
    return text
