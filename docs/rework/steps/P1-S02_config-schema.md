# P1-S02 — Implement the schema-2 loader with strict validation and layering

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P1-S01](P1-S01_package-skeleton.md) |
| Blocks | [P1-S03](P1-S03_sweep-engine.md) |
| Effort | 1 d |
| Findings / decisions | F2; 00/B7 (partly); utils defect: negative thread wrap |
| Updated | 2026-09-17 |

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

- Sections: `[run]`, `[generator]` (tools incl. `store` + `input`), `[beams]` (`ids`, `energies`), `[rivet]`, `[store]`, `[[sinks.module]]`, `[delphes]`, `[output]`, `[plot]`, `[plot.data]` (incl. `map`), `[terminal]`, `[[proc.fit]]`, `[[proc.hist]]`, `[settle]`, `[quantity.*]`, `[sweep]`, `[study.*]`
- Field metadata: doc, type, default, range, since (feeds `hep config reference`)
- Layering: defaults < machine file (allow-list) < extends chain < file < settle < study < pins/--set < sweep values; origin per value
- Unknown keys at **every** level (incl. top level) are errors

**Out (non-goals)**

- Sweep semantics (S03)
- migration of v1 files (S06)

## Design notes

- Plain dataclasses + a small validator layer (no pydantic dependency).
- Integers are range-checked before any conversion (no wrap).

## Tasks

- [ ] Write `hekit/config/{schema,load,layer,validate}.py`
- [ ] Unit tests for every rule

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

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
