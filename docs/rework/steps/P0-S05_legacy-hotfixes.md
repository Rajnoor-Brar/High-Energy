# P0-S05 — Hotfix the physics-relevant defects in the legacy tools

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P0 — Baseline, hygiene, legacy freeze |
| Depends on | [P0-S04](P0-S04_golden-fixtures.md) |
| Blocks | — |
| Effort | 0.5 d |
| Findings / decisions | 00/B2, B3, B4, B5, B10, B13, B20, B21, B23; records B11, B12, B27 |
| Updated | 2026-09-17 |

## Goal

Results produced by the legacy tools until P4-S06 are trustworthy: no correlated seeds, no partial YODAs treated as complete, correct labels, no mismatched data overlay, real error reporting.

## Context

- D19 hotfix-then-port; D20 test bed (B11 no action).
- B1 (identity seeds) needs the new planner; here only the B2 guard is added.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth` `supervise`, `run_with_fifo`, `main` | control flow | patch |
| `tools/rivpyth_common.py:679-686` | seed offset | guard |
| `sources/PhotoProduction/generator.cc:67-87` | write loop | patch |
| `configs/PhotoProduction/{eic,zeus_validation}.toml`, `photo_ep.cmnd` | labels/comments | edit |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- B3: rivet writes `<name>.yoda.part`; after both processes exit 0, check `/_EVTCOUNT` numEntries == event_count, then rename; `skip_existing` ignores `.part`.
- B20: collect both exit statuses; report the first non-zero that is not a SIGPIPE/SIGTERM caused by our own termination.
- B21: `generator.cc` exits 4 if `nWritten != nGenerated`.
- B2: `ConfigError` if `threads > 1 and seed_step < threads`; configs get `seed_step = 20`.
- B4 label √s = 318.1 GeV; B5 `use_data = false` in `eic.toml`; B10/B13/B23 comments; B28 left for P0-S06.

**Out (non-goals)**

- B1, B6–B9, B12, B14–B19, B22 (hekit)
- B11 (no action)
- B27 (record only)

## Design notes

- Seeds change for all points (B2 guard + seed_step) → re-capture plan fixtures and list the expected differences in `tests/golden/legacy_plan/EXPECTED_DELTAS.md`.
- Record in this file's Log: B27 (pTHatMin 6 > ETMIN 5; the pthatmin study measures it), B12 (tag rename deferred to v2 migration).

## Tasks

- [ ] Patch `tools/rivpyth` (B3, B20)
- [ ] Patch `tools/rivpyth_common.py` (B2 guard)
- [ ] Patch `generator.cc` (B21); rebuild
- [ ] Edit configs/comments (B2 seed_step, B4, B5, B10, B13, B23)
- [ ] Re-capture fixtures; write `EXPECTED_DELTAS.md`
- [ ] Scratch tests below

## Outputs

- patched `tools/*`, `sources/PhotoProduction/generator.cc`, configs
- `tests/golden/legacy_plan/EXPECTED_DELTAS.md`
- `tests/golden/test_hotfixes.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Kill test (B3) | scratch: start `rivpyth` on a mini point, `kill -TERM` after 2 s | no final `.yoda`; `.part` present; rerun with `skip_existing` regenerates |
| Error attribution (B20) | scratch config with a bogus analysis name | exit status and message are Rivet's |
| Write failure (B21) | `generator.exe /proc/forbidden base.cmnd point.cmnd` | non-zero exit |
| Seed guard (B2) | config with threads=20, seed_step=1 | `ConfigError` |
| Fixtures | `pytest tests/golden -q` | pass (with expected deltas) |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

`git revert` the hotfix commit; fixtures re-captured from P0-S04 commit.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
