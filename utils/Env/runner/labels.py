"""Labels: Rivet's .plot keys, and LaTeX → ROOT TLatex (rank 1).

What the plot stage and its backends share about text: the `.plot` blocks of an analysis (build/Rivet
first, then Rivet's own), YODA's text macros, line breaks, and the conversion of a `.plot` label
($…$ LaTeX) to TLatex for Paint (V11, V41, V47, V48). A backend plugin may import this module.
"""

from __future__ import annotations

import functools
import re
import tomllib

from . import hepfiles
from .paths import repo_root

# ── LaTeX ($…$ in Rivet .plot files) → ROOT TLatex (V11) ──────────────────────────────────────

@functools.cache
def latex() -> dict:
    """utils/Env/latex.toml: the LaTeX → TLatex commands, YODA's macros, TLatex → mathtext (V61)."""
    return tomllib.loads((repo_root() / "utils" / "Env" / "latex.toml").read_text(encoding="utf-8"))


_COMMANDS = latex()["tlatex"]


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


_MACROS, _PLAIN = latex()["macros"]["math"], latex()["macros"]["text"]       # YODA's macros, in and out of math


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
    """One line: the math parts ($…$) to TLatex; the text parts kept as written, but for the escapes
    (root_text): TLatex subscripts only `_{…}`, so a bare _ in text is the character (V41, V65)."""
    parts = text.split("$")
    out = "".join(_tlatex_math(_italic(part)) if i % 2 else root_text(part) for i, part in enumerate(parts))
    out = re.sub(r"\{\s+", "{", out)
    return re.sub(r"\s+", " ", out).strip()


def _tlatex_math(out: str) -> str:
    out = re.sub(r"\\[,;:! ]", " ", out)
    upright = r"\\(?:mathrm|text|textrm|mathit|operatorname|mbox)\s*\{([^{}]*)\}"
    out = re.sub(r"(?:(?<=^[_^])|(?<=[^\\][_^]))" + upright, r"{\1}", out)   # E_T^\text{jet} keeps its group
    out = re.sub(upright, r"\1", out)
    out = re.sub(r"\\mathbf\s*\{([^{}]*)\}", r"#bf{\1}", out)
    out = re.sub(r"\\([A-Za-z]+)", lambda m: _COMMANDS.get(m.group(1), "#" + m.group(1)), out)
    out = re.sub(r"(?<!\\)([_^])(#[A-Za-z]+(?:\{[^{}]*\})?|[A-Za-z0-9+*-])", r"\1{\2}", out)   # p_\perp → p_{#perp}
    return re.sub(r"\\([<>_])", r"\1", out)                              # \_ in math: the character, bare in TLatex


# ── one label language (V65): LaTeX. TLatex, as configs wrote labels before, is converted on reading ──

_TLATEX = re.compile(r"(?<!\\)(?:#[A-Za-z]+|[_^]\{)")


def is_tlatex(text: str) -> bool:
    """A label in ROOT's TLatex (`#sqrt{s}`, `p_{T}`), not LaTeX: it has no `$` and a TLatex mark."""
    return "$" not in text and bool(_TLATEX.search(text))


def from_tlatex(text: str) -> str:
    """TLatex → LaTeX, faithfully (V65): word by word, a word with a TLatex mark becomes math, its
    `#<name>` a `\\<name>` (latex.toml's [mathtext] for the ones that differ) and its letters
    `\\mathrm{…}`, since TLatex draws them upright: `p_{T0}^{ref}` → `$\\mathrm{p}_{\\mathrm{T0}}^{\\mathrm{ref}}$`,
    which tlatex() turns back into `p_{T0}^{ref}`. A word without one is text, as written."""
    inverse = latex()["mathtext"]

    def word(w: str) -> str:
        if not _TLATEX.search(w):
            return w
        w = re.sub(r"(?<!\\)#([A-Za-z]+)", lambda m: inverse[m[1]] if m[1] in inverse and not inverse[m[1]].isalpha()
                   else "\\" + inverse.get(m[1], m[1]), w)                  # #sqrt → \sqrt, #it → \mathit, #LT → <
        w = re.sub(r"(?<![\\A-Za-z])([A-Za-z][A-Za-z0-9]*)", lambda m: "\\mathrm{" + m[1] + "}", w)   # upright, as TLatex
        w = re.sub(r"\\(mathit|mathbf)\{\\mathrm\{([^{}]*)\}\}", r"\\\1{\2}", w)      # #it{Q}: italic after all
        w = re.sub(r"(?<!\\)_(?!\{)", r"\\_", w)                        # a bare _ in math: the character
        return f"${w}$"
    return " ".join(word(w) for w in text.split(" "))


def mathtext(text: str) -> str:
    """A LaTeX label as matplotlib draws it (the yoda backend, V65): YODA's macros expanded, `<` and `>`
    of the text set as math (LaTeX's text font prints > as ¿), the escapes \\_ \\^ \\# of the text the
    characters, and ':' (which separates mkhtml's options) a space."""
    parts = macros(text).split("$")
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"[<>]", lambda m: f"${m[0]}$", re.sub(r"\\([_^#\\])", r"\1", parts[i]))
    return "$".join(parts).replace(":", " ")


def canonical(text: str) -> str:
    """A label as the plot stage keeps it: LaTeX. A TLatex one (configs not yet migrated) is converted."""
    return from_tlatex(text) if is_tlatex(text) else text


@functools.cache
def _plot_blocks(analysis: str) -> tuple:
    """The `# BEGIN PLOT` blocks of an analysis's .plot file: build/Rivet first, then Rivet's own."""
    for place in hepfiles.rivet_dirs():
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
