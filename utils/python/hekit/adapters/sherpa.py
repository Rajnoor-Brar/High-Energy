"""Sherpa: card merging, rendering and stages (04 §4).

Sherpa's run card is YAML, so "base card plus overrides" is a **deep merge** rather than the
append-and-let-the-last-line-win that Pythia's flat `.cmnd` allows. A point's settings name a path
into that tree — `EPA:Q2Max`, `PDF_SET`, `SCALES` — and the rendered `point.yaml` is the merged
result, written whole so provenance is complete. Sherpa would also take `'KEY: value'` arguments on
the command line, but then the card on disk would not be the card that ran.

Three things this adapter knows that cost P7-S02 an afternoon to find out:

1. **`MPI_PDF_SET` is a separate key from `PDF_SET`.** Sherpa's multiple-interaction model reads its
   own, and falls back to the compiled default `PDF4LHC21_40_pdfas` when it is absent — a set that is
   not installed here, so the run dies in initialisation naming a PDF the card never mentions. A
   proton PDF written to `PDF_SET` is mirrored into `MPI_PDF_SET` unless the card set it itself.
2. **Beam order matters more than it looks.** Sherpa's own HERA example puts the lepton on beam 1,
   which sends the proton along −z and mirrors every pseudorapidity distribution. The planner's beam
   order is used as given, and `[beams].ids` for this project puts the proton first.
3. **Amisic MPI is very slow for photoproduction here** (00/B31's neighbour: 0 events in 768 s
   against 2 000 in 4 s with MPI off). Not something the adapter can fix; the base card carries the
   note.

Integration is a `prepare` stage, cached by `adapters.cache`: it is seed- and event-count-independent,
which is exactly what the cache key covers, so a seed-replica study integrates once (04 §1).
"""

from __future__ import annotations

import copy
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..errors import HepError
from . import base

NAME = "sherpa"

#: A FIFO between two processes on one machine; compressing it buys nothing.
STREAM_COMPRESSION = "none"

#: Sherpa's own results directory inside a cache entry (04 §4). Sherpa writes `Results.zip`.
RESULTS_DIR = "Results"

#: Keys the plan owns; a base card or an override that sets them is a planning error (04 §8).
RESERVED = {
    "beams": "[beams] ids",
    "beam_energies": "[beams] energies",
    "random_seed": "[run] seed (the seed block is derived from the point identity)",
    "events": "[run] events",
    "event_output": "the analyzer chain owns where events go",
    "result_directory": "the prepare cache owns this",
}

#: Written into the point card by the planner, never by a user.
OWNED = ("BEAMS", "BEAM_ENERGIES", "RANDOM_SEED", "EVENTS", "EVENT_OUTPUT", "RESULT_DIRECTORY",
         "ANALYSIS", "RIVET", "ANALYSIS_OUTPUT")

#: `rivet.mode = "native"` means Sherpa runs Rivet itself, so there is no `hep-run` in the chain.
RUNS_RIVET = True


def _yaml():
    try:
        import yaml
    except ImportError as error:                       # pragma: no cover - part of the venv
        raise HepError("reading a Sherpa card needs PyYAML",
                       hint="`hep doctor` reports what is importable") from error
    return yaml


# ── the card ─────────────────────────────────────────────────────────────────

def normalise_key(key: str) -> str:
    return "".join(str(key).split()).lower()


def load(text: str) -> dict:
    """A Sherpa YAML card as a dict.

    Sherpa's own cards contain values YAML cannot parse as anything but strings — `METS{H_T2/4}` has
    a brace in it — so the loader is the safe one and everything stays a scalar until Sherpa reads it.
    """
    yaml = _yaml()
    try:
        document = yaml.safe_load(text) or {}
    except Exception as error:                         # noqa: BLE001 - yaml's own error text is good
        raise HepError("the Sherpa card is not valid YAML", hint=str(error)) from None
    if not isinstance(document, dict):
        raise HepError("a Sherpa card must be a YAML mapping at the top level")
    return document


def flatten(document: Any, prefix: str = "") -> dict[str, str]:
    """`{"EPA": {"Q2Max": 1}}` → `{"epa:q2max": "1"}`, for the identity hash and clash checks."""
    found: dict[str, str] = {}
    if isinstance(document, dict):
        for key, value in document.items():
            found.update(flatten(value, f"{prefix}:{key}" if prefix else str(key)))
    elif isinstance(document, list):
        found[normalise_key(prefix)] = ", ".join(str(entry) for entry in document)
    else:
        found[normalise_key(prefix)] = str(document)
    return found


