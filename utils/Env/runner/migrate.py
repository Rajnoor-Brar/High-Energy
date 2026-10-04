"""`hep migrate [CONFIG…] [--apply]` (rank 5, V79): run TOMLs and their cards in today's forms.

audit 1's final phase, "break and migrate": what the runner now refuses, rewritten in what it takes.
A dry run (the default) prints a diff per file; `--apply` writes them. Only these, by line, so comments
and layout stay:

* labels (`labels`, `title`, `title_left`, `title_right`, `legend_header`, `x_label`, `y_label`,
  `legend`): TLatex → LaTeX, as a physicist writes it (labels.natural, the user's choice);
* `[run.<cfg>].swept`: gone; under `sweep_runs = true`, the list of the configurations it ran
  (`sweep_runs = ["a", "b"]`), in the order it ran them;
* a custom tool's bare `executable` that is not built but is a command on PATH → `"path:<name>"`;
* a base card's lines for keys the runner sets (its folder's `[card] owned`), which the plan already
  said were not used;
* (V81) `[plot.overlay.<name>]` → `[plot.figures.<name>]` with `class = "overlay"`, and
  `[plot.object."<glob>"]` → `[plot.figures.<glob, as a name>]` with `objects = ["<glob>"]`, their
  subtables too; in a figure, a style key written bare (`ratio.range = […]`, which beside `ratio = true`
  is not even TOML) → `style.ratio.range`. This runs on the text first, so a file it makes TOML reads.
"""

from __future__ import annotations

import difflib
import re
import shutil
import tomllib
from pathlib import Path

from . import config as configmod
from . import tools
from .errors import HepError
from .labels import is_tlatex, natural
from .paths import config_file, resolve

LABEL_KEYS = {"labels", "title", "title_left", "title_right", "legend_header", "x_label", "y_label", "legend"}
_KEY = re.compile(r"^(\s*)([A-Za-z0-9_\-]+|\"[^\"]+\")(\s*=\s*)(.*)$")
_TABLE = re.compile(r"^\s*\[\[?([^\]]+)\]\]?\s*(#.*)?$")
_OLD_FIGURE = re.compile(r'^(\s*)\[\s*plot\.(overlay|object)\.("[^"]+"|[A-Za-z0-9_\-]+)((?:\.[A-Za-z0-9_\-]+)*)\s*\](\s*(?:#.*)?)$')
_DOTTED = re.compile(r"^(\s*)([A-Za-z_]+)(\.[A-Za-z0-9_.\-]+\s*=.*)$")
#: base.toml's tables: a key under one of them, in a figure, is a style key.
STYLE_TABLES = ("page", "text", "curves", "data", "axes", "legend", "ratio")


def _slug(glob: str, taken: set) -> str:
    """A figure's name for an object glob: d04-* → d04."""
    base = re.sub(r"[^A-Za-z0-9_]+", "_", glob.rsplit("/", 1)[-1]).strip("_") or "objects"
    name, n = base, 1
    while name in taken:
        n += 1
        name = f"{base}_{n}"
    taken.add(name)
    return name


def figure_text(text: str) -> str:
    """The old figure tables of a run TOML as [plot.figures] (V81), by line; see the module's doc."""
    taken = set(re.findall(r"^\s*\[\s*plot\.figures\.([A-Za-z0-9_\-]+)", text, re.M))
    names: dict[tuple[str, str], str] = {}
    out, in_figure = [], False
    for line in text.splitlines(keepends=True):
        old = _OLD_FIGURE.match(line.rstrip("\n"))
        if old:
            indent, kind, key, sub, tail = old.groups()
            plain = key.strip('"')
            if (kind, plain) not in names:
                names[(kind, plain)] = _slug(plain, taken) if kind == "object" else plain
                taken.add(names[(kind, plain)])
                first = True
            else:
                first = False
            own = f'{indent}class = "overlay"\n' if kind == "overlay" else f"{indent}objects = [{_literal(plain)}]\n"
            if first and sub:                              # its subtable first: the figure's own table before it
                out += [f"{indent}[plot.figures.{names[(kind, plain)]}]\n", own]
            out.append(f"{indent}[plot.figures.{names[(kind, plain)]}{sub}]{tail}\n")
            if first and not sub:
                out.append(own)
            in_figure = not sub
            continue
        header = _TABLE.match(line)
        if header:
            in_figure = header[1].strip().startswith("plot.figures.") and header[1].strip().count(".") == 2
            out.append(line)
            continue
        dotted = _DOTTED.match(line.rstrip("\n"))
        if in_figure and dotted and dotted[2] in STYLE_TABLES:
            out.append(f"{dotted[1]}style.{dotted[2]}{dotted[3]}\n")
            continue
        out.append(line)
    return "".join(out)


def _split_comment(text: str) -> tuple[str, str]:
    """A TOML value and its trailing comment: a `#` outside every string."""
    quote = None
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if quote == '"' and c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#":
            return text[:i].rstrip(), text[i:]
        i += 1
    return text.rstrip(), ""


def _literal(text: str) -> str:
    """A TOML string for it: a literal '…' when it holds a backslash (LaTeX), else a basic "…"."""
    if "\\" in text and "'" not in text and "\n" not in text:
        return f"'{text}'"
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _value(lines: list[str], start: int, head: str) -> tuple[int, str, str]:
    """The value that starts on line `start` (after `head`), maybe spread over lines: (lines it took,
    the value's text, its comments, every line's, kept)."""
    text, comment = _split_comment(head)
    comments = [comment] if comment else []
    end = start
    while True:
        try:
            tomllib.loads("x = " + text)
            return end - start + 1, text, " ".join(comments)
        except tomllib.TOMLDecodeError:
            end += 1
            if end >= len(lines) or end - start > 60:
                raise
            more, extra = _split_comment(lines[end].rstrip("\n"))
            text += " " + more.strip()
            if extra:
                comments.append(extra)


