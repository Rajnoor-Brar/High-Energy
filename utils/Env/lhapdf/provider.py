"""utils/Env/lhapdf/provider.py — LHAPDF as a provider: is a PDF set a tool is given installed (V60, C10).

A provider is the first of the tool categories (01 §3): it gives other tools data. A tool folder's
quantity mapping names a check, `check = "lhapdf:<form>"` (utils/Env/<tool>/quantities.toml), and the
runner calls `check(form, value, where)` at plan time, so a missing set is refused before anything runs.

* "bare": the value is a bare set name, `<set>[/member]` (Sherpa's PDF_SET).
* "pythia": Pythia's PDF:pSet as written (V40: no prefix is added): one of Pythia's own sets (a number its
  documentation lists, PDFSelection.xml), "LHAPDF6:<set>[/member]" (the set must be installed), or a grid
  file. A bare name that is an installed LHAPDF set is refused: Pythia would read it as a file.
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
from pathlib import Path

from runner.errors import HepError

PREFIXES = ("LHAPDF6:", "LHAPDF5:")


def data_dirs() -> list[str]:
    return [d for d in os.environ.get("LHAPDF_DATA_PATH", "").split(":") if d]


def installed(name: str) -> bool:
    return any((Path(d) / name / f"{name}.info").is_file() for d in data_dirs())


def require(name: str, where: str) -> None:
    if not installed(name):
        raise HepError(f"the PDF set '{name}' is not installed", where=where,
                       hint=f"lhapdf install {name}   (searched LHAPDF_DATA_PATH: {', '.join(data_dirs()) or 'unset'})")


@functools.cache
def pythia_sets() -> tuple[int, ...]:
    """Pythia's own proton PDF sets, from its documentation (PDF:pSet's options); () when not found."""
    try:
        xmldoc = subprocess.run(["pythia8-config", "--xmldoc"], capture_output=True, text=True, timeout=30).stdout.strip()
        text = (Path(xmldoc) / "PDFSelection.xml").read_text(encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return ()
    block = re.search(r'<word name="PDF:pSet".*?</word>', text, re.S)
    return tuple(int(v) for v in re.findall(r'<option value="(\d+)"', block.group(0))) if block else ()


def check(form: str, value, where: str) -> None:
    text = str(value)
    if form == "bare":
        if text.startswith(PREFIXES):
            raise HepError(f"'{text}': this tool takes the bare LHAPDF set name", where=where,
                           hint=f"write '{text.split(':', 1)[1]}'")
        require(text.split("/")[0], where)
    elif form == "pythia":
        if (isinstance(value, int) and not isinstance(value, bool)) or text.isdigit():
            sets = pythia_sets()
            if sets and int(text) not in sets:
                raise HepError(f"PDF:pSet = {text} is not one of Pythia's own sets", where=where,
                               hint=f"Pythia's sets: {sets[0]}–{sets[-1]} (PDFSelection.xml); an LHAPDF set is \"LHAPDF6:<set>\"")
            return
        if text.startswith(PREFIXES):
            require(text.split(":", 1)[1].split("/")[0], where)
        elif installed(text.split("/")[0]):
            raise HepError(f"PDF:pSet = '{text}' is an LHAPDF set, which Pythia reads only as LHAPDF6:{text}",
                           where=where, hint=f"write the value as \"LHAPDF6:{text}\"")
    else:
        raise HepError(f"lhapdf has no check '{form}'", where=where, hint="bare or pythia")
