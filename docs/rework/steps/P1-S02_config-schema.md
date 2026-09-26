# P1-S02 — Implement the schema-2 loader with strict validation and layering

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P1-S01](P1-S01_package-skeleton.md) |
| Blocks | [P1-S03](P1-S03_sweep-engine.md) |
| Effort | 1 d |
| Findings / decisions | F2; 00/B7 (partly); utils defect: negative thread wrap |
| Updated | 2026-09-18 |

## Goal

Any run TOML loads into typed dataclasses with origin tracking; unknown keys, wrong types and out-of-range values fail with file:key, a did-you-mean hint and a fix; `extends`, the machine file and CLI `--set` layer in a defined order.

## Context

- 03 §1–2, §6; 01 N4.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth_common.py:16-180` | `get_*`, `reject_*`, `validate_config` | port as schema validators |
| `legacy/utils/Utility/Toml.hh:75-92` | `requirePositive` with key context | idea |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- Sections: `[run]`, `[generator]` (tools incl. `store` + `input`), `[beams]` (`ids`, `energies`), `[rivet]`, `[store]`, `[[analyzers.module]]`, `[delphes]`, `[output]`, `[plot]`, `[plot.data]` (incl. `map`), `[terminal]`, `[[proc.fit]]`, `[[proc.hist]]`, `[static]`, `[quantity.*]`, `[sweep]`, `[study.*]`
- Field metadata: doc, type, default, range, since (feeds `hep config reference`)
- Layering: defaults < machine file (allow-list) < extends chain < file < static < study < pins/--set < sweep values; origin per value
- Unknown keys at **every** level (incl. top level) are errors

**Out (non-goals)**

- Sweep semantics (S03)
- migration of v1 files (S06)

## Design notes

- Plain dataclasses + a small validator layer (no pydantic dependency).
- Integers are range-checked before any conversion (no wrap).

## Tasks

- [x] Write `hekit/config/{schema,load,layer,validate}.py`
- [x] Unit tests for every rule

## Outputs

- `utils/python/hekit/config/*`
- `tests/python/config/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| did-you-mean | pytest: `[plot] min_entry` | error suggests `min_entries` |
| No wrap | pytest: `[run] threads = -1` | range error |
| extends cycle | pytest: a↔b | error naming both files |
| Machine allow-list | pytest: machine file sets `generator.card` | error |
| Origin | pytest: `--explain run.threads` | chain file:line → cli |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert the package directory.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **done.**
  - **Process deviation:** the mirror into `bots/current_plan.md` was written part-way through the step
    instead of before it started. The status in this file and in the index was also set late.
  - **Modules** (deviation from the planned file list: `layer.py` became part of `load.py`, and the `Config`
    object lives in a new `model.py`, because layering and reading share the flattening code):
    - `fields.py` — `Field(kind, default, doc, minimum, maximum, choices, item, free, value_kind, required)`
      and the checks built on it; `Section`; duration parsing (`500ms`, `30s`, `5m`, `1h`, plain seconds).
    - `schema.py` — all 18 sections of 03 §1 as field tables. The section dataclasses are **generated** from
      those tables (`make_dataclass`), so defaults, types and documentation cannot drift; `hep config
      reference` (P1-S06) will read the same tables. `section_of()` maps a dotted path to its section,
      including `[plot.data]`, `[[analyzers.module]]`, `[[proc.fit]]`, `[[proc.hist]]`, `[quantity.<n>]`,
      `[study.<n>]`.
    - `load.py` — file reading, **origin scanning** (a line scanner: `tomllib` reports no line numbers, so a
      separate pass records `file:line` per key, indexing repeated `[[array]]` headers), schema-aware
      flattening, `Layer`/`Resolved` with a per-key layer chain, the machine allow-list, the `extends` chain
      with cycle detection, and `--set` parsed as TOML so types survive.
    - `model.py` — `Config` (typed sections, `quantities`, `studies`, `module_analyzers`, `proc_fits`,
      `proc_hists`, `warnings`), `Study` (its own scan plus captured section overrides), `load_config()`,
      `origin()`, `explain()`, `quantity()` with a did-you-mean.
    - `validate.py` — schema version, quantity shape, and the cross-section rules.
  - **Design decisions taken while implementing:**
    - *Flattening stops at single-value keys.* Tables merge deeply, but a table on a key that holds one value
      (`[quantity.<q>].key = { pythia = "PDF:pSet" }`) replaces as a whole; only *free* tables
      (`[static.gen]`, `[rivet].options`, `[plot.data].map`, `[static.use]`, `pin`, `init`) merge key by key.
      Without this the per-tool `key` table of 03 §3 was split into leaves and rejected. Recorded in 03 §2.
    - *A field's own default always passes its `choices`.* Several keys use `""` for "not set" while listing
      choices (`sweep.style`, `quantity.side`, `quantity.type`); the emptiness is caught by the rule that
      needs the value, not by the enum check.
    - *Defaults are a layer.* Every key has a value and an origin (`default`), which also means the field
      tables are validated against their own rules on every load — that caught two schema mistakes here.
    - *Warnings are collected, not printed* (`config.warnings`), so the caller decides. Two exist so far: a
      scalar √s with differing beam ids (CM-frame η shift) and `[plot.data]` without a `map` (00/B5).
  - **Validation coverage:** unknown keys at every level (top level, section, named section, array entry,
    study override) with did-you-mean; types (bool is not an int); ranges (`threads = -1` → "must be ≥ 0",
    no wrap); enums; list lengths; free-table value shapes; required keys; quantity shape (labels/tags
    lengths, filename-safe unique tags, `use` in range, per-type value rules for
    `setting`/`beams`/`energies`/`seed`/`events`/`generator`/`option`, particle names rejected with the PDG id
    in the hint); cross-section rules (store needs `input` and takes no card, `input`/`shower` only with their
    tool, native Rivet mode is Sherpa-only, something must consume the events, `xsec` is "generator" or a
    positive number, `yodamerge` needs a seed-only sweep, overlay must be scanned, hidden data must be the
    reference, fit ranges and histogram bins ordered).
  - **Schema-1 files** are recognised: loading the frozen `tests/golden/inputs/PhotoProduction/eic.toml` names
    the old sections and points at `hep config migrate` instead of drowning the user in unknown-key errors.
  - **Verification:**
    | Check | Result |
    |---|---|
    | `[plot] min_entry` | `unknown key 'min_entry' in [plot]`, hint `did you mean 'min_entries'?`, where = `<file>:<line>` |
    | `[run] threads = -1` | `must be ≥ 0, not -1`; `threads = true` → `must be an integer, not bool`; `99999` → `must be ≤ 4096` |
    | extends a↔b | `extends forms a cycle`, hint lists both files |
    | machine file sets `generator.card` | refused: "a machine file may not set 'generator.card'", hint lists the allow-list (`run.threads`, `terminal.*`, `paths.lhapdf`, `tools.<n>.exe`) |
    | origin chain | `explain("run.threads")` → `default → a.toml:3 → b.toml:3 → run.toml:7 → cli`; the CLI surface (`hep plan --explain`) arrives in P1-S05 |
    | tests | `pytest tests/python tests/golden -q` → **158 passed in 1.6 s** (78 new) |
