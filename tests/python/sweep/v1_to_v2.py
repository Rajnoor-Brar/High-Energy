"""Minimal schema-1 → schema-2 translation, for the golden comparison only (P1-S03).

`hep config migrate` (P1-S06) is the real thing: it writes files, renames the misleading PDF tags, keeps
an alias map and reports what it changed. This helper exists so that P1-S03 can run the **new** sweep
engine on the **frozen legacy inputs** and compare point sets, pages and legends against the fixtures
captured in P0-S04. It translates in memory, covers only what those two configs use, and is deliberately
strict: anything it does not understand raises, rather than being silently dropped.

Mapping (03 §6):

| schema 1 | schema 2 |
|---|---|
| `[analysis] cmnd_file/event_count/seed` | `[generator].card`, `[run].events`, `[run].seed` |
| `[rivpyth] threads/plugin_dir/yoda_file` | `[run].threads`, `[rivet].paths`, `[run].name` (stem) |
| `[rivpyth] serial/generator/hepmc_file/path_literal` | dropped |
| `[yoda] plot_merge_type/use_data/data_*` | `[plot].merge`, `[plot.data].*` |
| `[sweep] tag_style/yoda_legends/skip_existing/seed_step` | `[output].tag_style`, `[plot].legends`, `[run].skip_existing`, dropped |
| `[settle.rivet] plugin/options` | `[rivet].analyses`, `[rivet].options` |
| `[settle.cmnd] beams/seed/"Key:x"` | `[beams].energies`, `[run].seed`, `[settle.gen]` |
| `[sweep.cmnd.<n>] type="pythia"` | `[quantity.<n>] type="setting"`, `setting` → `key` |
| `[sweep.cmnd.<n>] type="beams"` | `[quantity.<n>] type="energies"` (energy pairs, not particles) |
| a `pythia` quantity on `Beams:idA`/`idB` | `[quantity.<n>] type="beams"`, `side="a"`/`"b"` |
| `[sweep.rivet.<n>] type="option"/"plugin"` | `type="option"` / `type="analysis"` |
| quantity key `cmnd.x` / `rivet.x` | bare `x` |
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import tomli_w

#: Beam particles of the PhotoProduction base card (`Beams:idA`, `Beams:idB`), needed because schema 2
#: separates particles from energies and the v1 files carried the particles in the base cmnd.
DEFAULT_IDS = [2212, 11]

SIDE_OF_SETTING = {"beams:ida": "a", "beams:idb": "b"}


def _bare(name: str) -> str:
    """`cmnd.pdf` → `pdf`."""
    return name.split(".", 1)[-1]


def _rename(entries: Any) -> list[Any]:
    out = []
    for entry in entries or []:
        if isinstance(entry, list):
            out.append([_bare(str(name)) for name in entry])
        else:
            out.append("+".join(_bare(part) for part in str(entry).split("+")))
    return out


def _quantity(section: str, name: str, body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    kind = body["type"]
    new: dict[str, Any] = {}
    if section == "cmnd":
        if kind == "pythia":
            setting = body.get("setting", "")
            side = SIDE_OF_SETTING.get(str(setting).lower())
            if side:                      # particles were a Pythia setting; now they are a beams quantity
                new["type"] = "beams"
                new["side"] = side
            else:
                new["type"] = "setting"
                if not setting:
                    raise ValueError(f"[sweep.cmnd.{name}] has no setting; a table-valued quantity "
                                     "needs the real migrate tool")
                new["key"] = setting
        elif kind == "beams":
            new["type"] = "energies"      # v1 "beams" held energies
        elif kind == "seed":
            new["type"] = "seed"
        else:
            raise ValueError(f"[sweep.cmnd.{name}] type {kind!r} is not handled")
    elif section == "rivet":
        if kind == "option":
            new["type"] = "option"
            new["option"] = body["option"]
        elif kind == "plugin":
            new["type"] = "analysis"
        else:
            raise ValueError(f"[sweep.rivet.{name}] type {kind!r} is not handled")
    else:
        raise ValueError(f"unknown quantity section {section!r}")

    for key in ("values", "labels", "tags", "use", "in_legend"):
        if key in body:
            new[key] = body[key]
    return name, new


def translate(path: Path) -> dict[str, Any]:
    """The schema-2 document equivalent to a schema-1 run TOML."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    analysis = raw.get("analysis", {})
    yoda = raw.get("yoda", {})
    rivpyth = raw.get("rivpyth", {})
    sweep = raw.get("sweep", {})
    settle = raw.get("settle", {})

    document: dict[str, Any] = {"schema": 2}
    run: dict[str, Any] = {"name": Path(rivpyth.get("yoda_file", "run.yoda")).stem}
    if analysis.get("event_count"):
        run["events"] = analysis["event_count"]
    if analysis.get("seed"):
        run["seed"] = analysis["seed"]
    if rivpyth.get("threads") is not None:
        run["threads"] = rivpyth["threads"]
    if sweep.get("skip_existing") is not None:
        run["skip_existing"] = sweep["skip_existing"]
    document["run"] = run
    document["generator"] = {"tool": "pythia", "card": analysis["cmnd_file"]}

    beams: dict[str, Any] = {"ids": list(DEFAULT_IDS)}
    settle_cmnd = dict(settle.get("cmnd", {}))
    if "beams" in settle_cmnd:
        beams["energies"] = settle_cmnd.pop("beams")
    document["beams"] = beams
    if "seed" in settle_cmnd:
        document["run"]["seed"] = settle_cmnd.pop("seed")

    rivet: dict[str, Any] = {}
    settle_rivet = settle.get("rivet", {})
    if settle_rivet.get("plugin"):
        rivet["analyses"] = [settle_rivet["plugin"]]
    if settle_rivet.get("options"):
        rivet["options"] = settle_rivet["options"]
    if rivpyth.get("plugin_dir"):
        rivet["paths"] = [rivpyth["plugin_dir"]]
    document["rivet"] = rivet

    plot: dict[str, Any] = {"merge": "yodamerge" if yoda.get("plot_merge_type") == 2 else "overlay"}
    for old, new in (("void_empty", "void_empty"), ("min_entries", "min_entries"),
                     ("auto_range", "auto_range"), ("range_pad", "range_pad"),
                     ("plot_analysis", "analysis")):
        if yoda.get(old) is not None:
            plot[new] = yoda[old]
    if sweep.get("yoda_legends"):
        plot["legends"] = sweep["yoda_legends"]
    data: dict[str, Any] = {}
    if yoda.get("use_data") and yoda.get("data_file"):
        data["file"] = yoda["data_file"]
        for old, new in (("data_legend", "legend"), ("data_hist", "show"), ("data_reference", "reference"),
                         ("rivet_refs", "rivet_refs")):
            if yoda.get(old) is not None:
                data[new] = yoda[old]
    elif yoda.get("rivet_refs"):
        data["rivet_refs"] = yoda["rivet_refs"]
    if data:
        plot["data"] = data
    document["plot"] = plot

    output: dict[str, Any] = {}
    if sweep.get("tag_style"):
        output["tag_style"] = sweep["tag_style"]
    if output:
        document["output"] = output

    new_settle: dict[str, Any] = {}
    if settle_cmnd:
        new_settle["gen"] = settle_cmnd
    if settle.get("use"):
        new_settle["use"] = {_bare(key): value for key, value in settle["use"].items()}
    if settle.get("tag"):
        new_settle["tag"] = settle["tag"]
    if new_settle:
        document["settle"] = new_settle

    quantities: dict[str, Any] = {}
    for section in ("cmnd", "rivet"):
        for name, body in sweep.get(section, {}).items():
            key, translated = _quantity(section, name, body)
            quantities[key] = translated
    if quantities:
        document["quantity"] = quantities

    new_sweep: dict[str, Any] = {}
    if sweep.get("across"):
        new_sweep["across"] = _rename(sweep["across"])
    if sweep.get("overlay"):
        new_sweep["overlay"] = _bare(sweep["overlay"])
    if sweep.get("style"):
        new_sweep["style"] = sweep["style"]
    if sweep.get("only"):
        new_sweep["only"] = sweep["only"]
    document["sweep"] = new_sweep

    studies: dict[str, Any] = {}
    for name, body in raw.get("study", {}).items():
        study: dict[str, Any] = {}
        if body.get("description"):
            study["description"] = body["description"]
        study["across"] = _rename(body.get("across", []))
        if body.get("overlay"):
            study["overlay"] = _bare(body["overlay"])
        if body.get("style"):
            study["style"] = body["style"]
        if body.get("pin"):
            study["pin"] = {_bare(key): value for key, value in body["pin"].items()}
        studies[name] = study
    if studies:
        document["study"] = studies
    return document


def write_v2(path: Path, destination: Path) -> Path:
    """Translate `path` and write it next to the test's other files."""
    destination.write_text(tomli_w.dumps(translate(path)), encoding="utf-8")
    return destination
