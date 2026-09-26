"""MadGraph, showered by Pythia (04 §7).

The odd one out. Every other external generator here hands over *events*; MadGraph hands over a
**matrix element** — an LHE file — and Pythia showers and hadronises it inside `hep-run`. So there is
no FIFO and no `Source::Stream`: the source is `Source::Pythia` reading the LHE, and this adapter
renders a *Pythia* card rather than a dialect of its own.

That also makes it the one adapter whose stages may not overlap. A FIFO's two ends have to be open at
once; a file has to be finished before anything reads it. Hence four phases:

1. **build** — `mg5_aMC proc_card.dat` writes the process directory. Cached: it depends on the
   processes and the model, not on the seed or the event count, and it is minutes of Fortran.
2. **launch** — `mg5_aMC` with a launch script writes `unweighted_events.lhe.gz`. This is where the
   seed, the event count and the beams go.
3. **unpack** — `gunzip`. Pythia's own gzip support is a build-time option (01 §4), so relying on it
   would make a run's success depend on how Pythia was compiled.
4. **shower** — `hep-run`, with `Beams:frameType = 4` and `Beams:LHEF`.

**Beams come from the LHE, not from the card.** The plan's ids and energies are written into the
*launch* script (`lpp1/2`, `ebeam1/2`); the shower card must not repeat them, because the LHE header
already fixes them and a card that disagreed would be silently overridden.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

from ..errors import HepError
from . import base

NAME = "madgraph"

#: MadGraph writes a file, so nothing overlaps: the LHE must be complete before Pythia opens it.
STREAMS = False

#: Where MadGraph puts what it generated, relative to the process directory.
LHE = Path("Events") / "run_01" / "unweighted_events.lhe"

#: Beam-type mapping (04 §7). `lpp` says what kind of beam it is, not which particle.
LPP = {2212: 1, -2212: -1, 11: 0, -11: 0}

#: Run-card keys the plan owns; a `run_card.*` override that sets them is a planning error.
RESERVED = {
    "nevents": "[run] events",
    "iseed": "[run] seed (the seed block is derived from the point identity)",
    "lpp1": "[beams] ids",
    "lpp2": "[beams] ids",
    "ebeam1": "[beams] energies",
    "ebeam2": "[beams] energies",
}

#: How a point sets a MadGraph run-card key: `run_card.ptj = 20`.
RUN_CARD = "run_card."

#: `generate`/`add process` lines, for the multi-jet merging warning.
_PROCESS = re.compile(r"^\s*(?:generate|add\s+process)\s+(.*)$", re.M)


# ── the cards ────────────────────────────────────────────────────────────────

def card_defaults(text: str) -> dict[str, str]:
    """What a proc card declares. Its *processes* are its content, so they are what the hash sees."""
    found: dict[str, str] = {}
    for index, match in enumerate(_PROCESS.finditer(text or "")):
        found[f"process:{index}"] = " ".join(match.group(1).split())
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("set ") and "=" not in stripped:
            parts = stripped.split()
            if len(parts) >= 3:
                found[parts[1].lower()] = " ".join(parts[2:])
    return found


def check_card(text: str, where: str) -> None:
    """A proc card describes processes; it must not run or output anything itself."""
    for line in (text or "").splitlines():
        head = line.strip().split(" ", 1)[0].lower()
        if head in {"output", "launch"}:
            raise HepError(f"the proc card has its own `{head}` line", where=where,
                           hint="hep writes those: `output` goes to the prepare cache and `launch` "
                                "carries the point's seed, event count and beams (04 §7)")
    if not _PROCESS.search(text or ""):
        raise HepError("the proc card generates no process", where=where,
                       hint="it needs at least one `generate …` line")


def check_overrides(point: Any, where: str) -> None:
    for name, _, _ in getattr(point, "settings", ()):
        key = str(name)
        bare = key[len(RUN_CARD):] if key.lower().startswith(RUN_CARD) else key
        if bare.lower() in RESERVED:
            raise HepError(f"a quantity sets {key}, which the plan owns", where=where,
                           hint=RESERVED[bare.lower()])


def frame_warning(point: Any) -> str:
    return ""


def merging_warning(text: str) -> str:
    """A multi-jet proc card without merging settings is usually a mistake — but only a warning.

    Validating the merging itself is out of scope (the step says so); noticing that nobody set any
    is cheap and is the part a reader would want said out loud.
    """
    processes = [match.group(1) for match in _PROCESS.finditer(text or "")]
    if len(processes) < 2:
        return ""
    jets = sum(1 for process in processes if re.search(r"\bj\b", process))
    if jets < 2:
        return ""
    return ("this proc card generates several jet multiplicities; merging (MLM/CKKW) is configured "
            "in the shower card, and hep does not check it (04 §7)")


def cache_text(group: Any) -> str:
    """What the prepare cache keys on: the proc card, because that is what is built."""
    return getattr(group, "base_card", "") or ""


def lpp_for(pdg: int) -> int:
    if int(pdg) not in LPP:
        raise HepError(f"no MadGraph beam type for PDG {pdg}",
                       hint="`lpp` covers protons (±2212) and leptons (±11); anything else needs a "
                            "beam setting in the proc card (04 §7)")
    return LPP[int(pdg)]


def launch_script(point: Any, *, seeds: Any, process_dir: Path, events: int = 0) -> str:
    """The script that turns the process directory into an LHE file (04 §7)."""
    beams = [int(entry) for entry in (getattr(point, "beams", ()) or ())]
    energies = [float(entry) for entry in (getattr(point, "energies", ()) or ())]
    if len(energies) == 1:                      # a scalar sqrt(s) is split evenly
        energies = [energies[0] / 2.0, energies[0] / 2.0]

    lines = [f"launch {process_dir}",
             # Pythia showers in `hep-run`, and a detector is P7-S08's business.
             "shower=OFF", "detector=OFF", "analysis=OFF", "done",
             f"set nevents {int(events or getattr(point, 'events', 0) or 0)}",
             f"set iseed {int(getattr(seeds, 'point', 0) or 0)}"]
    for index, code in enumerate(beams[:2], start=1):
        lines.append(f"set lpp{index} {lpp_for(code)}")
    for index, energy in enumerate(energies[:2], start=1):
        lines.append(f"set ebeam{index} {energy}")
    for name, entry, source in getattr(point, "settings", ()):
        key = str(name)
        if key.lower().startswith(RUN_CARD):
            lines.append(f"set {key[len(RUN_CARD):]} {entry}    # {source}")
    lines.append("done")
    return "\n".join(lines) + "\n"


def render_card(point: Any, *, seeds: Any, threads: int, card_path: str = "", card_sha: str = "",
                identity_hash: str = "", origin: str = "", lhe: str = "", **_: Any) -> str:
    """The **Pythia** card that showers the LHE (04 §7).

    Deliberately short. The beams are not here: the LHE header fixes them, and `Beams:frameType = 4`
    tells Pythia to read them from it. Writing them again would be a second, ignorable opinion.
    """
    return "\n".join([
        "! hekit point card (generated) — showers the LHE MadGraph produced",
        f"! point      : {getattr(point, 'name', '')}",
        f"! identity   : {identity_hash}",
        f"! proc card  : {card_path} ({card_sha})",
        f"! origin     : {origin}",
        "!",
        "! The beams are the LHE's: frameType 4 means Pythia reads them from its header, and the",
        "! plan wrote them into the launch script instead (04 §7).",
        "Beams:frameType = 4",
        f"Beams:LHEF = {lhe}" if lhe else "",
        "",
    ])


# ── the tool ─────────────────────────────────────────────────────────────────

def executable(config: Any = None) -> str:
    if config is not None:
        return base.executable_for("mg5_aMC", config)
    return shutil.which("mg5_aMC") or "mg5_aMC"


def probe(config: Any = None) -> base.Capabilities:
    found = base.Capabilities(tool=NAME, hepmc=False, native_rivet=False, seeds=True, prepare=True)
    path = executable(config)
    found.executable = path
    if shutil.which(path) is None and not Path(path).is_file():
        found.detail = "no `mg5_aMC` on PATH and no `tools.mg5_aMC.exe` in the machine file"
        return found
    found.available = True
    # MadGraph has no `--version`; its VERSION file is the honest place to look.
    version_file = Path(path).parent.parent / "VERSION"
    if version_file.is_file():
        for line in version_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("version"):
                found.version = line.split("=", 1)[-1].strip()
                break
    return found


_version: str | None = None


def version(config: Any = None) -> str:
    global _version
    if _version is None:
        _version = probe(config).version or ""
    return _version


def process_dir(cache: Path) -> Path:
    return Path(cache) / "process"


def prepare(config: Any, group: Any, cache: Path) -> list[base.Stage]:
    """Build the process directory (04 §7). Minutes of Fortran, and seed-independent."""
    cache = Path(cache)
    target = process_dir(cache)
    card = cache / "proc_card.dat"
    # The *proc* card, not `group.card` — that one is the Pythia shower card this adapter renders,
    # and MadGraph would find no `generate` line in it at all.
    text = cache_text(group)
    return [base.Stage(
        name="madgraph-build", role="prepare", phase=0,
        argv=[executable(config), str(card)],
        cwd=cache, parser=NAME,
        writes=[(str(card), text.rstrip() + f"\noutput {target}\n")],
        produces=[target / "bin" / "generate_events"],
        note="process directory, cached across seeds and event counts")]


def generate(config: Any, group: Any, fifo: Path) -> base.Stage:
    """The launch that writes the LHE. `fifo` is unused: MadGraph writes a file (04 §7)."""
    from . import cache as cache_module

    entry = cache_module.for_group(config, group)
    if entry is None:                                  # pragma: no cover - prepare always exists
        raise HepError("the MadGraph adapter needs a prepare cache entry")
    directory = Path(fifo).parent
    script = directory / "launch.dat"
    return base.Stage(
        name="madgraph-launch", role="generate", phase=1,
        argv=[executable(config), str(script)],
        cwd=directory, parser=NAME,
        writes=[(str(script), getattr(group, "launch", "") or "")],
        produces=[process_dir(entry.directory) / LHE.parent / (LHE.name + ".gz")],
        note="matrix-element events, as LHE")


def unpack(config: Any, group: Any, fifo: Path) -> base.Stage:
    """Decompress the LHE **into the point directory** (04 §7).

    Two reasons it lands there rather than staying in the cache. Pythia's gzip support is a
    build-time option (01 §4), so a run's success would otherwise depend on how Pythia happened to be
    compiled; and the shower card has to name the file, while the cache's path is a hash of the proc
    card — which the card cannot contain without the key depending on itself.
    """
    from . import cache as cache_module

    entry = cache_module.for_group(config, group)
    source = process_dir(entry.directory) / (LHE.name + ".gz")
    source = process_dir(entry.directory) / LHE.parent / (LHE.name + ".gz")
    target = lhe_path(config, group)
    return base.Stage(
        name="madgraph-unpack", role="generate", phase=2,
        argv=["sh", "-c", f'gunzip -c "$1" > "$2"', "sh", str(source), str(target)],
        cwd=Path(fifo).parent, parser="",
        produces=[target],
        note="Pythia's own gzip support is build-dependent")


def lhe_path(config: Any, group: Any) -> Path:
    """Where the shower card points: beside the point's own results, not in the cache."""
    from ..plan import naming

    return naming.point_dir(config, group.name) / "events.lhe"


def stages(config: Any, group: Any, fifo: Path) -> list[base.Stage]:
    """Launch then unpack: `generate` alone is not enough for a tool that writes a file."""
    return [generate(config, group, fifo), unpack(config, group, fifo)]
