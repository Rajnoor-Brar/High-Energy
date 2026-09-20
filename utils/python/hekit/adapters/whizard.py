"""Whizard: SINDARIN rendering and stages (04 §5).

SINDARIN is a *script*, not a settings file, so "base plus overrides" works the opposite way round
from every other adapter here: the point card comes **first** and then includes the base, because a
SINDARIN assignment takes effect when it is executed and `integrate`/`simulate` read whatever is set
at that moment. Pythia's "later wins" would be exactly wrong.

That makes one rule load-bearing: **the base must not set what the plan owns.** A base that assigns
`n_events` or `seed` runs after our override and silently replaces it, so the adapter parses for that
and refuses (04 §5).

Two other Whizard-specific facts:

* **particle names, not PDG codes.** `beams = p, e1` — Whizard speaks its model's language, so the
  ids the planner resolved are mapped through the active model file rather than through a hard-coded
  table that would go stale the moment someone used a different model.
* **Whizard is parton-level** unless the base card turns on a shower and hadronisation. That is a
  physics difference from every other generator here, so it is reported rather than assumed.

Compiling the matrix-element library and integrating is the expensive, seed-independent half, so it
is a cached `prepare` stage like Sherpa's (04 §1).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..errors import HepError
from . import base

NAME = "whizard"

#: A FIFO between two processes on one machine.
STREAM_COMPRESSION = "none"

#: Whizard appends `.hepmc` to `$sample`, so the stem is the FIFO name without that suffix (04 §5).
SAMPLE_SUFFIX = ".hepmc"

#: Keys the plan owns. A base card that assigns any of them runs *after* the override and wins.
RESERVED = {
    "seed": "[run] seed (the seed block is derived from the point identity)",
    "n_events": "[run] events",
    "sqrts": "[beams] energies",
    "beams": "[beams] ids",
    "beams_momentum": "[beams] energies",
    "$sample": "the sink chain owns where events go",
    "sample_format": "the sink chain owns the event format",
}

#: `key = value` at the start of a line, which is how SINDARIN assigns. The sigils matter: `$name` is
#: a string variable and `?name` is a flag, and a regex that only knew about bare names would not see
#: `?hadronization_active` — so it could neither report the parton level nor refuse a base card that
#: turned something the plan owns back on. Enough to catch those without pretending to be a parser.
ASSIGNMENT = re.compile(r"^\s*([?$]?[A-Za-z_][A-Za-z0-9_]*)\s*=")

#: How a base card declares its structure functions (04 §5).
#:
#: `beams` is the plan's — it names the particles — but the *structure-function chain* after the `=>`
#: is physics only the base card can state: `pdf_builtin` for the proton, `epa` for the photon flux.
#: Neither half can be written without the other, so the base states its half here and the adapter
#: assembles the line. A comment rather than a SINDARIN variable because SINDARIN has nowhere to put
#: one that `beams` would read.
STRUCTURE = re.compile(r"^\s*#\s*hep:\s*beam_structure\s*=\s*(.+?)\s*$", re.M)

#: `particle NAME <pdg>` … `name a b c` … `anti x y z`, as the model files are written.
_PARTICLE = re.compile(r"^\s*particle\s+(\S+)\s+(-?\d+)")
_NAMES = re.compile(r"^\s*(name|anti)\s+(.*)$")


def models_dir(config: Any = None) -> Path:
    """Where the model files live, derived from the executable rather than hard-coded (N6)."""
    path = Path(executable(config))
    found = path.parent.parent / "share" / "whizard" / "models"
    return found


def model_names(model: str = "SM", config: Any = None) -> dict[int, str]:
    """PDG code → the model's own name for it, both signs.

    Parsed from the model file so a different model brings its own names, rather than from a table
    here that would be right for the SM and quietly wrong for anything else.
    """
    path = models_dir(config) / f"{model}.mdl"
    if not path.is_file():
        raise HepError(f"no Whizard model file for '{model}'",
                       hint=f"looked in {models_dir(config)}; set `tools.whizard.exe` if Whizard is "
                            "installed somewhere else")
    found: dict[int, str] = {}
    code: int | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        particle = _PARTICLE.match(line)
        if particle is not None:
            code = int(particle.group(2))
            continue
        if code is None:
            continue
        names = _NAMES.match(line)
        if names is None:
            continue
        # The first token is the canonical name; quoted spellings like "e-" are aliases.
        tokens = [token for token in names.group(2).split() if not token.startswith('"')]
        if not tokens:
            continue
        found.setdefault(code if names.group(1) == "name" else -code, tokens[0])
    return found


def particle_name(pdg: int, *, model: str = "SM", config: Any = None) -> str:
    names = model_names(model, config)
    if int(pdg) not in names:
        raise HepError(f"the {model} model has no name for PDG {pdg}",
                       hint="Whizard takes particle names, not codes; a beam it cannot name cannot "
                            "be set up (04 §5)")
    return names[int(pdg)]


# ── the card ─────────────────────────────────────────────────────────────────

def beam_structure(text: str) -> str:
    """The `=> sf1, sf2` chain a base card declares, or empty for bare beams."""
    found = STRUCTURE.search(text or "")
    return found.group(1).strip() if found else ""


def card_defaults(text: str) -> dict[str, str]:
    """Every assignment the card makes, for the identity hash (03 §5)."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ASSIGNMENT.match(stripped)
        if match is not None:
            found[match.group(1).lower()] = stripped.split("=", 1)[1].strip()
    return found


