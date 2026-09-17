# P7-S06 — Decide and (optionally) rebuild ThePEG/Herwig

| Field | Value |
|---|---|
| Status | todo |
| Kind | decision |
| Phase | P7 — External generators and Delphes |
| Depends on | [P1-S07](P1-S07_doctor-pdf.md) |
| Blocks | [P7-S07](P7-S07_herwig.md) |
| Effort | 0.25 d + build |
| Findings / decisions | Q6; F10; 00 §1.3 |
| Updated | 2026-09-17 |

## Goal

A recorded decision on rebuilding ThePEG with HepMC and Rivet support; if rebuilt, `hep doctor` detects the modules.

## Context

- Without the rebuild Herwig is 'run-only'.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `~/HEP/src` build trees | configure flags | read |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- decision; optional rebuild commands and timings

**Out (non-goals)**

- Herwig adapter (S07)

## Decision record

- **Question:** Rebuild ThePEG `--with-hepmc=$HEP_INSTALL/hepmc3 --with-rivet=$HEP_INSTALL/rivet` and Herwig now, later, or never?
- **Options:**
  - now
  - later (when a Herwig study is planned)
  - never (Herwig stays run-only)
- **Criteria:**
  - need for Herwig comparisons
  - build time/risk
  - toolchain stability
- **Evidence:** (fill in)
- **Decision:** (fill in; user sign-off)
- **Consequences:** P7-S07 enabled or dropped; doctor output
- **Docs to update:** 04_Generators.md §6, 10_Roadmap.md §5, steps/README.md decision register

## Tasks

- [ ] Ask user
- [ ] If yes: rebuild in `~/HEP/build`, record commands
- [ ] Update doctor check

## Outputs

- decision record D-Q6

## Verification

| Check | Command | Expected |
|---|---|---|
| Detected | `hep doctor --json \| jq -r .generators.herwig.status` | `ok` (if rebuilt) |
| Read works | `Herwig read` toy card | OK (if rebuilt) |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Keep old install (build into a separate prefix first).

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
