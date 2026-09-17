# P8-S02 — Phys namespace

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P8 — Modules, YODA results, Phys, ML |
| Depends on | [P2-S03](P2-S03_core-status.md) |
| Blocks | — |
| Effort | 0.5 d |
| Findings / decisions | 00 §3 verdict (Physics → Phys) |
| Updated | 2026-09-17 |

## Goal

PDG traits, kinematics on HepMC four-vectors, `GenEvent` selectors and jet-definition parsing are available to modules.

## Context

- 13 §2.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Physics/{Particles,Types,TypeAid,Kinematics,Properties}.hh` | tables, kinematics | port (drop ROOT GenVector) |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `Phys/{Types,Pdg,Kinematics,Select,Jets}`
- port the legacy Physics tests

**Out (non-goals)**

- —

## Design notes

- Guard for ±inf in Δφ (legacy defect).

## Tasks

- [ ] Implement
- [ ] Tests

## Outputs

- `utils/Phys*`

## Verification

| Check | Command | Expected |
|---|---|---|
| PDG | compare to Pythia `ParticleData` for the table entries | match |
| Jets | `jetDefinition("antikt:0.4")` vs FastJet | equal definitions |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
