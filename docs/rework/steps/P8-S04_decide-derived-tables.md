# P8-S04 — Decide the derived-tables format (deferred)

| Field | Value |
|---|---|
| Status | done |
| Kind | decision |
| Phase | P8 — Modules, YODA results, Phys, ML |
| Depends on | [P8-S01](P8-S01_module-sink-yoda.md) |
| Blocks | — |
| Effort | 0.1 d |
| Findings / decisions | D23; Q10 |
| Updated | 2026-09-20 |

## Goal

The derived per-candidate table question is recorded with options, criteria and a revisit trigger.

## Context

- Deferred by user decision.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| 12 §5, 05 §5 | context | read |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- decision record only

**Out (non-goals)**

- Implementation

## Decision record — D-DERIVED

- **Question:** How should per-candidate / ML-feature tables be produced and stored?

- **Why it is open at all.** `Results` books YODA, and a YODA object is a *histogram*: it keeps sums
  in bins, not rows. Nothing in the pipeline can currently write "one line per jet with its
  features", which is the shape every training set has. 05 §6 gives a module inference
  (`ML::OnnxModel`) but no way to export what a model would be trained *on*, and that asymmetry is
  deliberate — D14 says results are YODA, so a second row-shaped output is a new format decision
  rather than an implementation detail.

- **Options, with what each would actually cost here** (measured 2026-09-20, this machine):

  | Option | New dependencies | Written by | Read back by | Note |
  |---|---|---|---|---|
  | Python replay of the store → Parquet | **pyarrow or fastparquet — neither installed**; `pandas.to_parquet` raises `ImportError: Unable to find a usable engine` | `hekit`, offline | pandas, polars, torch, sklearn | Needs no event-loop change at all: P5-S03 measured replay as **exact**, so a table can be produced after the fact from a store that already exists |
  | C++ module writing Parquet/Arrow | **Arrow C++ — not installed** | `hep-run`, in the event loop | as above | Puts a new library inside the event loop, which D15 keeps deliberately thin |
  | RNTuple (derived tables only) | **none** — ROOT 6.40.04 ships `RNTupleWriter/Reader/Model.hxx`, and uproot 5.7.6 reads RNTuple (`uproot.models.RNTuple`) | ROOT, offline or in a module | ROOT, uproot → numpy/pandas | The only option that works today with nothing new installed, and readable from both languages |
  | YODA only (no tables) | none | — | — | The status quo: training data would be produced ad hoc outside the toolkit |

- **Criteria:**
  - **ML tooling fit** — what a training script can open without ceremony. sklearn 1.9.0, pandas
    3.0.5, numpy 2.5.2, uproot 5.7.6 and awkward 2.13.0 are installed; torch is not. Parquet is the
    lingua franca, but nothing here can write it yet.
  - **Dependencies** — 01 N5's rule is that a component is optional and the build works without it.
    Two of the four options fail that today without an install.
  - **Consistency with D13–D15** — D13 keeps events in HepMC3 shards, D14 keeps results in YODA, and
    D15 keeps ROOT strictly on the processing side with `hep-run` not linking it. A derived table is
    neither an event nor a result, so it does not contradict D13 or D14; but writing one *from the
    event loop* would contradict D15, which is the sharpest thing the criteria say.

- **Evidence.** The three facts that were not knowable when this was first deferred:
  1. **Replay is exact** (P5-S03: a replayed store gives a YODA identical to the generation's,
     1004 numbers, χ² = 0). So the "produce tables offline from the store" family costs *nothing* in
     the event loop and can be added later without touching `hep-run` — which is what makes
     deferring cheap rather than merely postponed.
  2. **Parquet is not currently writable here** (no pyarrow, no fastparquet), and **Arrow C++ is not
     installed**; **RNTuple is fully available** in ROOT 6.40.04 and readable from uproot.
  3. **Features already have a schema.** P8-S03's `ML::Features` is an ordered, named list with
     width checked against the model. Whatever format is chosen, the column names and their order
     are already expressed in one place, so this decision is about the *container*, not about
     agreeing what the columns are.

- **Decision:** **Deferred.** Trigger: the first ML training dataset — that is, the first time
  someone needs rows rather than histograms. Not revisited before then.

- **Consequences now:** none. `hep-run` links no table library, `Results` stays YODA-only (D14), and
  12 §5 continues to list per-candidate tables as out of scope. The cost of deferring is bounded by
  evidence (1): whatever is decided can be built against stores that already exist.

- **What would change the answer.** If the training work turns out to be in Python (the installed
  stack suggests it would be), evidence (1) and (2) together point at *replay → table*, and the
  container question reduces to "Parquet with a new dependency, or RNTuple with none". If instead a
  model has to be fed inside the event loop, D15 argues against the C++/Arrow option and the
  question becomes a different one. Recording that here so the next reader does not restart from the
  four bare options.

- **Docs to update:** 10_Roadmap.md D23, steps/README.md decision register, 12 §5.

## Tasks

- [x] Record

## Outputs

- decision record D-DERIVED

## Verification

| Check | Command | Expected | Measured |
|---|---|---|---|
| Recorded | Decision record | status deferred with trigger | recorded above with options costed, criteria, evidence and a revisit trigger; register rows in 10 §D23, 10 §Q10 and steps/README all say deferred |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

n/a.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated (10 D23 + Q10, steps/README register, 12 §5)
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-20 — **done.** The decision is unchanged and was not mine to revisit: **deferred**, trigger
  the first ML training dataset. What this step added is the half that was a placeholder — the
  **Evidence**, which P5-S03, P8-S01 and P8-S03 have since made answerable.

  Three measurements, all on this machine today:

  - **Parquet cannot be written here at all.** Neither pyarrow nor fastparquet is installed, and
    `pandas.to_parquet` raises `ImportError: Unable to find a usable engine`. Arrow C++ is absent
    too. So *both* Parquet options carry a new dependency, which 01 N5 makes a real cost rather than
    a detail.
  - **RNTuple is free.** ROOT 6.40.04 ships `RNTupleWriter/Reader/Model.hxx` and uproot 5.7.6 reads
    RNTuple, so it is the only option on the list that works today with nothing new installed and is
    readable from both C++ and Python.
  - **Deferring is cheap, and now demonstrably so.** P5-S03 measured replay as exact, so any
    offline table can be built later from stores that already exist, without touching `hep-run`.
    That is the fact that turns "deferred" from a postponement into a bounded one.

  Also written down: **D15 is the sharpest of the three criteria.** A derived table is neither an
  event (D13) nor a result (D14), so it contradicts neither — but writing one *from the event loop*
  would contradict D15's "`hep-run` doesn't link ROOT", which rules on the C++/Arrow option without
  needing the trigger to fire. And P8-S03's `ML::Features` already fixes the column names and their
  order, so what is left open is the container, not the schema.

  No code, no new dependency, nothing to roll back.