def card_defaults(text: str) -> dict[str, str]:
    """Every setting a card applies, flattened. Used by the identity hash (03 §5)."""
    if not text.strip():
        return {}
    return flatten(load(text))


def check_card(text: str, where: str) -> None:
    """A base card may not set what the plan owns."""
    for key in card_defaults(text):
        head = key.split(":")[0]
        if head in RESERVED:
            raise HepError(f"the base card sets {head}, which the plan owns", where=where,
                           hint=f"remove it; it comes from {RESERVED[head]}")
    base.check_beam_keys(NAME, card_defaults(text), where=where)


def check_overrides(point: Any, where: str) -> None:
    """The same rule for a point's `setting` quantities."""
    names = [name for name, _, _ in getattr(point, "settings", ())]
    for name in names:
        head = normalise_key(name).split(":")[0]
        if head in RESERVED:
            raise HepError(f"a quantity sets {head}, which the plan owns", where=where,
                           hint=f"use {RESERVED[head]} instead")
    base.check_beam_keys(NAME, names, where=where)


def frame_warning(point: Any) -> str:
    return ""


def assign(document: dict, path: str, value: Any) -> None:
    """Set `EPA:Q2Max` (or `EPA.Q2Max`) inside a nested mapping, making the branches on the way."""
    parts = [part for part in re.split(r"[:.]", str(path)) if part]
    if not parts:
        return
    node = document
    for part in parts[:-1]:
        existing = node.get(part)
        if not isinstance(existing, dict):
            existing = {}
            node[part] = existing
        node = existing
    node[parts[-1]] = value


def merge(base_document: dict, overrides: dict) -> dict:
    """Deep merge: a mapping recurses, anything else replaces.

    A list replaces rather than extends, because Sherpa's lists are positional — `PDF_SET` is one
    entry per beam, and appending to it would silently mean something else.
    """
    merged = copy.deepcopy(base_document)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def mirror_mpi_pdf(document: dict) -> None:
    """Keep `MPI_PDF_SET` in step with `PDF_SET` (see the module note).

    Only when the card has not set it itself: a card that deliberately gives the MPI a different PDF
    is making a physics choice, and this is a safety net, not an opinion.
    """
    for source, target in (("PDF_SET", "MPI_PDF_SET"), ("PDF_LIBRARY", "MPI_PDF_LIBRARY")):
        if source in document and target not in document:
            document[target] = copy.deepcopy(document[source])


def render_card(point: Any, *, seeds: Any, threads: int, card_path: str = "", card_sha: str = "",
                identity_hash: str = "", origin: str = "", base_text: str = "",
                fifo: str = "", events: int = 0, mode: str = "inprocess",
                analyses: Any = (), **_: Any) -> str:
    """The point card: the base deep-merged with this point's settings and the plan's run control."""
    yaml = _yaml()
    document = merge(load(base_text) if base_text else {}, {})

    for name, value, _ in getattr(point, "settings", ()):
        assign(document, name, value)

    beams = list(getattr(point, "beams", ()) or ())
    energies = list(getattr(point, "energies", ()) or ())
    if beams:
        document["BEAMS"] = [int(entry) for entry in beams]
    if len(energies) == 2:
        document["BEAM_ENERGIES"] = [float(energies[0]), float(energies[1])]
    elif len(energies) == 1:
        # A scalar sqrt(s) is split evenly, which is what Sherpa's own single-value form means.
        document["BEAM_ENERGIES"] = [float(energies[0]) / 2.0, float(energies[0]) / 2.0]

    document["RANDOM_SEED"] = int(getattr(seeds, "point", 0) or 0)
    count = int(events or getattr(point, "events", 0) or 0)
    if count:
        document["EVENTS"] = count
    # `RESULT_DIRECTORY` is deliberately absent: it points at the prepare cache, whose key is this
    # very card, so putting it in would be circular. It goes on the command line instead (04 §4).

    if mode == "native":
        # Sherpa runs Rivet itself: no FIFO, no `hep-run`, and no store, module or Delphes analyzer
        # (04 §4). `ANALYSIS_OUTPUT` is the YODA's stem, so it lands where every other point's does.
        document.pop("EVENT_OUTPUT", None)
        document["ANALYSIS"] = "Rivet"
        document["RIVET"] = {"--analyses": [str(entry) for entry in analyses]}
        document["ANALYSIS_OUTPUT"] = "analysis"
    elif fifo:
        # `HepMC3_GenEvent[name]` writes exactly `name` — measured, not assumed: given `events` it
        # produces a file called `events`, with no extension of its own. The full FIFO name goes in.
        #
        # **Relative**, not absolute: Sherpa prepends "./" to what it is given, so an absolute path
        # becomes ".//home/..." and cannot be opened. The generate stage runs in the point directory,
        # so the bare name is both correct and free of a per-point path — which keeps it out of the
        # prepare-cache key too.
        document["EVENT_OUTPUT"] = f"HepMC3_GenEvent[{Path(fifo).name}]"

    mirror_mpi_pdf(document)

    header = (f"# point.yaml — generated by hep, do not edit.\n"
              f"# point:    {getattr(point, 'name', '')}\n"
              f"# identity: {identity_hash}\n"
              f"# base:     {card_path} ({card_sha})\n"
              f"# origin:   {origin}\n")
    return header + yaml.safe_dump(document, sort_keys=False, default_flow_style=None)