def toml_text(text: str, run=None, project: str = "") -> str:
    """One run TOML migrated (see the module's doc): its new text."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    table = ""
    swept_members = run.runs(None) if run is not None and run.sweep_runs else None
    has_swept = run is not None and any("swept" in run.raw.get("run", {}).get(k, {}) for k in run.configurations)
    i = 0
    while i < len(lines):
        line = lines[i]
        header = _TABLE.match(line)
        if header:
            table = header[1].strip()
            out.append(line)
            i += 1
            continue
        match = _KEY.match(line.rstrip("\n"))
        if not match:
            out.append(line)
            i += 1
            continue
        indent, key, eq, rest = match.groups()
        key = key.strip('"')
        taken, value_text, comment = _value(lines, i, rest)
        value = tomllib.loads("x = " + value_text)["x"]
        new = None
        if key in LABEL_KEYS:
            if isinstance(value, str) and is_tlatex(value):
                new = _literal(natural(value))
            elif isinstance(value, list) and any(isinstance(v, str) and is_tlatex(v) for v in value):
                new = "[" + ", ".join(_literal(natural(v)) if isinstance(v, str) else repr(v) for v in value) + "]"
        elif key == "swept" and table.startswith("run."):
            i += taken                                     # gone: sweep_runs lists the members
            continue
        elif key == "sweep_runs" and table == "run" and value is True and has_swept and swept_members:
            new = "[" + ", ".join(_literal(k) for k in swept_members) + "]"
        elif key == "executable" and table.startswith("tools.") and isinstance(value, str) and run is not None:
            tag = table.split(".", 1)[1].strip('"')
            tool = run.tools.get(tag)
            if tool is not None and tool.executable and not value.startswith("path:") and "/" not in value:
                built = resolve(value, "executable", project=project, where="")
                if not built.exists() and shutil.which(value):
                    new = _literal("path:" + value)
        if new is None:
            out.extend(lines[i:i + taken])
        else:
            tail = (" " + comment) if comment else ""
            out.append(_wrapped(f"{indent}{match.group(2)}{eq}", new, tail))
        i += taken
    return "".join(out)


def _wrapped(prefix: str, value: str, tail: str, width: int = 110) -> str:
    """`key = [a, b, …]`, broken after a comma once a line passes `width`, the items under the bracket."""
    line = prefix + value + tail
    if len(line) <= width or not value.startswith("["):
        return line + "\n"
    items, depth, quote, start = [], 0, None, 1
    for i, c in enumerate(value):                       # split the array at its top-level commas
        if quote:
            if c == quote and (quote == "'" or value[i - 1] != "\\"):
                quote = None
        elif c in "\"'":
            quote = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        elif c == "," and depth == 1:
            items.append(value[start:i].strip())
            start = i + 1
    items.append(value[start:-1].strip())
    pad = " " * (len(prefix) + 1)
    lines, current = [], prefix + "["
    for n, item in enumerate(items):
        piece = item + ("," if n < len(items) - 1 else "]")
        if current.strip() not in ("", prefix.strip() + "[") and len(current) + len(piece) + 1 > width:
            lines.append(current.rstrip())
            current = pad
        current += (piece if current.endswith("[") or current == pad else " " + piece)
    lines.append(current + tail)
    return "\n".join(lines) + "\n"


def card_text(text: str, folder) -> str:
    """A base card without the lines for keys the runner sets (the folder's [card] owned)."""
    owned = {tools._normal(k) for k in folder.get("card", "owned", [])}
    if not owned or folder.get("card", "style", "append") != "append":
        return text
    parse = tools.card_parser(folder)
    kept = [line for line in text.splitlines(keepends=True)
            if not ((parsed := parse(line.rstrip("\n"))) and parsed[0] in owned)]
    return "".join(kept)


def plan(names: list[str]) -> dict[Path, tuple[str, str]]:
    """Every file the configs touch: path → (its text, its migrated text), only those that change."""
    changes: dict[Path, tuple[str, str]] = {}
    for name in names:
        text = config_file(name).read_text(encoding="utf-8")
        first = figure_text(text)
        run = configmod.load(name, strict=False, text=first)
        new = toml_text(first, run, run.project)
        if new != text:
            changes[run.path] = (text, new)
        cards: dict[Path, object] = {}
        for tool in run.tools.values():                    # each base card, by its folder's rules (no planning)
            folder = tools.folders().get(tool.tool)
            for base in tool.baseconfig if folder is not None else ():
                try:
                    path = resolve(base, "baseconfig", project=run.project, where=f"[tools.{tool.tag}].baseconfig")
                except HepError:
                    continue
                if path.is_file():
                    cards.setdefault(path, folder)
        for base, folder in cards.items():
            text = base.read_text(encoding="utf-8")
            new = card_text(text, folder)
            if new != text:
                changes.setdefault(base, (text, new))
    return changes


def diff(path: Path, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        fromfile=str(path), tofile=str(path) + " (migrated)"))


def apply(changes: dict[Path, tuple[str, str]]) -> None:
    for path, (_, new) in changes.items():
        path.write_text(new, encoding="utf-8")
