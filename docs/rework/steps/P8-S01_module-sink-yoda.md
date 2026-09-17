# P8-S01 — Module API, YODA results layer and module sink

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P8 — Modules, YODA results, Phys, ML |
| Depends on | [P6-S01](P6-S01_sharded-rivet.md), [P5-S01](P5-S01_store-writer.md) |
| Blocks | [P8-S03](P8-S03_onnx.md), [P8-S04](P8-S04_decide-derived-tables.md) |
| Effort | 1.5 d |
| Findings / decisions | D14; R10; utils defects: unscaled finals, empty checkpoints |
| Updated | 2026-09-17 |

## Goal

User C++ modules (dlopen'd) book YODA objects per worker; results are merged, scaled in `finalize`, and written into `analysis.yoda` next to Rivet's; hekit merges module objects for replicas.

## Context

- 05 §5 (Modules); 07 §3.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Record/{Cloning,Declaration,Type_Methods}.hh` | clone/merge, declare-time validation, enum keys | adapt to YODA |
| `legacy/configs/defaults/Limits.toml` | binning presets | optional |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `Module/{Types,Registry,Loader}`, `HEKIT_MODULE`
- `Results/{Booker,Worker,Merge}`
- `Sink::Modules`
- combined write
- `[[sinks.module]]`
- `hekit` replica merge for module objects
- `hep new module`; CMake `hekit_<name>` targets

**Out (non-goals)**

- Derived tables (S04)

## Design notes

- Scaling contract: raw weights in `process`; scaling only in `finalize` with σ and ΣW known.

## Tasks

- [ ] Implement
- [ ] Toy module
- [ ] Tests

## Outputs

- C++ namespaces
- `modules/Examples/` toy
- tests

## Verification

| Check | Command | Expected |
|---|---|---|
| Exact totals | toy module at 1/4/20 threads | identical integrals |
| Scaling | scaled integral | = expected σ fraction |
| Dumps | periodic dump | non-empty |
| Plotting | `hep plot` / `rivet-mkhtml` | module histograms shown |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
