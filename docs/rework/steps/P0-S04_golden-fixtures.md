# P0-S04 — Capture golden fixtures of the legacy workflow

| Field | Value |
|---|---|
| Status | done |
| Kind | test |
| Phase | P0 — Baseline, hygiene, legacy freeze |
| Depends on | [P0-S03](P0-S03_tools-into-repo.md) |
| Blocks | [P0-S05](P0-S05_legacy-hotfixes.md), [P0-S06](P0-S06_legacy-archive.md), [P2-S06](P2-S06_equivalence-gate.md), [P3-S01](P3-S01_decide-serial-and-legacy-results.md) |
| Effort | 0.5 d |
| Findings / decisions | 00 §4.1 golden fixture; 00/B16 inventory; plans/B1 |
| Updated | 2026-09-18 |

## Goal

Legacy behaviour is frozen as data before any fix: plan expansions for every study, a mini run with plot intermediates, and an inventory of existing results.

## Context

- Legacy tools resolve `results/`, `configs/`, `output/` relative to the CWD (00/B18), so they can run in a scratch CWD with symlinks — no code change needed.
- Scratch CWD: `output/scratch/legacy/` with symlinks `configs`, `output`, `datasets` → repo and a real `results/`.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth_common.py` | `read_config`, `apply_overrides`, `expand_points`, `execution_plan`, `group_pages`, `page_suffix`, `curve_legend` | import (pure functions) |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `tests/golden/**` (tracked)
- scratch runs
- read-only inventory

**Out (non-goals)**

- Any tool fix (P0-S05)

## Design notes

- (a) `tests/golden/capture_legacy.py`: for `eic.toml` (default + 10 studies) and `zeus_validation.toml` write `tests/golden/legacy_plan/<cfg>/<study>.json` (points: number, suffix, settings with origin, analysis, legend, page; pages: suffix, members, legends; plan paths relative; point-cmnd text).
- (b) `tests/golden/legacy_mini.toml`: 2 PDF points, 5k events, 1 thread, fixed seed; run `rivpyth`, `ydmrg`, `ydplt` in the scratch CWD; store YODAs, unified/voided intermediates and generated `.plot` overrides under `tests/golden/legacy_run/` (small files only).
- (c) Read-only inventory of `results/PhotoProduction` → `tests/golden/results_inventory.json` (path, bytes, sha256, `/_EVTCOUNT` numEntries/sumW, cmnd sha, serial); flags partial files and serial drift. (Moved to `legacy/results/` in P0-S06.)
- (d) `tests/golden/test_legacy_counts.py`: single 1; pdf 4 (1 page); energies 4 (1 page); energy_pdf 16 (4 pages); mpi 3; mpi_onoff 2; mpi_grid 6 (2 pages); pthatmin 4; process 2; radius 3 (analysis `photo_eic:R=1` for the last); zeus 4 (never run).

## Tasks

- [x] Create scratch CWD with symlinks
- [x] Write and run capture script
- [x] Run mini legacy workflow in scratch
- [x] Write inventory script and run it read-only
- [x] Write count tests

## Outputs

- `tests/golden/{capture_legacy.py,legacy_mini.toml,test_legacy_counts.py,results_inventory.json}`
- `tests/golden/legacy_plan/**`
- `tests/golden/legacy_run/**`

## Verification

| Check | Command | Expected |
|---|---|---|
| No writes to real dirs | `touch output/scratch/stamp` before; after: `find results configs -newer output/scratch/stamp \| wc -l` | 0 |
| Counts | `pytest tests/golden -q` | all pass |
| Mini run complete | `ls tests/golden/legacy_run/*.yoda` | 2 files with `/_EVTCOUNT` = 5000 |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Delete `tests/golden/` and the scratch dir.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **done.**
  - **Deviation — frozen inputs.** The fixtures are captured from copies in `tests/golden/inputs/PhotoProduction/` (`eic.toml`, `zeus_validation.toml`, `photo_ep.cmnd`), not from the live `configs/`, because the user edits the configs between sessions and every fixture test would then fail. `test_inputs_are_the_fixture_inputs` warns (does not fail) when the live files have drifted. Recapture: `capture_legacy.py inputs plan`.
  - **Deviation — mini CWD.** The mini run uses its own scratch CWD `output/scratch/legacy_mini/` whose `configs/PhotoProduction` holds symlinks to the frozen input and to `legacy_mini.toml`, so its point cmnds record stable relative paths. `output/scratch/legacy/` (symlinks `configs`, `output`, `datasets`, `sources`; own `results/`) was created in P0-S03 and is kept for tool runs.
  - **Deviation — extra cases.** Besides the default and the 10 studies, the capture also covers CLI selections (`cli_pin_beams`, `cli_single_pin`, `cli_across_overlay`, `cli_across_together`, `cli_couple_mismatch`) and for zeus `cli_across_process`: 18 cases in total. `capture_legacy.py` has subcommands `inputs`, `plan`, `mini`, `inventory`.
  - **Point/page counts** (frozen inputs): default 4/1, single 1/0, pdf 4/1, energies 4/1, energy_pdf 16/4, mpi 3/1, mpi_onoff 2/1, mpi_grid 6/2, pthatmin 4/1, process 2/1, radius 3/1 (`photo_eic:R=0.4|0.7|1`), zeus default 4/1. Matches the audit's fixture table.
  - **Mini run** (2 PDF points, 27x920 e⁺p, 5k events, 1 thread, seed 12345, ZEUS data overlay): 18 s wall, all three tools exit 0, 3 HTML pages of 17 plots each.

    | Point | attempts | written | Rivet numEntries | σ (pb) |
    |---|---|---|---|---|
    | MSTW | 5000 | 5000 | 5000 | 71 422 |
    | NNLO | 5000 | 4999 | 4999 | 72 995 |

  - **Verified fact, corrects the P0-S05 design (00/B3, 00/B21).** `PythiaParallel::run()` returns *attempts*: `eventsPerThread[i]` is incremented before the success check and the callback runs only on success (`PythiaParallel.cc:186-208`). So `Main:numberOfEvents` counts `next()` calls, not written events.
    - B21 as written ("exit 4 if `nWritten != nGenerated`") would fail **every** run. It must count write failures instead.
    - B3 as written ("`/_EVTCOUNT` numEntries == `event_count`") would likewise reject every run. It must compare Rivet's count with the generator's *written* count.
    - Observed `next()` failure rates (1M-event runs): 5x41 ≈ 2.1 %, 10x100 ≈ 0.23 %, 18x275 ≈ 0.04 %, 27x920 ≈ 0.01 %. Energy dependent, so no fixed tolerance works.
  - **Inventory** (`tests/golden/results_inventory.json`, read-only): 25 YODA files, 7 plot directories, 541 files, 15.96 MB. Flags: `cmnd_reconstructed` (4 files of series 01), `positional_name` + `no_cmnd` (`01_eic28_p01…p04`), `no_serial` + `no_cmnd` (`eic28.yoda`, `eic63.yoda`); no orphan cmnds, nothing unreadable, no sha duplicates. Each YODA carries `missing_fraction`; nothing exceeds 5 %, so no file is flagged `short` — the earlier 1 % rule wrongly flagged all 5x41 runs. 5 of the 7 `index.html` files reference `/tmp` paths (00/B19).
    - Serial drift is visible: serial `01` covers both `eic28.toml` runs and the four un-provenanced positional files; `02`/`03`/`04` are all `eic.toml`. Series 01 and 02 hold the same events (identical `numEntries`, e.g. 979 630 for MSTW) under different names, which also shows the runs reproduce for a fixed seed.
  - **Verification:**
    - `find results configs -newer output/scratch/stamp | wc -l` → **0**, before and after the runs.
    - `pytest tests/golden -q` → **36 passed in 0.09 s**.
    - `legacy_run/` holds both YODAs with `/RAW/_EVTCOUNT` equal to the written counts, plus the ydmrg and ydplt plot intermediates (voided YODAs, remapped ZEUS data, `auto_range.plot`, mkhtml argument lists): 496 KB.
  - The data overlay warnings (`data d01…d10 trimmed to [17, 47]`) are 00/B5 in action: the ZEUS reference shares histogram names with `photo_eic` but is a different observable. Captured as legacy behaviour; `use_data = false` follows in P0-S05.
