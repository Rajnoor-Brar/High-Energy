# P0-S07 — Reduce the Makefile to what is still built

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P0 — Baseline, hygiene, legacy freeze |
| Depends on | [P0-S06](P0-S06_legacy-archive.md) |
| Blocks | [P1-S01](P1-S01_package-skeleton.md), [P2-S01](P2-S01_cmake-skeleton.md) |
| Effort | 0.2 d |
| Findings / decisions | plans 0.3 (reduced); 00 §4.4; F11 |
| Updated | 2026-09-18 |

## Goal

The interim Makefile builds only `generator.exe` and Rivet plugins, with per-target libraries, lazy flag evaluation and visible errors.

## Context

- After P0-S06 nothing else is built by make; CMake arrives in P2-S01, the Makefile becomes a wrapper in P4-S06.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `Makefile` | current rules | rewrite |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- Recursive `=` for `*-config` flags
- `generator.exe`: Pythia + HepMC3 only
- `.so`: `rivet-build` only; metadata copy failures fail the rule
- `make test` prints a pointer to pytest/ctest

**Out (non-goals)**

- CMake (P2-S01)
- header dependency tracking (moot: no utils headers left)

## Design notes

- Drop ONNX, Delphes, ROOT, toml++, YODA/LHAPDF flags from the generic rule.

## Tasks

- [x] Rewrite rules
- [x] Build both targets
- [x] Force a copy failure in scratch to see the error

## Outputs

- `Makefile`

## Verification

| Check | Command | Expected |
|---|---|---|
| No ONNX in generator link | `make -n PhotoProduction/generator.exe \| grep -c onnx` | 0 |
| Builds without ONNX env | `env -u ONNXRUNTIME_DIR make PhotoProduction/generator.exe` | OK |
| Plugin + metadata | `make PhotoProduction/photo_eic.so && ls output/PhotoProduction/photo_eic.info` | exists |
| Errors visible | scratch: unreadable `.plot` | rule exits non-zero |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

`git revert`.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **done.**
  - Rewritten: lazy `=` for `pythia8-config`, `HepMC3-config` and the git defines (nothing shells out until a
    build needs it); per-target `LIBS_<target>` with `generator.exe` = Pythia + HepMC3 only; ROOT, toml++, ONNX,
    Delphes, FastJet, YODA and LHAPDF dropped from the generic rule, together with the stale
    `-I./utils -I./modules` (both directories disappeared in P0-S06). Rivet plugins take no library flags:
    `rivet-build` supplies its own.
  - A failing metadata copy now fails the rule (the old rule ended in `; true`).
  - `make test` points at `pytest tests/golden` and says ctest arrives in P2-S01; `make help` is the default goal.
  - **Deviation:** `clean` no longer removes the whole `output/` tree — it deletes only `*.exe` and `Rivet_*.so`
    per project, so `output/scratch/` (the golden-fixture scratch areas, gitignored) survives. `distclean` keeps
    the old behaviour. The audit's complaint that `clean` removed the plugins `RIVET_ANALYSIS_PATH` points at is
    unchanged in kind (the plugins are build products), but a stray `make clean` no longer destroys scratch state.
  - **Not addressed (out of scope):** `GIT_SHA` changes still do not trigger a rebuild, and header dependency
    tracking is moot (no project headers are included any more). CMake handles both in P2-S01.
  - **Verification:**
    | Check | Result |
    |---|---|
    | `make -n PhotoProduction/generator.exe \| grep -c onnx` | **0** |
    | `env -u ONNXRUNTIME_DIR make PhotoProduction/generator.exe` | builds |
    | `make PhotoProduction/photo_eic.so` | builds; `output/PhotoProduction/photo_eic.info` and `.plot` present |
    | read-protected `.plot` in a scratch `SOURCE_ROOT` | `Failed to copy …`, make exits **2**; after `chmod 644`, exit 0 and both metadata files appear |