def check_card(text: str, where: str) -> None:
    """The insertion rule (04 §5): the base runs after the override, so it may not set what we set."""
    offenders = sorted(key for key in card_defaults(text) if key in RESERVED)
    if offenders:
        listed = ", ".join(offenders)
        raise HepError(
            f"the base card sets {listed}, which the plan owns", where=where,
            hint="a SINDARIN base is read *after* the point card, so an assignment here replaces "
                 f"the plan's: remove it. {RESERVED[offenders[0]]} is where it comes from")
    base.check_beam_keys(NAME, card_defaults(text), where=where)


def check_overrides(point: Any, where: str) -> None:
    names = [name for name, _, _ in getattr(point, "settings", ())]
    for name in names:
        if str(name).lower() in RESERVED:
            raise HepError(f"a quantity sets {name}, which the plan owns", where=where,
                           hint=RESERVED[str(name).lower()])
    base.check_beam_keys(NAME, names, where=where)


def frame_warning(point: Any) -> str:
    return ""


def parton_level(text: str) -> bool:
    """Is this card parton-level? Whizard showers and hadronises only when told to (04 §5)."""
    settings = card_defaults(text)
    return not any(settings.get(flag, "false").strip().lower() in {"true", "t"}
                   for flag in ("?hadronization_active", "?ps_fsr_active", "?shower_active"))


def value(entry: Any) -> str:
    """A SINDARIN literal: strings quoted, booleans as true/false, numbers as written."""
    if isinstance(entry, bool):
        return "true" if entry else "false"
    if isinstance(entry, (int, float)):
        return repr(entry)
    text = str(entry)
    return text if re.fullmatch(r"[-+]?[\d.eE+-]+", text) else f'"{text}"'


def render_card(point: Any, *, seeds: Any, threads: int, card_path: str = "", card_sha: str = "",
                identity_hash: str = "", origin: str = "", base_text: str = "",
                fifo: str = "", events: int = 0, model: str = "SM", config: Any = None,
                **_: Any) -> str:
    """The point card: the plan's settings, then `include` of the base (04 §5).

    The order is the whole trick. SINDARIN executes top to bottom, so everything the plan decides has
    to be assigned before the base's `integrate`/`simulate` read it.
    """
    lines = [
        "# point.sin — generated by hep, do not edit.",
        f"# point:    {getattr(point, 'name', '')}",
        f"# identity: {identity_hash}",
        f"# base:     {card_path} ({card_sha})",
        f"# origin:   {origin}",
        "#",
        "# These run *before* the base card, which is included at the end: SINDARIN executes in",
        "# order, so a setting made after `integrate` would arrive too late.",
        "",
    ]

    beams = [int(entry) for entry in (getattr(point, "beams", ()) or ())]
    energies = [float(entry) for entry in (getattr(point, "energies", ()) or ())]
    if beams:
        names = [particle_name(code, model=model, config=config) for code in beams]
        chain = beam_structure(base_text)
        lines.append(f"beams = {', '.join(names)}" + (f" => {chain}" if chain else ""))
    if len(energies) == 2:
        lines.append(f"beams_momentum = {energies[0]}, {energies[1]}")
        # Derived, and only for the log: Whizard works out the invariant mass itself.
        lines.append(f"# sqrt(s) = {2.0 * (energies[0] * energies[1]) ** 0.5:.6g} GeV")
    elif len(energies) == 1:
        lines.append(f"sqrts = {energies[0]}")

    lines.append(f"seed = {int(getattr(seeds, 'point', 0) or 0)}")
    count = int(events or getattr(point, "events", 0) or 0)
    if count:
        lines.append(f"n_events = {count}")

    for name, entry, source in getattr(point, "settings", ()):
        lines.append(f"{name} = {value(entry)}    # {source}")

    if fifo:
        # Whizard appends `.hepmc` to `$sample`, so the stem is the FIFO without that suffix — and it
        # is **absolute**, because generation runs in the cache directory (where the compiled library
        # and the grids are) while the FIFO lives beside the point's results.
        path = Path(fifo)
        stem = str(path.parent / (path.name[:-len(SAMPLE_SUFFIX)]
                                  if path.name.endswith(SAMPLE_SUFFIX) else path.stem))
        lines += ["sample_format = hepmc", f'$sample = "{stem}"']

    # Grids are read from the cache rather than rebuilt: that is the point of the prepare stage.
    lines.append("?rebuild_grids = false")
    lines.append("")
    lines.append(f'include("{card_path}")' if card_path else "")
    return "\n".join(lines) + "\n"


