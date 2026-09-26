# P8-S01 — Module API, YODA results layer and module sink

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P8 — Modules, YODA results, Phys, ML |
| Depends on | [P6-S01](P6-S01_sharded-rivet.md), [P5-S01](P5-S01_store-writer.md) |
| Blocks | [P8-S03](P8-S03_onnx.md), [P8-S04](P8-S04_decide-derived-tables.md) |
| Effort | 1.5 d |
| Findings / decisions | D14; R10; utils defects: unscaled finals, empty checkpoints |
| Updated | 2026-09-20 |

## Goal

User C++ modules (dlopen'd) book YODA objects per worker; results are merged, scaled in `finalize`, and written into `analysis.yoda` next to Rivet's; hekit merges module objects for replicas.

## Context

- 05 §5 (Modules); 07 §3.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Record/{Cloning,Declaration,Type_Methods}.hh` | clone/merge, declare-time validation, enum keys | adapt to YODA |
| `legacy/configs/defaults/Limits.toml` | binning presets | optional |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `Module/{Types,Registry,Loader}`, `HEKIT_MODULE`
- `Results/{Booker,Worker,Merge}`
- `Sink::Modules`
- combined write
- `[[sinks.module]]`
- `hekit` replica merge for module objects
- `hep new module`; CMake `hekit_<name>` targets

**Out (non-goals)**

- Derived tables (S04)

## Design notes

- Scaling contract: raw weights in `process`; scaling only in `finalize` with σ and ΣW known.

## Tasks

- [x] Implement
- [x] Toy module
- [x] Tests

## Outputs

- C++ namespaces
- `modules/Examples/` toy
- tests

## Verification

| Check | Command | Expected |
|---|---|---|
| Exact totals | toy module at 1/4/20 threads | identical integrals |
| Scaling | scaled integral | = expected σ fraction |
| Dumps | periodic dump | non-empty |
| Plotting | `hep plot` / `rivet-mkhtml` | module histograms shown |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-20 — implemented `Module/{Types,Registry,Loader}`, `Results/{Booker,Worker,Merge}`,
  `Sink::Modules`, the toy module and the replica merge. New ctest tests `modules` (slow, 9 cases)
  and `results_objects` (32 checks), plus 12 unit tests for the merge.

  **Verification, every row measured**

  | Row | Result |
  |---|---|
  | Exact totals | serial and sharded give **identical** objects at 4 threads — 5 objects, every `sumW` equal to 1e-12 — and the same σ. (Read as *the merge is exact*: 1 vs 4 vs 20 threads are different **event sets** at a fixed seed (05 §3), so their integrals cannot be equal and equality there would mean something was wrong.) |
  | Scaling | the normalised `multiplicity` integrates to **71 632.737 pb** against a measured σ of **71 632.735 pb** — agreement to 3 × 10⁻⁸, which is floating-point summation. The counter is untouched at 4 000, and the profile is left alone because a mean must not be scaled |
  | Dumps | the periodic dump is written and non-empty (39 objects), and holds **no** module objects — see below |
  | Plotting | `hep plot --points` renders them: `ToyJets/{pt,eta,multiplicity,events,pt_vs_eta}.png` under the point's page |

  **The scaling contract is a type, not a rule to remember.** `Results::Worker` has `fill` and no
  `scale`; `Results::Final` has `scale` and no `fill`, and is only reachable from `finalize`, after
  the merge, with σ and Σw known. So "scaled during the run", "scaled twice" and "scaled by a σ that
  was not final yet" are not mistakes a module can make. `legacy/utils/Record` allowed all three and
  wrote unscaled finals as a result (00 §4.1).

  That is also why **module objects are absent from a periodic dump**. Mid-run they are unscaled, and
  a dump containing them would be a file that looks like a result and is not — exactly Record's
  defect. A *stopped* run is different: `finish()` still runs, so the merge and `finalize` happen and
  the objects reach `analysis.partial.yoda`.

  **`fill` merges, `set` does not** — the rule P6-S01 left for this step. Every object a module can
  book is fillable, which is what makes k workers' clones sum to what one worker would have had, and
  is why the exact-totals row is exact rather than close.

  **Design notes**

  1. **A module gets handles, not pointers.** There is one object *per worker*, so a module holding a
     pointer would be holding one of k clones and filling only that one. A handle is an index, so a
     fill costs an array lookup rather than a map lookup or a `dynamic_cast`.
  2. **Booking validates at declare time**: empty names, a `/` in a name, duplicates, zero bins and
     reversed edges. Two of those keep nothing at all and look fine until the plot.
  3. **One `analysis.yoda`.** `Sink::Rivet` gained `alsoWrite`, and `hep-run` hands it the module
     objects, so both land in one file under `/<module>/<name>` (07 §1) and `hep plot` and
     `rivet-mkhtml` treat them alike. With no Rivet sink in the run, the module sink writes the file
     itself rather than dropping the objects.
  4. **The library is named after its file** — `modules/<project>/ToyJets.cc` → `libhekit_ToyJets.so`
     → `[[sinks.module]].name = "ToyJets"` — so the config and the build cannot drift, and
     `HEKIT_MODULE` uses the same name.
  5. **The loader never `dlclose`s.** A module's objects carry a vtable that lives in that library,
     and unloading it underneath them is a crash that names nobody.

  **Deviations**

  1. The replica merge (07 §3) is implemented as `hekit.results.merge`, and it **averages** rather
     than adds: a module's objects are already in cross-section units, so two replicas of one point
     combine as a Σw-weighted mean and adding them would give 2σ. An object a module deliberately
     left unscaled is the case the rule gets wrong, so the caller names those and they are summed.
     The surrounding replica-merge command does not exist yet — `[plot].merge = "yodamerge"` is in
     the schema and validated but unimplemented — so this is the half that can be built and tested
     now, and the other half has no owning step.
  2. `hep new module` is in this step's scope list but the CLI maps `hep new` to **P10-S01**; it is
     left there rather than split across two steps.
  3. Σw is taken from the summary's event count, which is exact for the unweighted runs this project
     makes. A weighted generator would want Σw recorded in `run.summary.json` first.
