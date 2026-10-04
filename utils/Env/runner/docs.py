"""The manual's generated parts (rank 5, V91): what the code states, the manual does not restate by hand.

A page of docs/ holds blocks

    <!-- generated: keys plot -->
    …
    <!-- /generated -->

and `make docs` rewrites what is between from the code; tests/runner/test_docs.py fails while a block
differs ("run `make docs`"). What a block may name:

* `keys <table>`: a schema table's keys (utils/Env/schema/run.toml: type, choices, bounds, default,
  inheritance, doc and notes, V90); `keys figure` lists a figure's own keys, then the [plot] keys it
  inherits;
* `style`: utils/Apps/Paint/base.toml's keys, their defaults and their comments;
* `commands`: `hep`'s subcommands and their options, from cli.parser()'s help.
"""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path

from . import cli, schema
from .paths import repo_root

BLOCK = re.compile(r"(<!-- generated: ([^>]+?) -->\n)(.*?)(<!-- /generated -->)", re.S)


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _value(value) -> str:
    """A value as the TOML that writes it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    return str(value)


def _type(entry: dict) -> str:
    out = schema.type_name(entry["type"])
    if entry.get("items"):
        out += f" ({schema.type_name(entry['items'])} each)"
    if entry.get("choices"):
        out += ": " + ", ".join(f"`{_value(c)}`" for c in entry["choices"])
    if "min" in entry:
        out += f", ≥ {entry['min']}"
    if entry.get("default_ok"):
        out += ', or `"default"`'
    return out


def keys(table: str) -> str:
    """A schema table as the reference's table: Key | Type | Default | Meaning."""
    entries = schema.spec().get(table, {}) if table == "figure" else schema.keys(table)
    rows = ["| Key | Type | Default | Meaning |", "|---|---|---|---|"]
    for name, entry in entries.items():
        default = "**required**" if entry.get("required") else f"`{_value(entry['default'])}`" if "default" in entry else ""
        meaning = entry.get("notes") or entry.get("doc", "")
        if entry.get("inherit"):
            meaning += " A configuration inherits it from `[run]`."
        rows.append(f"| `{name}` | {_cell(_type(entry))} | {default} | {_cell(meaning)} |")
    if table == "figure":
        inherited = [k for k, e in schema.spec().get("plot", {}).items() if e.get("page")]
        rows.append(f"| *every page key of `[plot]`* | as there | `[plot]`'s | {', '.join(f'`{k}`' for k in inherited)}: "
                    "the figure's value, for its pages only |")
    return "\n".join(rows)


def _style_entries() -> list[tuple[str, str, str]]:
    """base.toml's keys in file order: (dotted key, default as written, comment). A comment-only line
    under a key, indented to its comment, continues that key's comment; a key without one has its
    table's (`[page.margins]   # fractions of the page`)."""
    path = repo_root() / "utils" / "Apps" / "Paint" / "base.toml"
    text = path.read_text(encoding="utf-8")
    values = tomllib.loads(text)
    out: list[list[str]] = []
    table, column, about = "", None, ""
    for line in text.splitlines():
        if (head := re.match(r"\[([\w.]+)\]", line)):
            table, column = head.group(1), None
            about = found.group(1).strip() if (found := re.search(r"\s#\s?(.*)$", line)) else ""
            continue
        if (key := re.match(r"(\w+)\s*=", line)):
            name = f"{table}.{key.group(1)}" if table else key.group(1)
            comment = about
            if (found := re.search(r"\s#\s?(.*)$", line)):
                comment, column = found.group(1).strip(), found.start() + 1
            value = values
            for part in name.split("."):
                value = value[part]
            out.append([name, _value(value), comment])
            continue
        if out and column is not None and line.strip().startswith("#") and line.index("#") == column:
            out[-1][2] += " " + line.strip()[1:].strip()
        else:
            column = None
    return [tuple(e) for e in out]


def style() -> str:
    rows = ["| Key | Default | Means |", "|---|---|---|"]
    rows += [f"| `{name}` | `{_cell(value)}` | {_cell(comment)} |" for name, value, comment in _style_entries()]
    return "\n".join(rows)


def _option(action: argparse.Action) -> str:
    if action.option_strings:
        name = ", ".join(action.option_strings)
        if action.nargs != 0:
            name += f" {action.metavar or ('|'.join(map(str, action.choices)) if action.choices else action.dest.upper())}"
            name += "…" if action.nargs in ("+", "*") else ""
        return name
    shown = action.metavar or action.dest
    return f"{shown}…" if action.nargs in ("+", "*") else f"[{shown}]" if action.nargs == "?" else shown


def commands() -> str:
    """Each subcommand: its help, then a table of its arguments."""
    top = cli.parser()
    sub = next(a for a in top._actions if isinstance(a, argparse._SubParsersAction))
    helps = {a.dest: a.help for a in sub._choices_actions}
    out = []
    for name, parser in sub.choices.items():
        out.append(f"**`hep {name}`**: {helps.get(name, '')}\n")
        rows = ["| Argument | Meaning |", "|---|---|"]
        for action in parser._actions:
            if isinstance(action, argparse._HelpAction):
                continue
            meaning = action.help or ""
            rows.append(f"| `{_cell(_option(action))}` | {_cell(meaning)} |")
        out.append("\n".join(rows) + "\n")
    return "\n".join(out).rstrip("\n")


def render(what: str) -> str:
    kind, _, arg = what.strip().partition(" ")
    if kind == "keys" and arg in schema.TABLES:
        return keys(arg)
    if kind == "style" and not arg:
        return style()
    if kind == "commands" and not arg:
        return commands()
    raise ValueError(f"no generated block '{what}': keys <{'|'.join(schema.TABLES)}>, style or commands")


def updated(text: str) -> str:
    return BLOCK.sub(lambda m: f"{m.group(1)}{render(m.group(2))}\n{m.group(4)}", text)


def pages() -> list[Path]:
    docs = repo_root() / "docs"
    return sorted(p for p in docs.rglob("*.md") if "audit_" not in str(p.relative_to(docs)))


def stale() -> list[str]:
    """The pages whose generated blocks differ from what the code says now."""
    return [str(p.relative_to(repo_root())) for p in pages()
            if BLOCK.search(text := p.read_text(encoding="utf-8")) and updated(text) != text]


if __name__ == "__main__":                                  # make docs
    for page in pages():
        text = page.read_text(encoding="utf-8")
        if BLOCK.search(text) and (new := updated(text)) != text:
            page.write_text(new, encoding="utf-8")
            print(page.relative_to(repo_root()))
