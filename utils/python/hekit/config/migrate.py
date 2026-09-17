"""Schema 1 → schema 2 (03 §6).

The rework kept the shape of the configuration that worked — a base card plus typed quantities, `across`,
`settle`, studies — and changed the vocabulary around it. This translates a schema-1 file into the new
vocabulary, reports every change it made, and refuses to guess: anything it does not understand is an
error, not a silent omission.

What moves:

| schema 1 | schema 2 |
|---|---|
| `[analysis] cmnd_file / event_count / seed` | `[generator].card`, `[run].events`, `[run].seed` |
| `[rivpyth] threads / plugin_dir / yoda_file` | `[run].threads`, `[rivet].paths`, `[run].name` (the stem) |
| `[rivpyth] serial / generator / hepmc_file / path_literal` | dropped (07 §1: directories, not serial prefixes) |
| `[yoda] plot_merge_type / void_empty / …` | `[plot]`, `[plot.data]` |
| `[sweep] tag_style / yoda_legends / skip_existing / seed_step` | `[output].tag_style`, `[plot].legends`, `[run].skip_existing`, dropped (identity seeds, D21) |
| `[settle.rivet] plugin / options` | `[rivet].analyses` / `[rivet].options` |
| `[settle.cmnd] beams / seed / "Key:x"` | `[beams].energies`, `[run].seed`, `[settle.gen]` |
| `[sweep.cmnd.<n>] type = "pythia"` | `[quantity.<n>] type = "setting"`, `setting` → `key` |
| `[sweep.cmnd.<n>] type = "beams"` | `[quantity.energies] type = "energies"` — v1 "beams" held energies |
| a `pythia` quantity on `Beams:idA` / `idB` | `[quantity.beams] type = "beams"`, `side = "a"` / `"b"` |
| `[sweep.rivet.<n>] type = "option"` / `"plugin"` | `type = "option"` / `type = "analysis"` |
| `cmnd.x` / `rivet.x` in `across`, `overlay`, `pin`, `[settle.use]` | the bare name |
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any

import tomli_w

from ..errors import HepError

#: v1 quantity name → v2 name, so that a type and its name agree (03 §3).
QUANTITY_RENAMES = {"beams": "energies", "lepton": "beams"}

#: 00/B12: the PDF tags read like perturbative orders but name PDF sets. The migration renames them and
#: records the old name, so old result names can still be traced.
TAG_RENAMES = {
    "PDF:pSet": {"MSTW": "MSTW08lo", "NNLO": "NNPDF23lo", "NNNLO": "NNPDF23nlo", "LHC21": "PDF4LHC21"},
}

#: Which beam a `Beams:idA`/`idB` setting varies.
SIDE_OF_SETTING = {"beams:ida": "a", "beams:idb": "b"}

#: Beam particles that used to live only in the base card (03 §3 separates particles from energies).
DEFAULT_IDS = [2212, 11]

DROPPED = {
    "rivpyth": {"serial": "results are directories now, not serial-prefixed files (07 §1)",
                "generator": "hep-run replaces the per-project generator binary",
                "hepmc_file": "events stream through a private FIFO, or an event store (11)",
                "path_literal": "paths are resolved by hep (00/B18)"},
    "sweep": {"seed_step": "seeds come from a point's identity now (03 §5, D21)"},
}


@dataclass
class Migration:
    """The result of a migration: the new document and everything that changed."""

    document: dict[str, Any] = dataclass_field(default_factory=dict)
    notes: list[str] = dataclass_field(default_factory=list)
    #: old tag → new tag, per quantity, for tracing old result names (00/B12)
    aliases: dict[str, dict[str, str]] = dataclass_field(default_factory=dict)

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)


def bare(name: str) -> str:
    """`cmnd.pdf` → `pdf`, then any rename."""
    short = str(name).split(".", 1)[-1]
    return QUANTITY_RENAMES.get(short, short)


def _rename_across(entries: Any) -> list[Any]:
    renamed = []
    for entry in entries or []:
        if isinstance(entry, list):
            renamed.append([bare(name) for name in entry])
        else:
            renamed.append("+".join(bare(part) for part in str(entry).split("+")))
    return renamed


def _selector(value: Any) -> Any:
    """A v1 pin: a tag stays a tag; an integer was an index and becomes `#N` (D-B22)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return value
    return f"#{value}"


