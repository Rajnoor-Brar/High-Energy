"""Schema 2: every section of a run TOML, as field tables (03 §1).

The section dataclasses are generated from the field tables, so defaults, types and documentation have
one home. Nothing here reads files; `load.py` layers the values and builds the objects.
"""

from __future__ import annotations

from dataclasses import field as dataclass_field, make_dataclass
from typing import Any

from .fields import Field, Section

SCHEMA_VERSION = 2

# ── run control ──────────────────────────────────────────────────────────────

RUN = Section("run", doc="Run control: how much, how parallel, where to.", machine_keys=("threads",), fields={
    "name": Field("str", "", "output stem; also the prefix of every point name"),
    "events": Field("int", 0, "events to generate per point; 0 = whatever the native card says", minimum=0),
    "seed": Field("int", 0, "base of the identity seed policy (03 §5); never offset by sweep position",
                  minimum=0, maximum=900_000_000),
    "threads": Field("int", 0, "worker threads; 0 = all cores, resolved by hep", minimum=0, maximum=4096),
    "skip_existing": Field("bool", False, "skip a point whose name, hash and complete output all match"),
    "label": Field("str", "", "free text kept in manifests; never used in a path"),
})

GENERATOR = Section("generator", doc="Which generator, and its native card.", fields={
    "tool": Field("str", "pythia", "generator to run",
                  choices=("pythia", "sherpa", "herwig", "whizard", "madgraph", "store")),
    "card": Field("str", "", "native base card, relative to this file"),
    "shower": Field("str", "", "madgraph only: Pythia card used to shower the LHE events"),
    "input": Field("str", "", "store only: point name, 'sha256:…', or a path to an events/ directory"),
})

BEAMS = Section("beams", doc="Beam particles and energies; each adapter renders them (04).", fields={
    "ids": Field("list", [], "PDG ids [A, B], in the generator's beam order", item="int",
                 minimum=2, maximum=2),
    "energies": Field("any", None, "either [E_A, E_B] in GeV (lab frame) or a scalar √s (CM frame)"),
})

# ── sinks ────────────────────────────────────────────────────────────────────

RIVET = Section("rivet", doc="In-process Rivet analyses.", fields={
    "analyses": Field("list", [], "analysis names, optionally with ':OPT=VALUE'", item="str"),
    "options": Field("table", {}, "options applied to every project analysis that declares them",
                     free=True, value_kind="scalar"),
    "paths": Field("list", [], "plugin search path, added to RIVET_ANALYSIS_PATH for children", item="str"),
    "mode": Field("str", "inprocess", "inprocess, or native where the generator runs Rivet itself",
                  choices=("inprocess", "native")),
    "check_beams": Field("bool", True, "let Rivet reject events whose beams do not match the analysis"),
    "weights": Field("str", "nominal", "nominal weight only, or all weights into a multi-weight YODA",
                     choices=("nominal", "all")),
    "xsec": Field("any", "generator", "'generator', or a cross-section in pb"),
    "dump_every": Field("int", 0, "periodic finalize into a partial YODA; 0 = off (re-entrant analyses only)",
                        minimum=0),
})

STORE = Section("store", doc="Optional HepMC3 event store (11).", fields={
    "enabled": Field("bool", False, "write events as a sharded HepMC3 store"),
    "compression": Field("str", "gz", "shard compression", choices=("gz", "zst", "none")),
})

MODULE_SINK = Section("sinks.module", shape="array", doc="User C++ modules booking YODA objects (05 §5).",
                      fields={
    "name": Field("str", "", "registered module name, found in modules/<project>/", required=True),
    "options": Field("table", {}, "options passed to the module's configure()", free=True, value_kind="scalar"),
})

DELPHES = Section("delphes", doc="Detector simulation as an external stage.", fields={
    "card": Field("str", "", "Delphes .tcl card"),
})

# ── outputs and presentation ─────────────────────────────────────────────────

OUTPUT = Section("output", doc="Where results go and how points are named.", fields={
    "root": Field("str", "results/{project}", "results root; {project} is substituted"),
    "tag_style": Field("str", "tag", "how a point name is built from a quantity",
                       choices=("tag", "value", "index")),
})

PLOT_DATA = Section("plot.data", doc="Reference data overlaid on the curves.", fields={
    "file": Field("str", "", "YODA file holding the reference"),
    "legend": Field("str", "Data", "legend entry for the reference"),
    "show": Field("bool", True, "draw the reference in the main panel"),
    "reference": Field("bool", True, "use the reference as the ratio denominator"),
    "rivet_refs": Field("bool", False, "let rivet-mkhtml load Rivet's own reference data"),
    "map": Field("table", {}, "histogram name → reference object path; explicit, never matched by name (00/B5)",
                 free=True, value_kind="str"),
})

