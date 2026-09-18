# P2-S05 — Serial Rivet sink and atomic results writer

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P2 — C++ core, CMake, hep-run v1 |
| Depends on | [P2-S04](P2-S04_source-run-loop.md) |
| Blocks | [P2-S06](P2-S06_equivalence-gate.md), [P3-S05](P3-S05_hep-run-command.md), [P4-S05](P4-S05_photo-eic-reentrant.md), [P5-S01](P5-S01_store-writer.md) |
| Effort | 0.75 d |
| Findings / decisions | 00/B3, B21; F8; D22 |
| Updated | 2026-09-18 |

## Goal

`hep-run` writes `analysis.yoda` normalised to the merged σ; stopped runs write only `analysis.partial.yoda`; periodic dumps only for re-entrant analyses; a run summary feeds provenance.

## Context

- 05 §5 (Rivet), 07 §1–2.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Record/Recording.hh:204-231` | tmp + atomic rename | adapt |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `Sink::Rivet` (serial): analyses + options, check_beams, weights policy, `setCrossSection(σ, err, true)`, finalize, `getYodaAOs()`
- `Results::Writer`: `.tmp` → rename; partial naming; `analysis.dump.yoda` via `setFinalizePeriod` for re-entrant analyses only; `run.summary.json`

**Out (non-goals)**

- Module objects (P8-S01)
- sharded Rivet (P6-S01)

## Design notes

- Missing analysis is detected before generation (load analyses right after `init()`).

## Tasks

- [x] Implement
- [x] Tests

## Outputs

- `utils/Sink/Rivet.hh`, `utils/Results*`
- `tests/cpp/rivet_*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Missing analysis | spec with `NOPE_2099_I1` | exit 1 before any event |
| σ | python `yoda.read` of `/_XSEC` | = merged sigmaGen × 1e9 pb |
| Partial | SIGINT mid-run | only `analysis.partial.yoda` exists |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — implemented `Sink::Rivet` (206 lines), `Results::{Writer,Summary}` (203) and the facade;
  `hep-run` now builds its sinks from `[[sink]]` instead of always counting. Rivet runs **in process**:
  the same `GenEvent` the legacy FIFO carried, without the FIFO (D4).

  **Verification, all rows measured** (200 events, 2 threads, run from `output/scratch/`):

  | Row | Result |
  |---|---|
  | analysis `NOPE_2099_I1` | exit 1 before any event, under `--check` *and* a full run; message names `RIVET_ANALYSIS_PATH` and the configured paths; no YODA written |
  | σ in the YODA | `/_XSEC = 7.081873e+04 ± 2.212236e+03` pb, exactly the merged σ of the run (`xsec_pb = 70818.73351 ± 2212.236001`); `/_EVTCOUNT = 200` |
  | SIGINT mid-run | exit 6, directory holds `analysis.partial.yoda` and `run.summary.json` only — no `analysis.yoda`, no `.tmp` |

  A finished run writes `analysis.yoda` (35 KB, 17 `photo_eic` histograms + `/_XSEC` + `/_EVTCOUNT`) and
  `run.summary.json` with the counts, the seeds read back from the instances, σ ± err, and the Pythia
  warning counts (2 distinct messages in this run).

  **Tests:** ctest `results_writer` (naming, atomic write, stale-file removal in both directions, a
  failed write leaving nothing, the summary's fields) and `tests/python/run/test_rivet_sink.py`,
  13 cases against the real binary — including the one that matters for 03 §4: `--study radius` puts
  `photo_eic:R=0.4`, `:R=0.7` and `:R=1.0` in **one** YODA from **one** generation, with a single
  `/_EVTCOUNT`. Suite: 10/10 ctest, 372 Python.

  **Deviations and decisions**

  1. **The plan was pointing Rivet at the wrong directory.** `analysis_search_paths` listed the source
     `analyses/<project>` but not `build/analyses/<project>`, where `rivet-build` actually puts
     `Rivet_photo_eic.so` — so the very first real run could not find its analysis. Added
     `hekit.env.paths.build_root()` (honouring `HEKIT_BUILD`) and put the build tree first.
  2. **A missing analysis had to be caught by hand.** `AnalysisHandler::addAnalysis` only *warns* on an
     unknown name, so the sink resolves each name through `AnalysisLoader::getAnalysis` first and then
     re-checks `analysisNames().size()`, which also catches a name Rivet drops over a bad option value.
  3. **New `Sink::Sink::prepare()` hook**, called by `Run::Loop::prepare()` after the generator's
     `init()` and before any event. This is what makes the missing-analysis check work under `--check`
     — the step only asked for "before any event", and `--check` is strictly better.
  4. `dump_every` is **refused with a warning** rather than honoured for a non-re-entrant analysis
     (Rivet 4.1.3 skips `finalize` in a dump, `AnalysisHandler.cc:700-705`), so no unscaled file is ever
     written. `photo_eic` is still `Reentrant: false`; P4-S05 changes that, and the test will then need
     the opposite case.
  5. **The temporary name keeps the extension**: `analysis.tmp.yoda`, not `analysis.yoda.tmp`. YODA
     identifies its format from the suffix and refuses the latter outright — the same trap as the
     legacy partial file in P0-S03.
  6. **"Never both names"** is enforced actively: writing the partial deletes a stale `analysis.yoda`
     from an earlier attempt and vice versa, so a rerun that stops early cannot leave last week's
     result sitting next to today's partial.
  7. A run that analysed **no** events writes no YODA at all (with a warning) instead of an empty one:
     `hep` reads a missing output as "not run", which is the truth, whereas an empty YODA would be
     taken for a result.
  8. An unknown sink kind is exit 1, not a skip — a silently dropped store or module would look like a
     successful run that produced nothing.
  9. `RunRecord` grew the fields the summary needs (`events_requested`, `mode`, `seed`, `seeds`,
     `warnings`); `Run::Result` grew `summary_path`.
  10. Rivet's own warning counts are not in the summary yet — they need a Rivet log handler, which
      belongs with log capture in P3. Only Pythia's are recorded, and the field is a map so adding
      `"rivet"` later changes nothing else.