def _quantity(section: str, name: str, body: dict[str, Any], migration: Migration,
              *, rename_tags: bool) -> tuple[str, dict[str, Any]]:
    kind = body.get("type")
    new: dict[str, Any] = {}
    setting = body.get("setting", "")
    if section == "cmnd":
        if kind == "pythia":
            side = SIDE_OF_SETTING.get(str(setting).lower())
            if side:
                new["type"] = "beams"
                new["side"] = side
                migration.note(f"[sweep.cmnd.{name}] set {setting}; it is now a beams quantity "
                               f"with side = \"{side}\" (03 §3)")
            elif setting:
                new["type"] = "setting"
                new["key"] = setting
            else:
                raise HepError(f"[sweep.cmnd.{name}] has no 'setting'",
                               hint="a table-valued quantity has to be split by hand into one "
                                    "quantity per setting, or given a key")
        elif kind == "beams":
            new["type"] = "energies"
            migration.note(f"[sweep.cmnd.{name}] held energies; it becomes type = \"energies\" "
                           f"named '{bare(name)}' (03 §3)")
        elif kind == "seed":
            new["type"] = "seed"
            migration.note(f"[sweep.cmnd.{name}] is a seed quantity: its values now select a replica, "
                           "and the seed itself comes from the point identity (03 §5)")
        else:
            raise HepError(f"[sweep.cmnd.{name}] has an unknown type {kind!r}")
    elif section == "rivet":
        if kind == "option":
            new["type"] = "option"
            new["option"] = body["option"]
        elif kind == "plugin":
            new["type"] = "analysis"
        else:
            raise HepError(f"[sweep.rivet.{name}] has an unknown type {kind!r}")
    else:
        raise HepError(f"unknown quantity section [sweep.{section}]")

    for key in ("values", "labels", "use", "in_legend", "note"):
        if key in body:
            new[key] = body[key]

    tags = list(body.get("tags", []))
    if rename_tags and setting in TAG_RENAMES:
        table = TAG_RENAMES[setting]
        renamed = [table.get(tag, tag) for tag in tags]
        changed = {old: fresh for old, fresh in zip(tags, renamed) if old != fresh}
        if changed:
            migration.aliases[bare(name)] = changed
            migration.note(f"[quantity.{bare(name)}] tags renamed (00/B12): "
                           + ", ".join(f"{old} → {fresh}" for old, fresh in changed.items()))
            new["note"] = (body.get("note", "") + " " if body.get("note") else "") + \
                "tags renamed in the schema-2 migration: " + \
                ", ".join(f"{old} was {fresh}" for fresh, old in changed.items())
        tags = renamed
    if tags:
        new["tags"] = tags
    return bare(name), new


def _declared_options(document: dict[str, Any], config_dir: Path) -> set[str] | None:
    """Options the configured analysis declares, or None when its `.info` cannot be read (00/B14)."""
    from ..adapters import rivet

    analyses = document.get("rivet", {}).get("analyses", [])
    if not analyses:
        return None
    search = tuple(Path(entry) if Path(entry).is_absolute() else config_dir / entry
                   for entry in document.get("rivet", {}).get("paths", []))
    info = rivet.read_info(analyses[0].split(":")[0], search)
    return info.options if info.found else None