PLOT = Section("plot", doc="Plotting (was [yoda] in schema 1).", fields={
    "backend": Field("str", "mkhtml", "plotting backend", choices=("mkhtml", "mpl")),
    "merge": Field("str", "overlay", "overlay the curves, or yodamerge them (seed-only sweeps)",
                   choices=("overlay", "yodamerge")),
    "void_empty": Field("bool", False, "blank bins that are zero in every curve"),
    "min_entries": Field("int", 0, "blank bins with fewer raw entries than this in any curve; 0 = off",
                         minimum=0),
    "auto_range": Field("bool", False, "clip each x axis to the bins with content"),
    "range_pad": Field("int", 0, "empty bins to keep on each side of an auto range", minimum=0),
    "legends": Field("str", "label", "what a curve legend shows", choices=("label", "tag", "value")),
    "analysis": Field("str", "", "common analysis name when plugins differ; '' = the first one"),
}, subsections={"data": PLOT_DATA})

TERMINAL = Section("terminal", doc="Live view (06).", machine_keys=("dashboard", "log_tail", "stall_after"),
                   fields={
    "dashboard": Field("str", "auto", "live dashboard, plain lines, or automatic",
                       choices=("auto", "live", "plain")),
    "log_tail": Field("int", 6, "log lines to keep on screen", minimum=0, maximum=100),
    "stall_after": Field("duration", "5m", "no progress for this long counts as a stall"),
})

# ── processing (12) ──────────────────────────────────────────────────────────

PROC_FIT = Section("proc.fit", shape="array", doc="Fits run after a study (12).", fields={
    "name": Field("str", "", "name of this fit in fits.json", required=True),
    "target": Field("str", "", "YODA path to fit", required=True),
    "model": Field("str", "", "model expression, e.g. 'gauss + poly2'", required=True),
    "range": Field("list", [], "fit range [low, high]", item="number", minimum=2, maximum=2),
    "init": Field("table", {}, "initial parameter values", free=True, value_kind="number"),
    "backend": Field("str", "auto", "fitting backend", choices=("auto", "minuit2", "roofit", "scipy")),
})

PROC_HIST = Section("proc.hist", shape="array", doc="Histograms derived with RDataFrame or uproot (12).",
                    fields={
    "name": Field("str", "", "name of the resulting YODA object", required=True),
    "source": Field("str", "", "input file, e.g. delphes.root", required=True),
    "tree": Field("str", "Delphes", "tree name"),
    "expression": Field("str", "", "expression to histogram", required=True),
    "selection": Field("str", "", "optional selection expression"),
    "bins": Field("list", [], "[n, low, high]", item="number", minimum=3, maximum=3),
})

# ── sweeps (semantics in P1-S03) ─────────────────────────────────────────────

QUANTITY = Section("quantity", shape="named", doc="The sweep catalogue (03 §3).", fields={
    "type": Field("str", "", "what the quantity varies", required=True,
                  choices=("setting", "beams", "energies", "seed", "card", "generator", "events",
                           "analysis", "option")),
    "key": Field("any", None, "setting name; a table {tool = key} when the generator is swept"),
    "side": Field("str", "", "beams only: vary just this beam", choices=("a", "b")),
    "target": Field("str", "", "option only: the analysis the option belongs to"),
    "option": Field("str", "", "option only: the option name as the analysis declares it"),
    "values": Field("list", [], "the values to scan", minimum=1, required=True),
    "labels": Field("list", [], "legend text per value", item="str"),
    "tags": Field("list", [], "filename-safe tag per value", item="str"),
    "use": Field("int", 0, "1-based value applied when the quantity is not scanned; 0 = leave the card alone",
                 minimum=0),
    "in_legend": Field("bool", True, "show this quantity in legends"),
    "note": Field("str", "", "free comment kept in the reference"),
})

SWEEP = Section("sweep", doc="Which quantities vary (03 §4).", fields={
    "across": Field("list", [], "quantity groups; '+' couples, separate entries form a grid"),
    "overlay": Field("str", "", "quantity whose group is drawn as curves; the rest become pages"),
    "style": Field("str", "", "flat across list: one coupled group or one group each",
                   choices=("together", "grid")),
    "only": Field("int", 0, "run only this 1-based point; 0 = all", minimum=0),
})

