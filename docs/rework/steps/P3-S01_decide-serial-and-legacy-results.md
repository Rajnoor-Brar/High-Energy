# P3-S01 — Decide the serial label and the fate of legacy results

| Field | Value |
|---|---|
| Status | todo |
| Kind | decision |
| Phase | P3 — Supervision, results layout, terminal |
| Depends on | [P0-S04](P0-S04_golden-fixtures.md) |
| Blocks | [P3-S03](P3-S03_results-provenance.md) |
| Effort | 0.1 d |
| Findings / decisions | Q3, Q4; 00 §4.1 (results series 01–04, serial drift) |
| Updated | 2026-09-17 |

## Goal

Q3 and Q4 are decided and recorded before the results layout is implemented (P3-S03).

## Context

- 07 §1; inventory `legacy/results/PhotoProduction.inventory.json` (P0-S04/S06).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| results inventory | series, partial flags, serials | evidence |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- Decision records; if approved, a plain `mv results/PhotoProduction/* results/PhotoProduction/legacy/` (gitignored dir) with a README

**Out (non-goals)**

- Converting legacy YODAs

## Decision record

- **Question:** Q3: keep a numeric serial in names/paths? Q4: import legacy results into the new layout, or freeze them?
- **Options:**
  - Q3-A (proposed): no serial in paths; optional free-text `run.label` in manifests
  - Q3-B: keep `NN_` prefix
  - Q4-A (proposed): no import; move to `results/PhotoProduction/legacy/` + README; `[plot].extra` overlays by path
  - Q4-B: `hep import-legacy` converting to point dirs
- **Criteria:**
  - legacy hashes cannot be rebuilt (seed/serial drift, reconstructed cmnds, possible partial files)
  - effort
  - risk of mixing untrusted outputs with new ones
- **Evidence:** (fill in: inventory summary)
- **Decision:** (fill in; user sign-off)
- **Consequences:** 07 §1 table; P3-S03 layout; P4-S02 `[plot].extra`
- **Docs to update:** 07_Outputs.md §1, 10_Roadmap.md §5, steps/README.md decision register

## Tasks

- [ ] Summarise inventory
- [ ] Ask user
- [ ] Record
- [ ] Move legacy results if approved

## Outputs

- decision records D-Q3, D-Q4
- `results/PhotoProduction/legacy/README.md` (if moved)

## Verification

| Check | Command | Expected |
|---|---|---|
| Sign-off recorded | Decision record | filled |
| Move complete | `find results/PhotoProduction/legacy -type f \| wc -l` vs inventory | equal (if moved) |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

`mv` back (gitignored files).

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