def migrate_document(raw: dict[str, Any], *, rename_tags: bool = True,
                     drop_undeclared_options: bool = True, config_dir: Path | None = None) -> Migration:
    """Translate a parsed schema-1 document."""
    migration = Migration()
    analysis = raw.get("analysis", {})
    yoda = raw.get("yoda", {})
    rivpyth = raw.get("rivpyth", {})
    sweep = raw.get("sweep", {})
    settle = raw.get("settle", {})
    if "schema" in raw:
        raise HepError("this file already declares a schema version", hint="nothing to migrate")
    if not analysis:
        raise HepError("this does not look like a schema-1 run file", hint="[analysis] is missing")

    for section, keys in DROPPED.items():
        for key, why in keys.items():
            if key in raw.get(section, {}):
                migration.note(f"[{section}].{key} dropped: {why}")

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
    if not analysis.get("cmnd_file"):
        raise HepError("[analysis].cmnd_file is missing", hint="every generator needs its native card")
    document["generator"] = {"tool": "pythia", "card": analysis["cmnd_file"]}

    beams: dict[str, Any] = {"ids": list(DEFAULT_IDS)}
    settle_cmnd = dict(settle.get("cmnd", {}))
    if "beams" in settle_cmnd:
        beams["energies"] = settle_cmnd.pop("beams")
        migration.note("[settle.cmnd].beams held energies; it becomes [beams].energies")
    document["beams"] = beams
    migration.note(f"[beams].ids = {DEFAULT_IDS} was implicit in the base card; schema 2 states it "
                   "(check it against your card)")
    if "seed" in settle_cmnd:
        document["run"]["seed"] = settle_cmnd.pop("seed")

    rivet_section: dict[str, Any] = {}
    settle_rivet = settle.get("rivet", {})
    if settle_rivet.get("plugin"):
        rivet_section["analyses"] = [settle_rivet["plugin"]]
    if settle_rivet.get("options"):
        rivet_section["options"] = settle_rivet["options"]
    if rivpyth.get("plugin_dir"):
        rivet_section["paths"] = [rivpyth["plugin_dir"]]
    document["rivet"] = rivet_section

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
        for old, new in (("data_legend", "legend"), ("data_hist", "show"),
                         ("data_reference", "reference")):
            if yoda.get(old) is not None:
                data[new] = yoda[old]
        migration.note("[plot.data].map is empty: schema 2 overlays reference data only where you map "
                       "it explicitly, because matching by histogram name overlaid unrelated "
                       "observables (00/B5)")
        data["map"] = {}
    if yoda.get("rivet_refs"):
        data["rivet_refs"] = yoda["rivet_refs"]
    if data:
        plot["data"] = data
    document["plot"] = plot

    if sweep.get("tag_style"):
        document["output"] = {"tag_style": sweep["tag_style"]}

    new_settle: dict[str, Any] = {}
    if settle_cmnd:
        new_settle["gen"] = settle_cmnd
    if settle.get("use"):
        new_settle["use"] = {bare(key): _selector(value) for key, value in settle["use"].items()}
    if settle.get("tag"):
        new_settle["tag"] = settle["tag"]
    if new_settle:
        document["settle"] = new_settle

    quantities: dict[str, Any] = {}
    for section in ("cmnd", "rivet"):
        for name, body in sweep.get(section, {}).items():
            key, translated = _quantity(section, name, body, migration, rename_tags=rename_tags)
            quantities[key] = translated

    if drop_undeclared_options:
        declared = _declared_options(document, config_dir or Path.cwd())
        if declared is not None:
            for name in [key for key, body in quantities.items()
                         if body["type"] == "option" and body.get("option") not in declared]:
                option = quantities.pop(name)["option"]
                migration.note(f"[quantity.{name}] dropped: analysis "
                               f"'{document['rivet']['analyses'][0]}' does not declare "
                               f"'{option}' (00/B14)")
    if quantities:
        document["quantity"] = quantities

    new_sweep: dict[str, Any] = {}
    if sweep.get("across"):
        new_sweep["across"] = _rename_across(sweep["across"])
    if sweep.get("overlay"):
        new_sweep["overlay"] = bare(sweep["overlay"])
    if sweep.get("style"):
        new_sweep["style"] = sweep["style"]
    if sweep.get("only"):
        new_sweep["only"] = sweep["only"]
    document["sweep"] = _without_missing_quantities(new_sweep, quantities, migration, "[sweep]")

    studies: dict[str, Any] = {}
    for name, body in raw.get("study", {}).items():
        study: dict[str, Any] = {}
        if body.get("description"):
            study["description"] = body["description"]
        study["across"] = _rename_across(body.get("across", []))
        if body.get("overlay"):
            study["overlay"] = bare(body["overlay"])
        if body.get("style"):
            study["style"] = body["style"]
        if body.get("pin"):
            study["pin"] = {bare(key): _selector(value) for key, value in body["pin"].items()}
        studies[name] = _without_missing_quantities(study, quantities, migration, f"[study.{name}]")
    if studies:
        document["study"] = studies

    migration.document = document
    return migration


