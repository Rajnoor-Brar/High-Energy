# P2-S01 — CMake build with optional components

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P2 — C++ core, CMake, hep-run v1 |
| Depends on | [P0-S07](P0-S07_makefile-hygiene.md) |
| Blocks | [P2-S02](P2-S02_pythia-parallel-spike.md), [P2-S03](P2-S03_core-status.md) |
| Effort | 0.75 d |
| Findings / decisions | F11; 00 §4.4; N5 |
| Updated | 2026-09-17 |

## Goal

`cmake -S . -B build` builds the (still empty) facade libraries, `hep-run` stub and Rivet plugins; optional components switch off cleanly; compile commands and ctest are available; `photo_eic` lives in `analyses/PhotoProduction/`.

## Context

- 09 §1; 13 §2 (one INTERFACE library per facade).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `Makefile` `.so` rule | rivet-build + metadata copy | reproduce as a CMake custom target |
| `*-config` scripts (pythia8, rivet, yoda, HepMC3, lhapdf, fastjet) | flags | wrap in `cmake/Find*.cmake` |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `CMakeLists.txt`, `cmake/Find{Pythia8,Rivet,YODA,HepMC3,LHAPDF,FastJet,TomlPlusPlus,OnnxRuntime,Delphes}.cmake`
- Options `HEKIT_WITH_{RIVET,HEPMC,ONNX,DELPHES}` (AUTO/OFF); HepMC compression definitions + zlib (+zstd if found)
- `git mv sources/PhotoProduction/photo_eic.* analyses/PhotoProduction/`; `rivet_<project>` targets; interim Makefile `.so` rule also searches `analyses/`
- ctest + pytest registration; `compile_commands.json`

**Out (non-goals)**

- Namespace code (S03+)
- Makefile → wrapper (P4-S06)

## Design notes

- Per-project dirs discovered by glob (`analyses/*/`, `modules/*/`).
- `hep build` wraps cmake later (P3/P4).

## Tasks

- [ ] Write CMake + Find modules
- [ ] Move photo_eic
- [ ] Configure full and minimal builds
- [ ] Register ctest/pytest

## Outputs

- `CMakeLists.txt`, `cmake/*`, `analyses/PhotoProduction/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Full build | `cmake -S . -B build -G Ninja && cmake --build build` | OK |
| Minimal build | `cmake -S . -B build-min -DHEKIT_WITH_RIVET=OFF -DHEKIT_WITH_HEPMC=OFF -DHEKIT_WITH_ONNX=OFF && cmake --build build-min` | OK |
| Plugin | `ls build/analyses/PhotoProduction/{Rivet_photo_eic.so,photo_eic.info}` | exist |
| Legacy make still works | `make PhotoProduction/photo_eic.so` | OK |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert; `git mv` photo_eic back.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
