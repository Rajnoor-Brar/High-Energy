"""utils/Env/madgraph/render.py — MadGraph's launch script and proc card (docs/06_Internals.md §16, L14).

MadGraph hands over a matrix element, as an LHE file, and a `pythia` tool showers it. Two cards:

* the **proc card** (the base) becomes `prepare_card`: the processes and `output` into the prepare
  cache. That is minutes of Fortran and depends on the processes only, so the cache is keyed on
  the base card (`[prepare] key = "base"`), never on beams, events or seed;
* the **point card** is a launch script: the run named after the seed (so the LHE path is known),
  no shower or detector (the chain has its own), then the run-card values: nevents, iseed, the
  beams as lpp and their energies.

Both begin with `set automatic_html_opening False`: MadGraph opens a browser from a batch run
otherwise (v1's 00/B39).
"""

from __future__ import annotations

import re

from runner.errors import HepError

QUIET = "set automatic_html_opening False"


def card(bases: list[str], overrides: list, context: dict) -> str:
    for text in bases:
        for line in text.splitlines():
            head = line.strip().split(" ", 1)[0].lower()
            if head in ("output", "launch"):
                raise HepError(f"the proc card has its own `{head}` line", where=f"[tools.{context.get('tag')}].baseconfig",
                               hint="the runner writes `output` (into the prepare cache) and `launch` (with the point's values)")
        if not re.search(r"^\s*(generate|add\s+process)\s", text, re.M):
            raise HepError("the proc card generates no process", where=f"[tools.{context.get('tag')}].baseconfig")
    lines = [QUIET, "launch {prepared}/process -n r{seed}", "shower=OFF", "detector=OFF", "analysis=OFF", "done",
             "set iseed {seed}"]
    for key, value, origin in overrides:               # the runner's Override (L26)
        if key == "beams":
            for index, code in enumerate(value, start=1):
                lpp = {int(k): v for k, v in context["render"]["lpp"].items()}
                if int(code) not in lpp:
                    raise HepError(f"no MadGraph beam type (lpp) for PDG {code}", where=origin)
                lines.append(f"set lpp{index} {lpp[int(code)]}")
        elif isinstance(value, list):
            raise HepError(f"'{key}' takes one value, not a list", where=origin)
        else:
            lines.append(f"set {key} {value}")
    lines.append("done")
    return "\n".join(lines) + "\n"


def prepare_card(lines: list[str], bases: list[str], context: dict) -> str:
    """The proc card with `output` into the cache: the process directory, built once."""
    return "\n".join([QUIET, *[b.rstrip() for b in bases], f"output {context['prepared']}/process -f"]) + "\n"
