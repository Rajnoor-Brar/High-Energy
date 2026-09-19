# P6-S03 — hep bench

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P6 — Throughput |
| Depends on | [P6-S01](P6-S01_sharded-rivet.md) |
| Blocks | — |
| Effort | 0.5 d |
| Findings / decisions | A4; 05 §3 |
| Updated | 2026-09-19 |

## Goal

`hep bench CONFIG` measures generation only, generation with sinks, and replay with k readers, and recommends a concurrency mode.

## Context

- Decision rule 05 §3.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Monitor/Timer.hh` (ported in P2-S03) | timers | reuse |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- CLI + recommendation logic

**Out (non-goals)**

- Automatic tuning

## Design notes

- Small event counts; results cached per machine.

## Tasks

- [x] Implement
- [x] Unit-test the recommendation logic

## Outputs

- `hekit` bench command

## Verification

| Check | Command | Expected |
|---|---|---|
| Runtime | `hep bench tests/e2e/mini.toml` | < 2 min |
| Logic | pytest | recommendations match table |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-19 — implemented `hekit/run/bench.py` and `hep bench`. New ctest test `bench` (label
  `slow`, 7 cases) plus 15 unit tests for the rule. Suite: **20/20 ctest, 596 Python**.
  **Phase P6 is complete.**

  **Verification, both rows measured**

  | Row | Result |
  |---|---|
  | Runtime | `hep bench tests/e2e/mini.toml` at 600 events: **~11 s** for four legs, well inside the row's 2 minutes. The integration test asserts a 120 s ceiling so a loaded machine cannot flake it |
  | Logic | 15 unit tests over the pure `recommend`, covering every row of the table below, plus `sink_share`, the cache round-trip and a corrupt cache |

  **What it reports**, on PhotoProduction at 1 000 events, two threads:

  ```
    generation      0.18s        5523 ev/s
    serial          0.75s        1327 ev/s
    sharded     refused: photo_eic clusters jets, which cannot be done from several threads
    replay          0.52s        1916 ev/s

    the sinks are 76% of a serial run's wall clock
    recommended: [run].mode = "serial"
    because photo_eic clusters jets, which cannot be done from several threads
  ```

  **This answers assumption 01 A4 with a number.** "Is Rivet's CPU cost per event comparable to or
  larger than Pythia's?" — **larger, about three times**: the sinks are ~75 % of a serial run's wall
  clock, so generation is a quarter of it. The assumption was right, and P6-S01's finding is what
  makes it moot for this project: the analysis that costs the most is the one that cannot be shared
  out.

  A replay reads back at 1 916 ev/s against 1 327 for generate-and-analyse — about **1.5x**, which is
  the number that says whether "generate once, analyse many" (11) is worth the disk on this machine.

  **The rule, and why it is in that order.** `recommend()` asks *is it allowed?* before *is it
  faster?*, because a sharded run of an analysis that clusters jets is not a faster run, it is a
  wrong one (00/B31):

  | generation | serial | sharded | recommendation |
  |---|---|---|---|
  | any | measured | refused | `serial`, quoting the refusal verbatim |
  | any | measured | ≥ 1.15x faster | `sharded`, with the speedup |
  | any | measured | < 1.15x faster | `serial` — "not worth the extra moving parts" |
  | ≈ serial | measured | marginal | `serial` — "the sinks cost almost nothing, so there is nothing to parallelise" |
  | any | not measured | any | `serial` — nothing to compare |

  The last two are different answers to the same speedup and lead somewhere different: cheap sinks
  mean more threads would help, while expensive-but-unparallelisable sinks mean something is under a
  lock. Verified in the other direction too — with `MC_FSPARTICLES` + `MC_XS` on four threads it
  measures 1.91x and recommends `sharded`.

  **Deviations**

  1. The default is **2 000 events**, not the 10 000 the CLI sketch showed: four legs at 10 000 would
     be a minute of generation for a number that is stable at a fifth of it. `--events` overrides.
  2. A refused leg carries `hep-run`'s own first line as its reason and the hint separately, so the
     report reads as a sentence rather than an exit code. The recommendation quotes it rather than
     summarising it to "it did not work".
  3. The replay leg is **reported but never used by `recommend`**: it answers a different question
     (is replay worth the disk?), whose answer depends on how often the analysis will change — which
     a benchmark cannot know. `--no-replay` skips it.
  4. Results are cached in `output/scratch/bench/`, keyed by project, point **and machine** — a
     number measured elsewhere is not a number about this machine — and `--refresh` re-measures. The
     cache is only used when the event count matches.
  5. Nothing is written into `results/`: a benchmark is not a result (09 §3), and there is a test
     that asserts it.
