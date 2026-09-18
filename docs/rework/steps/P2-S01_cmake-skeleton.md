# P2-S01 — CMake build with optional components

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P2 — C++ core, CMake, hep-run v1 |
| Depends on | [P0-S07](P0-S07_makefile-hygiene.md) |
| Blocks | [P2-S02](P2-S02_pythia-parallel-spike.md), [P2-S03](P2-S03_core-status.md) |
| Effort | 0.75 d |
| Findings / decisions | F11; 00 §4.4; N5 |
| Updated | 2026-09-18 |

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

- [x] Write CMake + Find modules
- [x] Move photo_eic
- [x] Configure full and minimal builds
- [x] Register ctest/pytest

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

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **done.**
  - **`cmake/`**: `HekitDependency.cmake` turns `*-config` output into imported interface targets, and
    nine Find modules use it (`Pythia8`, `Rivet`, `YODA`, `HepMC3`, `LHAPDF`, `FastJet`, `TomlPlusPlus`,
    `OnnxRuntime`, `Delphes`). Compiler flags that are neither `-I` nor `-D` are **dropped on purpose**:
    `pythia8-config --cxxflags` hands out `-O2 -std=c++17`, which must not override the build type or the
    standard the project chose. `-L` directories also become `-rpath`, so a built binary runs without
    `LD_LIBRARY_PATH`.
  - **Options:** `HEKIT_WITH_{RIVET,HEPMC,ONNX}` are AUTO/ON/OFF (AUTO = on when found; ON demands it),
    `HEKIT_WITH_DELPHES` defaults to OFF because the in-process sink is deferred. Pythia and YODA are the
    hard requirements.
  - **Facades:** one INTERFACE library per namespace of 13 §2, linked in dependency order so that a lower
    layer can never link a higher one. Compression flags land on `hekit_Store` exactly as verified in
    P0-S00 (`HEPMC3_USE_COMPRESSION`, `HEPMC3_Z_SUPPORT`, plus zstd when found).
  - **`hep-run` stub** (`utils/apps/hep-run.cc`): `--capabilities` prints the JSON that `hep doctor` and
    `hep plan` read (version, spec schema, build type, compression, components), `--version`, `--help`;
    anything else exits 2 (usage) or 3 with the step that implements it. The real loop is P2-S04.
  - **Analyses:** `photo_eic.{cc,info,plot}` moved to `analyses/PhotoProduction/` with `git mv`. Projects
    are discovered by glob, so adding one needs no CMake edit; each gets a `rivet_<project>` target built
    with `rivet-build` (keeping ABI compatibility with the installed Rivet) with the metadata copied
    beside the library. A plugin whose `.info` says `Requires: ONNX` gets the ONNX flags.
  - **The interim Makefile** searches `analyses/` first, then `sources/`, so `make PhotoProduction/photo_eic.so`
    still builds into `output/PhotoProduction/` for the legacy pipeline.
  - **ctest** runs the C++ checks and the whole Python suite, so one command checks everything;
    `compile_commands.json` is exported. `build/`, `build-*/` and `compile_commands.json` are gitignored.
  - **`hep doctor`** now finds a built-but-not-installed `hep-run` in `build/bin`, and reports its
    components, compression and spec schema.
  - **Two CMake traps worth recording:** a `;` inside a quoted string is a list separator, which silently
    split a `FAIL_MESSAGE` into unknown keywords, and expanding a list into a compile definition turned
    `gz;zst` into `-DHEKIT_COMPRESSION="gz -Dzst`. Both are now joined explicitly.
  - **Verification:**
    | Check | Result |
    |---|---|
    | Full build | `cmake -S . -B build -G Ninja && cmake --build build` → `hep-run` + `Rivet_photo_eic.so`; components `rivet, hepmc, onnx`, compression `gz,zst` |
    | Minimal build | all three components OFF → builds, `hep-run --capabilities` reports no components and no compression |
    | Plugin | `build/analyses/PhotoProduction/{Rivet_photo_eic.so,photo_eic.info,photo_eic.plot}` exist |
    | Legacy make | `make PhotoProduction/photo_eic.so` → builds from `analyses/` into `output/PhotoProduction/` |
    | ctest | 4 tests (3 cxx + the Python suite), all pass in 5.4 s |
    | Suite | `pytest tests/python tests/golden -q` → **320 passed** |
