"""Labels: Rivet's .plot keys, and LaTeX → ROOT TLatex (rank 1).

What the plot stage and its backends share about text: the `.plot` blocks of an analysis (build/Rivet
first, then Rivet's own), YODA's text macros, line breaks, and the conversion of a `.plot` label
($…$ LaTeX) to TLatex for Paint (V11, V41, V47, V48). A backend plugin may import this module.
"""

from __future__ import annotations

import functools
import re
import subprocess
from pathlib import Path

from .paths import build_root

# ── LaTeX ($…$ in Rivet .plot files) → ROOT TLatex (V11) ──────────────────────────────────────

_COMMANDS = {"text": "", "mathrm": "", "rm": "", "mathit": "", "textrm": "", "mathbf": "#bf",
             "left": "", "right": "", "le": "#leq", "ge": "#geq", "to": "#rightarrow", "ell": "l"}


def _italic(math: str) -> str:
    """Letters in math are italic, as LaTeX sets them: E_T → #it{E}_#it{T}; commands and upright groups are not."""
    upright = r"\\(?:mathrm|text|textrm|operatorname|mbox|mathbf)\s*\{[^{}]*\}"
    return re.sub(upright + r"|\\[A-Za-z]+|([A-Za-z]+)", lambda m: f"#it{{{m[1]}}}" if m[1] else m[0], math)


def root_text(text: str) -> str:
    """A label as ROOT's TLatex should draw it (V41). TLatex subscripts only `_{…}` and superscripts
    only `^{…}`, so a bare _ or ^ is already the character ('PDF4LHC21_40', 'E_T'); the escapes \\_,
    \\^ and \\# give the character itself, kept apart from a brace that follows it."""
    text = re.sub(r"\\([_^])(?=\{)", r"#kern[0]{\1}", text)
    return re.sub(r"\\([_^#\\])", r"\1", text)


#: YODA's own text macros (yoda/plotting/mlp_preprocessor.py), so a .plot file reads the same in both backends
_MACROS = {"GeV": r"\mathrm{GeV}", "TeV": r"\mathrm{TeV}", "MeV": r"\mathrm{MeV}", "pt": r"{p_\mathrm{T}}",
           "pT": r"{p_\mathrm{T}}", "dfrac": r"\frac", "tfrac": r"\frac"}


_PLAIN = {"GeV": "GeV", "TeV": "TeV", "MeV": "MeV", "pt": "$p_\\mathrm{T}$", "pT": "$p_\\mathrm{T}$",
          "dfrac": "\\frac", "tfrac": "\\frac"}


def macros(text: str) -> str:
    """YODA's macros expanded by us (V48): `\\mathrm{GeV}` inside `$…$`, `GeV` outside. Rivet's own
    expansion of `\\GeV` uses `\\xspace`, which LaTeX-typeset matplotlib text does not define."""
    pattern = re.compile(r"\\(" + "|".join(_MACROS) + r")(?![A-Za-z])")
    parts = text.split("$")
    return "$".join(pattern.sub(lambda m: (_MACROS if i % 2 else _PLAIN)[m[1]], part) for i, part in enumerate(parts))


def lines_of(text: str) -> list[str]:
    """A label's lines, split at `\\newline` or `\\\\`, each with its math closed: a `$…$` left open
    across a break is closed before it and reopened after (`$a \\newline b$` → `$a$`, `$b$`)."""
    lines, open_math = [], False
    for line in re.split(r"\\newline(?![A-Za-z])|\\\\", text):
        line = ("$" if open_math else "") + line.strip()
        open_math = line.count("$") % 2 == 1
        lines.append(line + ("$" if open_math else ""))
    return lines


def tlatex(text: str) -> str:
    """`$\\mathrm{d}\\sigma/\\mathrm{d}E_T$ [pb/GeV]` → `d#sigma/d#it{E}_{#it{T}} [pb/GeV]`. YODA's macros
    (`\\GeV`, `\\pT`, …) are understood, and `\\newline` (or `\\\\`) makes ROOT's `#splitline{…}{…}`; a math span
    left open across the break is closed before it and reopened after (V47)."""
    lines = [_tlatex_line(line) for line in lines_of(macros(text))]
    out = lines[-1]
    for line in reversed(lines[:-1]):
        out = f"#splitline{{{line}}}{{{out}}}"
    return out


def _tlatex_line(text: str) -> str:
    out = "".join(_italic(part) if i % 2 else part for i, part in enumerate(text.split("$")))
    out = re.sub(r"\\[,;:! ]", " ", out)
    upright = r"\\(?:mathrm|text|textrm|mathit|operatorname|mbox)\s*\{([^{}]*)\}"
    out = re.sub(r"(?<=[_^])" + upright, r"{\1}", out)                 # E_T^\text{jet} keeps its group
    out = re.sub(upright, r"\1", out)
    out = re.sub(r"\\mathbf\s*\{([^{}]*)\}", r"#bf{\1}", out)
    out = re.sub(r"\\([A-Za-z]+)", lambda m: _COMMANDS.get(m.group(1), "#" + m.group(1)), out)
    out = re.sub(r"([_^])(#[A-Za-z]+(?:\{[^{}]*\})?|[A-Za-z0-9+*-])", r"\1{\2}", out)   # p_\perp → p_{#perp}, \pi^- → #pi^{-}
    out = re.sub(r"\{\s+", "{", out)
    return re.sub(r"\s+", " ", out).strip()


@functools.cache
def _plot_blocks(analysis: str) -> tuple:
    """The `# BEGIN PLOT` blocks of an analysis's .plot file: build/Rivet first, then Rivet's own."""
    places = [build_root() / "Rivet"]
    try:
        found = subprocess.run(["rivet-config", "--datadir"], capture_output=True, text=True, timeout=30)
        places += [Path(p) for p in found.stdout.strip().split(":") if p]
    except (OSError, subprocess.SubprocessError):
        pass
    for place in places:
        path = place / f"{analysis}.plot"
        if not path.is_file():
            continue
        blocks = []
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, body in re.findall(r"^# BEGIN PLOT (\S+)\n(.*?)^# END PLOT", text, re.S | re.M):
            keys = dict(line.split("=", 1) for line in body.splitlines() if "=" in line and not line.startswith("#"))
            try:
                blocks.append((re.compile(pattern), {k.strip(): v.strip() for k, v in keys.items()}))
            except re.error:
                continue
        return tuple(blocks)
    return ()


def labels_of(path: str) -> dict:
    """The .plot keys that apply to a YODA path, later blocks winning, as in Rivet."""
    analysis, short = path.strip("/").split("/", 1)[0].split(":")[0], path.rsplit("/", 1)[-1]
    keys: dict = {}
    for pattern, block in _plot_blocks(analysis):
        if pattern.match(f"/{analysis}/{short}"):
            keys.update(block)
    return keys