# ── the tool ─────────────────────────────────────────────────────────────────

def executable(config: Any = None) -> str:
    return base.executable_for("Sherpa", config) if config is not None else (
        shutil.which("Sherpa") or "Sherpa")


def probe(config: Any = None) -> base.Capabilities:
    found = base.Capabilities(tool=NAME, hepmc=True, native_rivet=True, seeds=True, prepare=True)
    path = executable(config)
    found.executable = path
    if shutil.which(path) is None and not Path(path).is_file():
        found.detail = "no `Sherpa` on PATH and no `tools.Sherpa.exe` in the machine file"
        return found
    try:
        done = subprocess.run([str(Path(path).parent / "Sherpa-config"), "--version"],
                              capture_output=True, text=True, timeout=30)
        found.version = (done.stdout or "").strip()
    except Exception:                                  # noqa: BLE001 - a version is a convenience
        found.version = ""
    found.available = True
    return found


#: Memoised, because it is a subprocess and the planner asks once per group (04 §8).
_version: str | None = None


def version(config: Any = None) -> str:
    """Sherpa's version, part of the prepare-cache key: a grid is not portable across versions."""
    global _version
    if _version is None:
        _version = probe(config).version or ""
    return _version


def prepare(config: Any, group: Any, cache: Path) -> list[base.Stage]:
    """Integration: the point's own card, run with `-e 0`, writing its grid into the cache (04 §4).

    Seed- and event-count-independent, which is what makes it cacheable — and it is the expensive
    half of a Sherpa run, so a seed study that integrated ten times would be ten times too slow.

    It reads the *point's* card rather than a copy in the cache, because there is only ever one card
    and copying it would give two things that could drift. What differs is supplied on the command
    line: where the grid goes, and that nothing is written out. `EVENT_OUTPUT: None` matters — with
    it left in place Sherpa opens the HepMC3 output at initialisation, and that output is a FIFO, so
    the integration would block forever waiting for a reader that only the generate stage starts.
    """
    from ..plan import naming

    cache = Path(cache)
    card = naming.card_path(config, group.name, NAME)
    return [base.Stage(
        name="sherpa-integrate", role="prepare",
        argv=[executable(config), "-f", str(card), "-e", "0",
              f"RESULT_DIRECTORY: {cache / RESULTS_DIR}", "EVENT_OUTPUT: None"],
        cwd=cache, parser=NAME,
        produces=[cache / f"{RESULTS_DIR}.zip"],
        note="integration grid, cached across seeds and event counts")]


def generate(config: Any, group: Any, fifo: Path) -> base.Stage:
    """Generation: the same card, pointed at the cached integration, writing HepMC3 to the FIFO."""
    from ..plan import naming
    from . import cache as cache_module

    directory = Path(fifo).parent
    entry = cache_module.for_group(config, group)
    native = getattr(config.rivet, "mode", "inprocess") == "native"
    environment: dict[str, str] = {}
    if native:
        # Sherpa loads the analysis itself, so it needs the plugin path that `Analyzer::Rivet` would
        # otherwise set for us (05 §5). A stage carries its own environment for exactly this.
        found = [str(entry) for entry in _analysis_paths(config)]
        if found:
            import os

            environment["RIVET_ANALYSIS_PATH"] = ":".join(
                found + ([os.environ["RIVET_ANALYSIS_PATH"]]
                         if os.environ.get("RIVET_ANALYSIS_PATH") else []))
    return base.Stage(
        name="sherpa-generate", role="generate",
        argv=[executable(config), "-f", str(naming.card_path(config, group.name, NAME)),
              f"RESULT_DIRECTORY: {entry.directory / RESULTS_DIR}"],
        cwd=directory, parser=NAME, env=environment,
        note="runs Rivet itself" if native else "HepMC3 into the FIFO that hep-run reads")


def _analysis_paths(config: Any) -> list[Path]:
    from ..plan.build import analysis_search_paths

    return list(analysis_search_paths(config))
