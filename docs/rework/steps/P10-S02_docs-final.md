# P10-S02 — Final documentation pass

| Field | Value |
|---|---|
| Status | done |
| Kind | docs |
| Phase | P10 — Cleanup, docs, release |
| Depends on | [P10-S01](P10-S01_cleanup-housekeeping.md) |
| Blocks | [P10-S03](P10-S03_portability-release.md) |
| Effort | 0.5 d |
| Findings / decisions | 00 §4.7 |
| Updated | 2026-09-20 |

## Goal

Docs describe the implemented system: user guide, generated config reference, new `docs/MAP.md`, rework docs marked implemented with deviations, `bots/` updated (with approval), step index closed.

## Context

- Legacy docs stay in `legacy/docs/`.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `docs/rework/*` | design | update status |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- docs only

**Out (non-goals)**

- Code

## Design notes

- Every documented command must appear in `hep --help` (test).

## Tasks

- [x] Write guide
- [x] Regenerate reference
- [x] New MAP
- [x] Mark rework docs
- [x] Propose bots/ edits
- [x] Close index

## Outputs

- `docs/GUIDE.md` (new), `docs/MAP.md` (new), `docs/README.md` rewritten
- `docs/rework/README.md` marked **Implemented**, with a table of the eleven places the design was wrong
- `docs/rework/steps/README.md`: phase table closed, change log entry
- `bots/BOT.md` layout table refreshed (`sources/` and `tools/` are gone; `analyses/`, `modules/`, `cmake/` added)
- `tests/python/env/test_docs.py` (7) — both Verification rows, as tests

## Verification

| Check | Command | Expected | Measured |
|---|---|---|---|
| Links | `test_every_relative_link_resolves` | 0 broken | **0 broken** over 504 relative links in 76 documents, 7 of them with `#anchors` checked against the target's headings. Proved to discriminate by adding a link to a missing file and watching it fail |
| Commands | `test_every_command_is_documented` + the converse | all present | all **19** commands documented; and no document mentions a `hep <word>` that does not exist — the second direction matters as much, since it is what sends a reader to type something that fails |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-20 — **done.** Two new documents, three rewritten, and both rows turned into tests so the
  docs cannot rot silently.

  **`docs/GUIDE.md`** is the missing document: how to get work done, in the order a session actually
  happens — plan, run, proc, plot — with the things that surprise people given their own sections
  (why threads are sometimes not used, what a seed is derived from, what `hep clean` refuses to
  touch). It ends with a symptom-to-command table and the exit codes, because "it failed and I do
  not know what to look at" is the commonest question a toolkit has to answer.

  **`docs/MAP.md`** is where things live: the two halves and the narrow contract between them, the
  C++ layering, the `hekit` packages, the shape of a results directory, and a "finding your way in"
  table. It names the two invariants a reader should know before opening the code — the scaling
  contract, and that concurrency is a property of the sink.

  **The design is now a record, not a proposal.** `rework/README.md` says so, and carries a table of
  **eleven places where building it changed it** — jet clustering that cannot be sharded, a sink
  exception that would have called `std::terminate`, Delphes that cannot read a FIFO, Whizard's
  missing photon structure function, ROOT dropped from the physics layer, a Δφ that does not
  terminate, a plugin convention that had never been run, a module sink that cannot always shard, a
  χ² that is not a general minimisation, a derived histogram that must not be a `Histo1D`, and
  derived tables deferred with evidence. A reader of the design should not have to find those one at
  a time.

  **Both rows are tests, and both were checked against a deliberate break.** The link test resolves
  every relative link in `docs/**` *including anchors*, against the headings of the file linked to —
  a link to a renamed section is as broken as one to a missing file and much harder to notice. 504
  links across 76 documents, 0 broken. The command test runs in **both directions**: every command
  is documented somewhere, and no document mentions a `hep <word>` that does not exist. The second
  is the one that protects a reader from typing something that fails.

  **Deviations.** `legacy/` is excluded from the link check — it is frozen by design and describes
  code that no longer runs, so holding it to the current system's links would be asking it to lie.
  A test also asserts the guide and the map never link *into* `legacy/` for current behaviour.
  `bots/BOT.md`'s layout table was stale (it still listed `sources/` and `tools/`, both gone, and
  omitted `analyses/`, `modules/` and `cmake/`); refreshed under the standing `bots/` approval.