def _without_missing_quantities(section: dict[str, Any], quantities: dict[str, Any],
                                migration: Migration, label: str) -> dict[str, Any]:
    """Drop references to quantities the migration removed (00/B14), and say so."""
    if "across" in section:
        kept = []
        for entry in section["across"]:
            names = entry if isinstance(entry, list) else str(entry).split("+")
            missing = [name for name in names if name not in quantities]
            if missing:
                migration.note(f"{label} no longer scans {', '.join(missing)}: the quantity was dropped")
                continue
            kept.append(entry)
        section["across"] = kept
    if section.get("overlay") and section["overlay"] not in quantities:
        migration.note(f"{label} overlay '{section['overlay']}' dropped with its quantity")
        section.pop("overlay")
    if "pin" in section:
        section["pin"] = {name: value for name, value in section["pin"].items() if name in quantities}
    return section


HEADER = """\
# {name} — migrated from {source} by `hep config migrate` (schema 1 → 2).
#
# Review it before use: the migration reports what it changed, and the notes below are that report.
{notes}
"""


def dumps(migration: Migration, *, name: str, source: str) -> str:
    """The migrated document as TOML, with the migration report as its header."""
    notes = "\n".join(f"#   - {note}" for note in migration.notes)
    header = HEADER.format(name=name, source=source, notes=notes or "#   (nothing needed changing)")
    return header + "\n" + to_toml(migration.document)


def migrate_file(path: Path, **kwargs: Any) -> Migration:
    """Read a schema-1 file and migrate it."""
    try:
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HepError(f"configuration file not found: {path}") from None
    except tomllib.TOMLDecodeError as error:
        raise HepError(f"invalid TOML: {error}", where=str(path)) from None
    kwargs.setdefault("config_dir", Path(path).resolve().parent)
    return migrate_document(raw, **kwargs)


# ── emitting readable TOML ───────────────────────────────────────────────────
# tomli_w puts every array element on its own line, which turns a four-value quantity into twenty lines.
# These configs are read and edited by hand, so short arrays stay inline. Escaping is still tomli_w's
# job: each scalar is formatted by asking it to dump a one-key document.

LINE_WIDTH = 96


def format_scalar(value: Any) -> str:
    return tomli_w.dumps({"v": value}).strip()[4:]


def format_value(value: Any, used: int = 0) -> str:
    """A value as TOML: inline when it fits on a line, one element per line when it does not.

    `used` is how much of the line the key has already taken, so the decision is about the whole line.
    """
    if not isinstance(value, list):
        return format_scalar(value)
    if not value:
        return "[]"
    parts = [format_value(item) for item in value]
    inline = "[" + ", ".join(parts) + "]"
    if used + len(inline) <= LINE_WIDTH and "\n" not in inline:
        return inline
    return "[\n" + "".join(f"    {part},\n" for part in parts) + "]"


def _is_table(value: Any) -> bool:
    return isinstance(value, dict)


def emit(document: dict[str, Any], prefix: str = "", *, header: str = "") -> list[str]:
    """The document as TOML lines: scalars first, then nested tables, in insertion order.

    A table that holds nothing but other tables gets no header of its own — `[quantity]` above
    `[quantity.pdf]` is noise.
    """
    lines: list[str] = []
    scalars = {key: value for key, value in document.items() if not _is_table(value)}
    tables = {key: value for key, value in document.items() if _is_table(value)}
    if header and (scalars or not tables):
        lines += ["", f"[{header}]"]
    for key, value in scalars.items():
        if isinstance(value, list) and value and all(_is_table(item) for item in value):
            for item in value:                       # an array of tables
                lines += ["", f"[[{prefix}{key}]]"] + emit(item, "")
            continue
        rendered = quote_key(key)
        lines.append(f"{rendered} = {format_value(value, len(rendered) + 3)}")
    for key, value in tables.items():
        name = f"{prefix}{quote_key(key)}"
        lines += emit(value, f"{name}.", header=name)
    return lines


def quote_key(key: str) -> str:
    """Bare where possible, quoted where the key holds a colon or a space (`"PhaseSpace:pTHatMin"`)."""
    return key if key.replace("_", "").replace("-", "").isalnum() else f'"{key}"'


def to_toml(document: dict[str, Any]) -> str:
    text = "\n".join(emit(document)).strip("\n")
    return text + "\n"