# ── the tool ─────────────────────────────────────────────────────────────────

def executable(config: Any = None) -> str:
    if config is not None:
        return base.executable_for("whizard", config)
    return shutil.which("whizard") or "whizard"


def probe(config: Any = None) -> base.Capabilities:
    found = base.Capabilities(tool=NAME, hepmc=True, native_rivet=False, seeds=True, prepare=True)
    path = executable(config)
    found.executable = path
    if shutil.which(path) is None and not Path(path).is_file():
        found.detail = "no `whizard` on PATH and no `tools.whizard.exe` in the machine file"
        return found
    try:
        done = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30)
        first = (done.stdout or "").strip().splitlines()
        found.version = first[0].replace("WHIZARD", "").strip() if first else ""
    except Exception:                                  # noqa: BLE001 - a version is a convenience
        found.version = ""
    found.available = True
    return found


_version: str | None = None


def version(config: Any = None) -> str:
    global _version
    if _version is None:
        _version = probe(config).version or ""
    return _version


#: The integration card, beside the grids it produces.
INTEGRATE_CARD = "integrate.sin"


def integration_card(text: str) -> str:
    """The point card with the generation lines taken out.

    The base card ends in `simulate`, and Whizard's `--execute` runs *before* the card rather than
    after, so the integration cannot be told to write nothing — it needs a card of its own. Without
    this the integration opens the FIFO and blocks for ever waiting for a reader that only the
    *generate* stage starts.
    """
    kept: list[str] = []
    for line in text.splitlines():
        key = ASSIGNMENT.match(line.strip())
        name = key.group(1).lower() if key else ""
        if name in {"n_events", "$sample", "sample_format"}:
            continue
        kept.append(line)
    kept.append("")
    kept.append("# written by hep: integration only, so nothing is generated and no FIFO is opened.")
    kept.append("n_events = 0")
    return "\n".join(kept) + "\n"


def prepare(config: Any, group: Any, cache: Path) -> list[base.Stage]:
    """Compile the matrix-element library and integrate, in the cache directory (04 §5).

    Whizard writes its compiled library, its grids and its phase-space files beside the working
    directory, which is why this runs *in* the cache: they are the reusable part.
    """
    cache = Path(cache)
    card = cache / INTEGRATE_CARD
    return [base.Stage(
        name="whizard-integrate", role="prepare",
        argv=[executable(config), "--no-banner", "--rebuild", str(card)],
        cwd=cache, parser=NAME,
        writes=[(str(card), integration_card(getattr(group, "card", "") or ""))],
        # No `produces`: what Whizard leaves behind is named after the processes and the library,
        # both of which a card can rename, and a wrong name here would silently re-integrate on
        # every run. The stage's exit code is the signal, and the marker is only written when the
        # whole point succeeded.
        note="matrix-element library and integration grids, cached across seeds")]


def generate(config: Any, group: Any, fifo: Path) -> base.Stage:
    """Generation: the same card, reading the cached grids, writing HepMC3 into the FIFO."""
    from ..plan import naming
    from . import cache as cache_module

    entry = cache_module.for_group(config, group)
    return base.Stage(
        name="whizard-generate", role="generate",
        argv=[executable(config), "--no-banner",
              str(naming.card_path(config, group.name, NAME))],
        # In the cache, not the point directory: Whizard finds its compiled library and its grids by
        # working directory, and rebuilding them per point is the cost the cache exists to avoid.
        cwd=entry.directory if entry is not None else Path(fifo).parent,
        parser=NAME, note="HepMC3 into the FIFO that hep-run reads")
