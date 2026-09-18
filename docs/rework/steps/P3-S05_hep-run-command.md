# P3-S05 — Wire the hep run command end to end

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P3 — Supervision, results layout, terminal |
| Depends on | [P3-S02](P3-S02_supervisor.md), [P3-S03](P3-S03_results-provenance.md), [P3-S04](P3-S04_terminal.md), [P2-S05](P2-S05_rivet-sink-results-writer.md) |
| Blocks | [P4-S06](P4-S06_retire-legacy-tools.md), [P7-S01](P7-S01_adapter-framework.md) |
| Effort | 0.5 d |
| Findings / decisions | R1–R6; rule 1 |
| Updated | 2026-09-18 |

## Goal

`hep run CONFIG [selectors]` plans, supervises `hep-run`, renders, writes results and provenance, honours `--check`, `--rerun`, `--detach`, `--events`, `--threads`, `--set`.

## Context

- 08 §2.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth:225-263` `main` | flow | replace |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/cli` run command
- `tests/e2e/mini.toml`

**Out (non-goals)**

- External generators (P7)

## Design notes

- `--check` runs `hep-run --check` for every group before spawning any run.

## Tasks

- [x] Implement
- [x] e2e tests in scratch

## Outputs

- CLI wiring
- `tests/e2e/mini.toml`
- `tests/integration/test_hep_run_e2e.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| e2e | `HEKIT_RESULTS=output/scratch/r hep run tests/e2e/mini.toml` | 2 groups, YODA + provenance |
| Study | 4-point PDF study at 20k (scratch) | completes with dashboard |
| Ctrl-C | interrupt mid-run | partial + exit 6; later points not started |
| Rerun | `hep run` again | done points skipped, partial redone |
| Preflight | config with ProcessType 2 | stopped before any spawn |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — implemented `hekit/run/cli.py` (459 lines), `tests/e2e/mini.toml` and
  `tests/integration/test_hep_run_e2e.py` (13 cases, 67 s, ctest test `e2e`, label `slow`).
  Suite: 488 Python, **12/12 ctest**. **Phase P3 is complete.**

  **Verification, every row measured**

  | Row | Result |
  |---|---|
  | e2e | 2 generations, each with `analysis.yoda`, `run.summary.json`, `provenance.json`, `run.toml`, `point.cmnd`, `status.jsonl` and `logs/hep-run.log`; σ = 7.314e+04 and 7.224e+04 pb for the two PDF sets |
  | Study | the 4-point PDF study of `eic.v2.toml` at 20 k events, live dashboard under a pty: **4 done in 1m34s**, one point directory each, `studies/01_pdf/` |
  | Ctrl-C | **exit 6**; the running point left `analysis.partial.yoda` (2 000 of 200 000 events, σ recorded) and *no* `analysis.yoda`; the second point was never started |
  | Rerun | `0 done, 2 skipped` — "name, hash and a finished result all match"; `--rerun` redoes them; a partial is redone; a changed identity is **refused** with the `--rerun` hint |
  | Preflight | `Photon:ProcessType = 2` → **exit 3** before any spawn: no YODA, no study directory, only the specs and cards on disk |

  **The order the command imposes** (the part that is not delegated): plan everything → refuse a name
  collision → write every spec → preflight *every* generation with `hep-run --check` → run them one at
  a time → stamp, provenance, manifest. Exit code is the worst point's.

  **Defects found and fixed while wiring it up**

  1. **The skip rule never matched.** The plan holds a bare digest and a written spec holds
     `sha256:<digest>`, so every rerun looked like a name collision. `skip.same_hash` now compares
     them prefix-insensitively. This is the kind of thing only an end-to-end run finds.
  2. **Ctrl-C reached nothing.** Every stage is started with `start_new_session=True`, so the user's
     SIGINT goes to `hep` alone — the run continued to completion and exited 0. `Supervisor.run` now
     takes `should_stop()` and forwards the request one escalation step per press, which is what makes
     "stop at the next checkpoint" true rather than aspirational.
  3. **One renderer per *point*** meant the plain header reprinted and lines interleaved out of order;
     it is now one renderer for the run.
  4. **Warnings were re-emitted on every poll** (`reader.logs[len(point.logs):]` compares a list that
     keeps duplicates with one that de-duplicates), so a single warning printed four times with a
     growing count. The consumed count is tracked per stage now.
  5. A progress line identical to the previous one is dropped — at 100 % the same line was printed on
     every poll.
  6. **Provenance tool keys were display names** (`"Pythia"`); 07 §2 writes them lower case
     (`"pythia": "8.317"`), and a machine-readable document should not carry capitalisation.
  7. **`hep show --help` contained a `σ`**, which a C-locale stdout cannot encode. Help text is now
     ASCII; the same trap appeared three times in tests decoding child output with the locale, so the
     test helpers decode explicitly.
  8. The dashboard's point-name column is sized from the longest name in the run: a long name ran into
     its own numbers (`…PDF4LHC21_pt32_mpi20.00 k ev`), and the final frame is now drawn *after* the
     run is marked finished, so the last thing on screen is the tally and not the Ctrl-C hint.

  **Deviations**

  1. `tests/e2e/mini.toml` borrows PhotoProduction's built Rivet plugin through `[rivet].paths`; it is
     not a project of its own and should not need one to be an end-to-end fixture.
  2. `--detach` is implemented but not covered by a test: it hands the run to `setsid` and returns, so
     asserting on it means watching a background process that outlives the test. `hep watch` (tested)
     is how its output is read.
  3. The step's test file names are `tests/e2e/mini.toml` and `tests/integration/test_hep_run_e2e.py`,
     exactly as specified; the ctest entry is `e2e` (label `slow`) beside `equivalence`.