SETTLE = Section("settle", doc="Values held fixed (03 §4).", fields={
    "tag": Field("str", "", "tag appended to every point name"),
    "use": Field("table", {}, "quantity → 1-based index or tag to pin", free=True, value_kind="scalar"),
    "gen": Field("table", {}, "native generator settings held fixed", free=True, value_kind="scalar"),
    "ana": Field("table", {}, "analysis options held fixed", free=True, value_kind="scalar"),
})

STUDY = Section("study", shape="named", doc="A named scan (03 §4).", free_keys=True, fields={
    "description": Field("str", "", "what the study compares"),
    "across": Field("list", [], "quantity groups for this study"),
    "overlay": Field("str", "", "curve quantity for this study"),
    "style": Field("str", "", "flat across list: coupled or grid", choices=("together", "grid")),
    "pin": Field("table", {}, "quantity → 1-based index or tag", free=True, value_kind="scalar"),
})

# ── machine-only sections ────────────────────────────────────────────────────

PATHS = Section("paths", doc="Machine paths (machine.toml).", machine_keys=("lhapdf",), fields={
    "lhapdf": Field("str", "", "LHAPDF data directory"),
})

TOOLS = Section("tools", shape="named", doc="Where external tools live (machine.toml).",
                machine_keys=("exe",), fields={
    "exe": Field("str", "", "executable for this tool"),
})

#: Top-level keys that are not sections.
TOP_LEVEL = {
    "schema": Field("int", SCHEMA_VERSION, "schema version; 2 is current", choices=(SCHEMA_VERSION,),
                    required=True),
    "extends": Field("list", [], "files layered under this one, left to right", item="str"),
    "project": Field("str", "", "project name; defaults to the parent directory of this file"),
}

#: Every section, in the order the reference lists them.
SECTIONS: dict[str, Section] = {
    section.name: section for section in (
        RUN, GENERATOR, BEAMS, RIVET, STORE, MODULE_SINK, DELPHES, OUTPUT, PLOT, TERMINAL,
        PROC_FIT, PROC_HIST, QUANTITY, SWEEP, SETTLE, STUDY, PATHS, TOOLS,
    )
}

#: Sections a machine file may touch at all (03 §2 allow-list).
MACHINE_SECTIONS = tuple(name for name, section in SECTIONS.items() if section.machine_keys)


def _default_for(spec: Field) -> Any:
    """Lists and tables need a factory; scalars can be plain defaults."""
    if spec.kind in {"list", "table"}:
        return dataclass_field(default_factory=spec.default_value)
    return spec.default_value()


def _class_for(section: Section) -> type:
    """A dataclass mirroring one section's fields."""
    name = "".join(part.capitalize() for part in section.name.replace(".", "_").split("_"))
    return make_dataclass(
        name,
        [(key, Any, _default_for(spec)) for key, spec in section.fields.items()],
        namespace={"__doc__": section.doc, "_section": section,
                   "fields": staticmethod(lambda section=section: section.fields)},
    )


def _all_sections() -> dict[str, Section]:
    """Every section including nested ones ([plot.data]), keyed by name."""
    found: dict[str, Section] = {}
    for section in SECTIONS.values():
        found[section.name] = section
        for subsection in section.subsections.values():
            found[subsection.name] = subsection
    return found


#: Generated dataclasses, one per section (nested sections included).
CLASSES: dict[str, type] = {name: _class_for(section) for name, section in _all_sections().items()}


def section_of(path: tuple[str, ...]) -> tuple[Section | None, tuple[str, ...]]:
    """Which section a dotted key path belongs to, and the key path inside it.

    `("plot", "data", "file")` → the `plot.data` subsection; `("quantity", "pdf", "values")` → the
    `quantity` family; `("sinks", "module")` → the module sink array.
    """
    if not path:
        return None, ()
    if path[0] == "sinks" and len(path) >= 2 and path[1] == "module":
        return MODULE_SINK, path[2:]
    if path[0] == "proc" and len(path) >= 2 and path[1] in {"fit", "hist"}:
        return (PROC_FIT if path[1] == "fit" else PROC_HIST), path[2:]
    section = SECTIONS.get(path[0])
    if section is None:
        return None, path
    if section.shape == "named":
        return section, path[2:]          # quantity.<name>.<key>
    for name, subsection in section.subsections.items():
        if len(path) >= 2 and path[1] == name:
            return subsection, path[2:]
    return section, path[1:]
