"""utils/Env/whizard/render.py — Whizard's SINDARIN point card (05_Tools.md §1, L13).

SINDARIN is a script: an assignment takes effect when it runs, and the base card's `integrate` and
`simulate` read what is set at that moment. So the point card comes FIRST and includes the base
LAST, the opposite of Pythia's "later wins", and a base that assigns what the plan owns (seed,
n_events, beams, …) is refused, because it would run after the plan's value and replace it.

* Beams are named, not numbered: PDG codes become the model's own names (SM.mdl), and the base
  card states its structure-function chain in a comment, `# hep: beam_structure = pdf_builtin, epa`.
* The events go to `$sample`, absolute, because generation runs in the prepare cache (where the
  compiled library and the grids are); Whizard appends `.hepmc` itself.
* The integration card (`prepare_card`) is the point card without `n_events`, `$sample` and
  `sample_format`: `--execute` runs before the card, so it cannot switch the output off (v1).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from runner.errors import HepError

OWNED = ("seed", "n_events", "sqrts", "beams", "beams_momentum", "$sample", "sample_format")
GENERATION = ("n_events", "$sample", "sample_format")
ASSIGNMENT = re.compile(r"^\s*([?$]?[A-Za-z_][A-Za-z0-9_]*)\s*=")
STRUCTURE = re.compile(r"^\s*#\s*hep:\s*beam_structure\s*=\s*(.+?)\s*$", re.M)


def names(model: str = "SM") -> dict[int, str]:
    """PDG code → the model's name for it, both signs, from share/whizard/models/<model>.mdl."""
    exe = shutil.which("whizard")
    path = Path(exe).resolve().parent.parent / "share" / "whizard" / "models" / f"{model}.mdl" if exe else None
    if path is None or not path.is_file():
        raise HepError(f"no Whizard model file for {model}", hint="load_hep: whizard on PATH")
    found: dict[int, str] = {}
    code = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if m := re.match(r"^\s*particle\s+\S+\s+(-?\d+)", line):
            code = int(m.group(1))
        elif code is not None and (m := re.match(r"^\s*(name|anti)\s+(.*)$", line)):
            tokens = [t for t in m.group(2).split() if not t.startswith('"')]
            if tokens:
                found.setdefault(code if m.group(1) == "name" else -code, tokens[0])
    return found


def literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    return text if re.fullmatch(r"[-+]?[\d.eE+-]+", text) else f'"{text}"'


def card(bases: list[str], overrides: list, context: dict) -> str:
    if len(bases) != 1:
        raise HepError("a Whizard tool takes one base card", where=f"[tools.{context.get('tag')}].baseconfig")
    base = bases[0]
    owned = sorted({m.group(1).lower() for line in base.splitlines() if not line.lstrip().startswith("#")
                    and (m := ASSIGNMENT.match(line)) and m.group(1).lower() in OWNED})
    if owned:
        raise HepError(f"the base card sets {', '.join(owned)}, which the plan owns",
                       where=f"[tools.{context.get('tag')}].baseconfig",
                       hint="SINDARIN runs the base after the point card, so it would replace the plan's value (L13)")
    lines = ["# SINDARIN runs in order: the plan's settings first, the base card (included last) after."]
    structure = STRUCTURE.search(base)
    for key, value, origin in overrides:               # the runner's Override (L26)
        if key == "beams":
            table = names()
            missing = [c for c in value if int(c) not in table]
            if missing:
                raise HepError(f"the SM model has no name for PDG {missing[0]}", where=origin)
            chain = f" => {structure.group(1)}" if structure else ""
            lines.append(f"beams = {', '.join(table[int(c)] for c in value)}{chain}    # {origin}")
        elif key == "beams_momentum":
            lines.append(f"beams_momentum = {', '.join(f'{float(e)} GeV' for e in value)}    # {origin}")
        else:
            lines.append(f"{key} = {literal(value)}    # {origin}")
    lines.append("seed = {seed}")
    output = context.get("output", "")
    if output:
        stem = output[: -len(".hepmc")] if output.endswith(".hepmc") else output
        lines += ["sample_format = hepmc", f'$sample = "{stem}"']
    lines.append(f'include("{context["base_paths"][0]}")')
    return "\n".join(lines) + "\n"


def prepare_card(lines: list[str], bases: list[str], context: dict) -> str:
    """The integration: the point card without the generation settings, so `simulate` makes none."""
    kept = [line for line in lines if not ((m := ASSIGNMENT.match(line)) and m.group(1).lower() in GENERATION)]
    return "\n".join(kept) + "\n"
