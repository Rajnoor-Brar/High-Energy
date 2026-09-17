# P4-S06 — Retire rivpyth/ydplt/ydmrg and generator.cc

| Field | Value |
|---|---|
| Status | todo |
| Kind | git |
| Phase | P4 — Plotting, compare, retirement of the legacy tools |
| Depends on | [P4-S02](P4-S02_plot-mkhtml.md), [P4-S05](P4-S05_photo-eic-reentrant.md), [P3-S05](P3-S05_hep-run-command.md), [P2-S06](P2-S06_equivalence-gate.md), [P1-S06](P1-S06_config-migrate.md) |
| Blocks | [P10-S01](P10-S01_cleanup-housekeeping.md) |
| Effort | 0.5 d |
| Findings / decisions | rule 1; D18, D19 |
| Updated | 2026-09-17 |

## Goal

After a real-study cross-check, the legacy tools and generator move to `legacy/`, v2 configs become canonical, and the Makefile becomes a thin CMake wrapper.

## Context

- Gate: the `pdf` study at 100k events, run by both toolchains in scratch, is compatible (`hep compare`).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/*`, `sources/PhotoProduction/generator.cc`, `configs/PhotoProduction/*.toml` | files | move/rename |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `git mv tools/* legacy/tools/`
- `eic.v2.toml` → `eic.toml`, `zeus_validation.v2.toml` → `zeus_validation.toml` (old → `legacy/configs/`)
- `generator.cc` → `legacy/`
- Makefile wrapper (`make`, `make test`, `make analyses P=…`)
- env: drop `tools/` from PATH; remove `~/HEP/*.moved` (approval)

**Out (non-goals)**

- Removing transition shims (P10-S01)

## Design notes

- `sources/` is removed if empty.

## Tasks

- [ ] Run the gate
- [ ] Moves (approval)
- [ ] Wrapper Makefile
- [ ] Env update

## Outputs

- moved files
- `Makefile`

## Verification

| Check | Command | Expected |
|---|---|---|
| Gate | scratch pdf study both ways + `hep compare` | compatible |
| Retired | `which rivpyth` | not found |
| No references | `git grep -n rivpyth -- ':!legacy' ':!docs'` | empty |
| Build + tests | `make && make test` | cmake, ctest, pytest green |
| E2E | `hep plan/run/plot` on eic.toml (scratch) | works |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

`git revert`; restore PATH entry.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
