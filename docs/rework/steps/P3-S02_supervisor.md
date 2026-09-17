# P3-S02 — Process supervisor, FIFO transport and stall detection

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P3 — Supervision, results layout, terminal |
| Depends on | [P2-S03](P2-S03_core-status.md) |
| Blocks | [P3-S04](P3-S04_terminal.md), [P3-S05](P3-S05_hep-run-command.md) |
| Effort | 1 d |
| Findings / decisions | 00/B19, B20; F4; 06 §4 |
| Updated | 2026-09-17 |

## Goal

`hekit.run` spawns stages as data, wires FIFOs in a per-run private directory, polls all stages, escalates signals, attributes the first real failure, detects stalls, and always cleans up.

## Context

- 06 §3.3 exit codes, §4 supervision.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth` `supervise`, `terminate`, `run_with_fifo` (117–222) | control flow | port + fix B20 |
| `legacy/utils/Monitor/Threading.hh:97-116` | stall predicates (monotonic idle ≥ threshold; fatal at ×N) | port |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/run/{supervisor,transport,signals,parsers}.py`
- per-stage log files; `pass_fds` for status
- SIGINT → grace → SIGTERM → SIGKILL
- stall: no status and no log growth for `stall_after`

**Out (non-goals)**

- Rendering (S04)

## Design notes

- Fake stages for tests are small Python scripts under `tests/python/run/fakes/`.

## Tasks

- [ ] Implement
- [ ] Fake-stage test suite (each test ≤ 10 s)

## Outputs

- `utils/python/hekit/run/*`
- `tests/python/run/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Early exit | pytest fake: generator exits 1 before opening FIFO | reader stopped; exit 1 attributed |
| Hang | pytest fake: silent hang | exit 7 after stall_kill |
| Flood | pytest fake: 1 GB stderr | bounded memory; log file only |
| Ignores SIGINT | pytest fake | SIGTERM after grace |
| Reader dies | pytest fake | exit 4 |
| Cleanup | all tests | FIFO dir removed |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
