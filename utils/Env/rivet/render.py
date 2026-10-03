"""utils/Env/rivet/render.py — Rivet's analyses and their options (docs/05_Tools_Reference.md §3, V60).

The runner core knows no tool (BOT.md); what is Rivet's lives here, as the folder's `options` hook:

* each analysis rendered with its options, in increasing precedence (V54): the table's `options` (every
  analysis), the analysis's own inline `NAME:OPT=V`, then the quantities that target it;
* every option declared in the analysis's `.info` (C9, L19): Rivet ignores an undeclared option
  silently, so the curves would be identical;
* `{analyses}` for the argv (`-a <analysis[:options]>` each), the analyses for the identity and for the
  standard configuration `rivet_analyses`, and the names the identity's `[identity] files` expand;
* the page texts `{opt:NAME}` and `{opt:<analysis>:NAME}` (V66): each option's value at the point, the
  `.info`'s "(default X)" where the run sets none. `{opt:NAME}` exists when every analysis that has the
  option has it at the same value.
"""

from __future__ import annotations

import re
from pathlib import Path

from runner.errors import HepError


def options(extra: dict, targeted: dict, context: dict) -> dict:
    """`extra`: the table's tool-specific keys; `targeted`: analysis → {option: value} from quantities;
    `context`: tag, bools, native (the runner's value writer), info_dirs."""
    native, bools, tag = context["native"], context["bools"], context["tag"]
    common = {k: native(v, bools) for k, v in extra.get("options", {}).items()}
    rendered = []
    for analysis in extra["analyses"]:
        base, *inline = analysis.split(":")
        merged = dict(common)                                  # the table's, for every analysis …
        merged.update(item.partition("=")[::2] for item in inline)   # … the analysis's own, written inline …
        merged.update(targeted.get(base, {}))                  # … and the point's quantities, most specific last
        rendered.append(":".join([base, *(f"{k}={v}" for k, v in sorted(merged.items()))]))
    unknown = set(targeted) - {a.split(":")[0] for a in extra["analyses"]}
    if unknown:
        raise HepError(f"options target analyses not run by {tag}: {', '.join(sorted(unknown))}", where=f"[tools.{tag}]")
    defaults = declared_options(rendered, context["info_dirs"], tag)
    return {
        "texts": texts(rendered, defaults),
        "identity": {"analyses": rendered},
        "config_data": {"analyses": rendered},
        "placeholders": {"analyses": [x for a in rendered for x in ("-a", a)]},
        "identity_values": {"analysis": [a.split(":")[0] for a in rendered]},
    }


def texts(rendered: list[str], defaults: dict[str, dict[str, str]]) -> dict[str, str]:
    """{opt:<analysis>:NAME} for every option an analysis has (given, else its .info default), and
    {opt:NAME} where the analyses that have NAME agree on it (V66)."""
    out: dict[str, str] = {}
    seen: dict[str, set[str]] = {}
    for analysis in rendered:
        name, *given = analysis.split(":")
        values = dict(defaults.get(name, {}))
        values.update(item.partition("=")[::2] for item in given)
        for option, value in values.items():
            out[f"opt:{name}:{option}"] = value
            seen.setdefault(option, set()).add(value)
    out.update({f"opt:{option}": next(iter(v)) for option, v in seen.items() if len(v) == 1})
    return out


def declared_options(rendered: list[str], dirs: list[Path], tag: str) -> dict[str, dict[str, str]]:
    """C9 (L19): each analysis has a .info, and every option it is given is declared there. Returns
    each analysis's documented defaults, an option's "(default X)" comment."""
    defaults: dict[str, dict[str, str]] = {}
    if not dirs:
        return defaults
    for analysis in rendered:
        name, *given = analysis.split(":")
        info = next((d / f"{name}.info" for d in dirs if (d / f"{name}.info").is_file()), None)
        if info is None:
            raise HepError(f"no analysis '{name}' (no {name}.info)", where=f"[tools.{tag}].analyses",
                           hint=f"searched {', '.join(str(d) for d in dirs)}; a project plugin needs `hep build`")
        declared, inside = set(), False
        for raw in info.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"^Options:", raw):
                inside = True
                continue
            if inside:
                match = re.match(r"^\s*-\s*([A-Za-z0-9_]+)=", raw)
                if match:
                    declared.add(match.group(1))
                    default = re.search(r"\(default ([^,()\s]+)", raw)
                    if default:
                        defaults.setdefault(name, {})[match.group(1)] = default.group(1)
                elif raw.strip() and not raw.startswith((" ", "\t", "-")):
                    break
        for option in given:
            key = option.split("=")[0]
            if key not in declared:
                raise HepError(f"'{name}' does not declare the option {key}", where=f"[tools.{tag}]",
                               hint=(f"declared: {', '.join(sorted(declared)) or 'none'} (in {info}). Rivet ignores "
                                     "an undeclared option silently, so the curves would be identical (L19)"))
    return defaults
