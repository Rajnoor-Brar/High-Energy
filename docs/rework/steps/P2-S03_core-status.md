# P2-S03 — Core and Status namespaces

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P2 — C++ core, CMake, hep-run v1 |
| Depends on | [P2-S01](P2-S01_cmake-skeleton.md), [P1-S01](P1-S01_package-skeleton.md) |
| Blocks | [P2-S04](P2-S04_source-run-loop.md), [P3-S02](P3-S02_supervisor.md), [P8-S02](P8-S02_phys.md) |
| Effort | 1 d |
| Findings / decisions | F4; 06 §3; legacy utils reuse |
| Updated | 2026-09-17 |

## Goal

`Core` (spec reader, errors/exit codes, signals, clocks, sha256, paths, provenance record) and `Status` (fd-3 JSON lines, heartbeat, plain fallback) exist with tests; a minimal Python status reader round-trips.

## Context

- 13 §2; 06 §3.1–3.3; house style (facade + submodules).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Utility/Sha256.hh` + FIPS vectors `legacy/tests/test_utils_hardening.cc` (~129–153) | code + vectors | copy; add regular-file check |
| `legacy/utils/Utility/Signals.hh:22-57` | stop flag | adapt to `sigaction`, second signal escalates |
| `legacy/utils/Utility/{Time,Paths}.hh` | clock aliases, root discovery | adapt |
| `legacy/utils/Monitor/Threading.hh:121-136,212-213,256-265`, `Monitor/Timer.hh` | deadline loop, coalescing, timers | adapt/copy |
| `legacy/utils/Record/Meta.hh:25-110,243-299` | provenance fields | idea |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `utils/Core.hh` + `Core/{Types,Spec,Errors,Signals,Clock,Sha256,Paths,Provenance}.hh`
- `utils/Status.hh` (with `#ifdef Status` guard) + `Status/{Types,Writer,Heartbeat,Plain,Timer}.hh`
- `hekit/run/status.py` reader
- ctest + pytest

**Out (non-goals)**

- Source/Sink/Run (S04+)

## Design notes

- Spec: structural validation only, against `spec_v2.json` field list.
- Status writer: atomic counters read by a heartbeat thread; the event loop never formats JSON.

## Tasks

- [ ] Implement Core
- [ ] Implement Status
- [ ] Python reader
- [ ] Tests

## Outputs

- `utils/Core*`, `utils/Status*`
- `tests/cpp/{core_*,status_*}`
- `utils/python/hekit/run/status.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Spec errors | `ctest -R core_spec` | missing key → exit 1 with key name |
| SHA-256 | `ctest -R core_sha256` | FIPS vectors pass |
| Signals | `ctest -R core_signals` | first SIGINT sets flag; second escalates |
| Round trip | `ctest -R status_roundtrip` (+ pytest reader) | all kinds parsed; unknown kinds ignored |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
