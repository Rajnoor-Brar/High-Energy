"""External Delphes: a tee, a stage, and a sidecar (05 §5, P7-S08).

Delphes is not a generator, so this is not a generator adapter — it is a *sink* with a process behind
it. `Sink::Delphes` writes HepMC3 and `DelphesHepMC3` reads it, in its own process:

    hep-run ──▶ events.delphes.hepmc ──▶ DelphesHepMC3 <card> delphes.root <events>

In its own process on purpose. Delphes declares a global `class Event` and carries ROOT global state
(13 §3), and the namespace here is called `Events` precisely because of that clash. Running it beside
us rather than inside us keeps both halves' globals to themselves.

**A file, not a FIFO — measured, and not what 05 §5 assumed.** `DelphesHepMC3` sizes its input before
reading it and *skips any input whose length is zero* (`readers/DelphesHepMC3.cpp:160-169`:
`fseek(END); ftello(); if (length <= 0) { fclose; continue; }`). A FIFO always measures zero, so
Delphes opened the pipe, decided there was nothing in it and exited, and `hep-run` then died writing
into a closed pipe. There is no flag for it; the sizing is how its progress bar works.

So the tee writes a **regular** HepMC3 file and the Delphes stage runs in the phase *after*
`hep-run` — the same shape as MadGraph's LHE, and for the same reason: a tool that seeks cannot be
streamed to. The cost is an uncompressed intermediate on disk, which is why it is deleted once
Delphes has succeeded unless `[delphes].keep_events` says otherwise.

`delphes.root` is ROOT, and ROOT is read by `hep proc` (12), never by `hep-run`. What this writes
beside it is a small JSON sidecar saying which card produced it and from what, so the ROOT file is
traceable without opening it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..errors import HepError
from . import base

NAME = "delphes"

#: The intermediate the tee writes and Delphes reads. Beside the point's results, not in `/tmp`
#: (00/B19). A regular file: Delphes cannot read a pipe (see the module note).
FIFO_NAME = "events.delphes.hepmc"

#: What Delphes writes, and what `hep proc` later reads (12 §1).
OUTPUT = "delphes.root"

#: Written beside it, so a ROOT file can be traced without opening it.
SIDECAR = "delphes.json"


def executable(config: Any = None) -> str:
    if config is not None:
        return base.executable_for("DelphesHepMC3", config)
    return shutil.which("DelphesHepMC3") or "DelphesHepMC3"


def probe(config: Any = None) -> base.Capabilities:
    found = base.Capabilities(tool=NAME, hepmc=True)
    path = executable(config)
    found.executable = path
    if shutil.which(path) is None and not Path(path).is_file():
        found.detail = ("no `DelphesHepMC3` on PATH and no `tools.DelphesHepMC3.exe` in the machine "
                        "file")
        return found
    found.available = True
    return found


def card_path(config: Any) -> Path:
    """`[delphes].card`, resolved next to the config file like every other card (03 §7)."""
    declared = getattr(getattr(config, "delphes", None), "card", "") or ""
    if not declared:
        raise HepError("[delphes] has no card, but a Delphes stage was asked for",
                       hint='card = "cards/delphes_card_CMS.tcl", relative to this file')
    candidate = Path(declared).expanduser()
    if candidate.is_absolute():
        return candidate
    return (config.path.parent / candidate).resolve()


def enabled(config: Any) -> bool:
    return bool(getattr(getattr(config, "delphes", None), "card", ""))


def fifo_path(directory: Path) -> Path:
    return Path(directory) / FIFO_NAME


def sink_document(directory: Path) -> dict[str, Any]:
    """The `[[sink]]` entry that makes `hep-run` write the tee."""
    return {"kind": NAME, "dir": str(fifo_path(directory))}


def stage(config: Any, group: Any, directory: Path) -> base.Stage:
    """`DelphesHepMC3 <card> <out.root> <events>`, **after** `hep-run` (see the module note).

    Written under a temporary name and renamed on success, which is the rule every other output in
    this project follows (D22) and which Delphes needs more than most: it **creates the ROOT file
    before it reads the card**, so a card with a syntax error leaves a `delphes.root` that opens,
    contains nothing, and looks exactly like a result. Measured in P7-S08.

    Delphes also refuses to overwrite an existing output — a good rule, and a bad interaction with
    `--rerun` — so any stale one is cleared first. All in one shell command, because a stage is one
    process.
    """
    directory = Path(directory)
    card = card_path(config)
    output = directory / OUTPUT
    events = fifo_path(directory)
    return base.Stage(
        name="delphes", role="detector",
        argv=["sh", "-c",
              'rm -f "$2" "$2.part"; "$0" "$1" "$2.part" "$3" && mv "$2.part" "$2"',
              executable(config), str(card), str(output), str(events)],
        cwd=directory, parser=NAME,
        produces=[output],
        note="detector simulation, reading the events the run teed out")


def sidecar(config: Any, group: Any, directory: Path) -> dict[str, Any]:
    """What produced `delphes.root`, so the ROOT file is traceable without opening it."""
    from ..plan import hashing

    card = card_path(config)
    return {
        "schema": 1,
        "point": getattr(group, "name", ""),
        "hash": getattr(getattr(group, "identity", None), "hash", ""),
        "card": str(card),
        "card_sha256": hashing.sha256_bytes(hashing.read_card(card)) if card.is_file() else "",
        "events": str(fifo_path(directory)),
        "output": str(Path(directory) / OUTPUT),
    }


def write_sidecar(config: Any, group: Any, directory: Path) -> Path:
    path = Path(directory) / SIDECAR
    path.write_text(json.dumps(sidecar(config, group, directory), indent=2) + "\n",
                    encoding="utf-8")
    return path
