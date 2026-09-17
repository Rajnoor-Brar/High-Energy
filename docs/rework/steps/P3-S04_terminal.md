# P3-S04 — Live dashboard, plain mode and watch/runs/show

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P3 — Supervision, results layout, terminal |
| Depends on | [P3-S02](P3-S02_supervisor.md) |
| Blocks | [P3-S05](P3-S05_hep-run-command.md) |
| Effort | 1 d |
| Findings / decisions | R5; F12; utils defect: progress interval before totals |
| Updated | 2026-09-17 |

## Goal

A `rich` inline dashboard and a plain line mode render any status stream; `hep watch`, `hep runs`, `hep show` work from files.

## Context

- 06 §1–2, §5–6.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Monitor/Methods.hh:17-26` | ETA extrapolation | idea |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/term/{dashboard,plain,theme}.py`
- `status.jsonl` writer (supervisor side)
- `hep watch/runs/show`
- curated log pane with dedupe counts

**Out (non-goals)**

- Event tables (P5-S03)

## Design notes

- Progress interval computed from totals after the `init` message (fixes the legacy bar-interval defect).

## Tasks

- [ ] Implement
- [ ] Snapshot tests

## Outputs

- `utils/python/hekit/term/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Snapshots | pytest `Console(record=True)` on recorded `status.jsonl` | stable output |
| Plain on pipe | `hep watch latest \| cat` | plain lines |
| Terminal restored | pty test with an exception mid-render | cursor/echo restored |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
