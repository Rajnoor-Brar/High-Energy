# P0-S05 — Hotfix the physics-relevant defects in the legacy tools

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P0 — Baseline, hygiene, legacy freeze |
| Depends on | [P0-S04](P0-S04_golden-fixtures.md) |
| Blocks | — |
| Effort | 0.5 d |
| Findings / decisions | 00/B2, B3, B4, B5, B10, B13, B20, B21, B23; records B11, B12, B27 |
| Updated | 2026-09-18 |

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

- [x] Patch `tools/rivpyth` (B3, B20)
- [x] Patch `tools/rivpyth_common.py` (B2 guard)
- [x] Patch `generator.cc` (B21); rebuild
- [x] Edit configs/comments (B2 seed_step, B4, B5, B10, B13, B23)
- [x] Re-capture fixtures; write `EXPECTED_DELTAS.md`
- [x] Scratch tests below

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

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **done.**

  **Design corrections (the step as written would have broken every run):**
  - **B21.** `nWritten != nGenerated` is the normal case, not an error: `PythiaParallel::run()` counts `next()` attempts and calls the callback only on success (P0-S04 Log). Implemented instead: `toHepMC.output().failed()` is checked right after opening (so an unwritable path fails before generating), `writeNextEvent` failures are counted (first five warn), and either condition exits **4**.
  - **B3.** Likewise, Rivet's count cannot be compared with `event_count`. Implemented: `rivpyth` relays the generator's stdout through a pipe, keeps the counts from its summary line, and after both processes exit 0 compares Rivet's `/RAW/_EVTCOUNT` with the *written* count; only then does it `os.replace` the partial file onto the final name.
  - **Partial suffix.** `X.yoda.part` is impossible: YODA picks its format from the extension and raises "Format cannot be identified from string". The partial file is **`X.part.yoda`**.

  **New findings while implementing (added to 00_Audit §4.1):**
  - **00/B29.** `yoda.read()` resets `LC_ALL` to `C` and never restores it. The locale default encoding then becomes ASCII, and the next `write_text()` of a point cmnd fails on the em dash in its header — this broke the mini run at point 2 as soon as `rivpyth` started reading YODA. Fixed by restoring the locale around the read in `analysed_events` **and** naming `encoding="utf-8"` in every text read/write of `rivpyth_common.py`, `tools/rivpyth` and `tests/golden/*.py`. Lesson for hekit (P1-S01): never rely on the locale default.
  - **00/B30.** Measured with this base cmnd (proton = beam A, photon from the lepton = beam B), Pythia 8.317, 400 events at 27x920: `Photon:ProcessType` 0 and 1 give **identical** events and σ = 74 261.7 pb, with every hard process a resolved-resolved HardQCD code (111-124); 2 **fails `init()`**; 3 initialises, switches MPI off ("unresolved photon") and still yields only HardQCD codes (σ differs ~1 %). So the direct contribution is unreachable with this card and the `process` study is currently a null comparison (two independent samples of the same physics). The catalogue notes in both configs now state this; enabling the direct contribution needs a separate card and is left as physics work. `Photon:ProcessType = 2` was removed from `zeus_validation.toml` (it would abort).

  **Applied:**
  | Finding | Change |
  |---|---|
  | B2 | `validate_config` rejects a base seed with `threads > 1` and `seed_step < threads` (skipped when a seed quantity is scanned or `[static.cmnd].seed` is set); both configs get `seed_step = 20` |
  | B3 | `.part.yoda` + count check + atomic rename; `skip_existing` (final name) reruns a partial point |
  | B4 | 27x920 label √s = 318.1 GeV (2·√(27.5 × 920)) |
  | B5 | `use_data = false` in `eic.toml`, with the reason in the file |
  | B10 | header, `use` comments, study descriptions, `min_entries`/`void_empty` comments corrected |
  | B13 | measured ProcessType notes in `eic.toml`, `zeus_validation.toml` and `photo_ep.cmnd` |
  | B20 | `supervise` returns both statuses (giving the survivor 10 s before stopping it); `first_failure` prefers a real error over a knock-on SIGPIPE/SIGTERM |
  | B21 | as corrected above |
  | B23 | `photo_ep.cmnd`: what overrides the run control, and the attempts-vs-written note |
  | B11 | no action (test bed, D-B11): the studies keep running e⁺ |
  | B12 | recorded in `eic.toml` ("NNLO" = NNPDF2.3 LO, "NNNLO" = NNPDF2.3 NLO); renamed with an alias map in P1-S06 |
  | B27 | recorded in the `pthatmin` study description: base `pTHatMin = 6` sits above jet `ETMIN = 5`, biasing the lowest-E_T jets; the study measures it |

  **Verification (scratch CWD `output/scratch/hotfix/`):**
  | Check | Result |
  |---|---|
  | Kill test (B3) | `kill -TERM` after 15 s left **only** `kill_27x920_ep_MSTW.part.yoda` (84 371 B) and no final `.yoda`. Rivet does finalize and write on SIGTERM, which is exactly why the old code produced a complete-looking result |
  | Rerun after the kill (B3) | with `skip_existing = true` the point was **not** skipped: it regenerated, renamed, and the final file holds `numEntries = 2000` with no `.part.yoda` left |
  | Bogus analysis (B20) | `rivpyth: rivet failed with status 1 (generator -15, rivet 1)`, exit 1, no output file — Rivet's status, not the generator's signal |
  | Unwritable output (B21) | `/proc/forbidden/x.hepmc` and `/root/denied.hepmc` both exit **4** with "could not open HepMC3 output", before generating |
  | Seed guard (B2) | `threads = 20, seed_step = 1` → `ConfigError`; `seed_step = 20` and `threads = 1` accepted |
  | Fixtures | recaptured; `pytest tests/golden -q` → **55 passed in 0.24 s** |
  | Physics unchanged | the mini-run YODAs are byte-identical to the P0-S04 capture: 5000/5000 and 5000/4999 events, σ = 71 422.16 and 72 994.84 pb |

  **Fixture deltas** are listed in `tests/golden/legacy_plan/EXPECTED_DELTAS.md`: point seeds (`seed + (n−1)·20`), the base-cmnd sha in 161 point cmnds, 38 27x920 legend strings, and zeus `cli_across_process` 3 → 2 points.

  **Note for the user:** the existing `results/PhotoProduction` files were produced with the old seeds (`seed_step = 1`), and file names do not encode the seed, so rerunning a study now produces statistically independent events under the same names. The inventory in `tests/golden/results_inventory.json` is the record; P3-S01 moves those files to `legacy/`.
