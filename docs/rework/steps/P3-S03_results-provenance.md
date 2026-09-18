# P3-S03 — Results layout, skip rule and provenance

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P3 — Supervision, results layout, terminal |
| Depends on | [P3-S01](P3-S01_decide-serial-and-legacy-results.md), [P1-S04](P1-S04_identity-seeds-hash.md) |
| Blocks | [P3-S05](P3-S05_hep-run-command.md), [P4-S01](P4-S01_plot-pipeline.md), [P5-S02](P5-S02_store-source-replay.md) |
| Effort | 0.75 d |
| Findings / decisions | 00/B3, B18; 07 §1–2 |
| Updated | 2026-09-18 |

## Goal

Point/group directories, study manifests, the name+hash+complete skip rule, partial handling and full provenance (JSON + YODA annotations) are implemented and redirectable via `HEKIT_RESULTS`.

## Context

- Decision Q3/Q4 from P3-S01.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Record/Meta.hh:25-110,243-299` | field list (git, host, compiler, file hashes) | port |
| `tools/rivpyth_common.py:755-800` | path resolution | replace (repo-root based) |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/results/{layout,manifest,skip}.py`, `hekit/prov/{provenance,stamp}.py`
- YODA annotations `HekitPoint/HekitHash/HekitGit` on `/_EVTCOUNT`
- orphan detection

**Out (non-goals)**

- Plotting

## Design notes

- All writes via tmp + rename.

## Tasks

- [x] Implement
- [x] Tests with tmp `HEKIT_RESULTS`

## Outputs

- `utils/python/hekit/{results,prov}/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Name collision | pytest: same name, different hash | error with `--rerun` hint |
| Partial | pytest: `analysis.partial.yoda` present | point reruns |
| Annotations | pytest: stamp then `yoda.read` | keys present |
| CWD independence | run from `/` | same layout |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — implemented `hekit/results/{layout,skip,manifest}.py` and
  `hekit/prov/{provenance,stamp}.py` (≈720 lines) with 33 tests (1.0 s). Suite: 432 Python, 11/11 ctest.

  **Verification, every row measured**

  | Row | Result |
  |---|---|
  | Name collision (same name, different hash) | `State.MISMATCH`, **not** rerun, message names both hashes and the hint says `--rerun` or a new `[run].name` |
  | Partial (`analysis.partial.yoda` present) | `State.PARTIAL` → the point reruns; a summary saying `stopped` also wins over a final-named YODA |
  | Annotations | `HekitPoint`, `HekitHash`, `HekitGit` readable back off `/_EVTCOUNT` after a stamp, with the histograms intact |
  | CWD independence | the same layout from `/` and from a temporary directory (run as two subprocesses, compared) |

  **What went in**

  - **`Layout`** — `points/<group>/`, `studies/[NN_]<study>[_<label>]/`, `legacy/`, plus `logs/`,
    `pages()` and `orphans()`. D-Q3's serial is implemented here: one series across all studies (as
    `01_`…`04_` were), allocated by `mkdir` in a loop rather than by a scan, so two `hep run`s starting
    together cannot both take `01`. `[run].serial = false` drops it. A **point** path never carries a
    serial.
  - **`skip`** — the three-part rule (name, hash, complete). 00/B3 is the reason it exists: the old
    `skip_existing` meant "a file with the final name is there", so a killed run was skipped for ever
    and a changed card was silently honoured with the old physics.
  - **`manifest`** — a study run's selection, points **by reference** (path + hash, never a copy),
    pages, CLI, label and serial. Paths are stored relative to the results root so a study can be
    replotted after it moves to another machine.
  - **`prov.provenance`** — folds `run.summary.json` into git state, tool versions, card hashes,
    plugin `.so` hashes, PDF sets and output hashes. Every field degrades to "unknown"; a run never
    fails because provenance could not be gathered.
  - **`prov.stamp`** — `HekitPoint`/`HekitHash`/`HekitGit` onto `/_EVTCOUNT` (and `/RAW/_EVTCOUNT`),
    so a YODA that leaves its directory still identifies itself.
  - **`[run].serial`** added to the schema (default on) and the committed
    `docs/rework/reference/config.md` regenerated.

  **Deviations and notes**

  1. **The serial is allocated by `mkdir`, not by a scan.** Scanning and then creating is a race;
     `mkdir` failing with `FileExistsError` is the only reliable "somebody took it".
  2. `write_atomic` names its temporary `run.summary.tmp.json`, not `run.summary.json.tmp` — the same
     rule as the YODA writer, for the same reason (a suffix-driven reader must still be able to open
     the temporary if anyone ever looks at one).
  3. **A package must not re-export a function under one of its module names.** `hekit.prov` exported
     `stamp` (the function), which shadowed `hekit.prov.stamp` (the module) for
     `from hekit.prov import stamp`; the module is exported and the function reached as
     `stamp.stamp()`. Caught by the tests.
  4. Provenance records an analysis plugin's **`.so` digest**, not just its name: a plugin rebuilt with
     different cuts has the same name and a different digest, and that is the difference between two
     results that look comparable and two that are.
  5. The locale save/restore around every YODA read is carried over from 00/B29 — YODA's reader sets
     `LC_ALL` to `C` and does not put it back, which breaks the next non-ASCII write in the process.
     There is a test for exactly that.
  6. `hekit/results/` is a new package; the step's `hekit/results/{layout,manifest,skip}.py` and
     `hekit/prov/{provenance,stamp}.py` are exactly what was written, with `__init__` exports.
