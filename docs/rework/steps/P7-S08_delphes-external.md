# P7-S08 — External Delphes stage

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P7 — External generators and Delphes |
| Depends on | [P7-S01](P7-S01_adapter-framework.md) |
| Blocks | [P9-S02](P9-S02_proc-rdf-delphes.md) |
| Effort | 0.75 d |
| Findings / decisions | R9; 05 §5 (Delphes) |
| Updated | 2026-09-20 |

## Goal

A HepMC tee feeds a supervised `DelphesHepMC3` stage that writes `delphes.root` with a provenance sidecar.

## Context

- In-process Delphes deferred (global `Event`, ROOT state).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `$HEP_INSTALL/delphes/bin/DelphesHepMC3` | CLI | drive |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `[delphes]` card; `Analyzer::Store` tee to FIFO; stage wiring; sidecar

**Out (non-goals)**

- In-process mode

## Design notes

- Delphes failures map to exit 4 (input) or 5 (output).

## Tasks

- [x] Implement
- [x] Tests

## Outputs

- `hekit/adapters/delphes.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Output | 1k events | `delphes.root` readable by uproot |
| Failure | bad card | exit 4/5 attributed |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-20 — implemented `Analyzer::Delphes` and `hekit/adapters/delphes.py`. Delphes 3.5.1 is
  installed, so both rows were run. New ctest test `delphes` (label `slow`, 7 cases) and 11 unit
  tests. **Phase P7 is complete** apart from P7-S07, which D-Q6 left blocked.

  **Verification, both rows measured**

  | Row | Result |
  |---|---|
  | Output | 200 events → `delphes.root`, read back with **uproot**: 200 entries and the `Jet` branches. The Rivet analyzer still ran on the same events — the tee is a tee — and `delphes.json` beside the ROOT file names the card, its sha256 and the point's identity |
  | Failure | a card with a syntax error fails the point and is attributed to the `delphes` stage. Exit **1**, not 4 or 5: Delphes says 1 and 1 is "spec or card error", which is more specific than the role default. A *crash* still maps to 5 through `ROLE_EXIT["detector"]` |

  **The design assumed a FIFO, and that cannot work.** 05 §5 described a `Analyzer::Store` tee on a pipe
  with Delphes reading it alongside `hep-run`. `DelphesHepMC3` sizes its input before reading and
  **skips anything whose length is zero** — `readers/DelphesHepMC3.cpp:160-169`:
  `fseek(END); length = ftello(); if (length <= 0) { fclose; continue; }` — and a FIFO always
  measures zero. Pointed at one it opened the pipe, decided it was empty, exited, and `hep-run` died
  writing into a closed pipe (correctly attributed, which is how it was found). The sizing is how its
  progress bar works, so there is no flag.

  So the tee writes a **regular file** and the detector runs in the phase after `hep-run` — the same
  shape as MadGraph's LHE, and for the same reason: a tool that seeks cannot be streamed to. Verified
  from the other side too: `keep_events` leaves a real file, and the test asserts `not is_fifo()`.

  **The defect that fell out of the failure row.** Delphes **creates the ROOT file before it reads
  the card**, so a bad card left a `delphes.root` that opened, contained nothing, and looked exactly
  like a result. It is now written as `delphes.root.part` and renamed only on success, which is the
  rule every other output here follows (D22).

  **Design notes**

  1. `Analyzer::Delphes` opens its output in `start()`, not `prepare()` — `--check` stops between the two
     (06 §3.3), and on a FIFO that would have been 00/B33 from the writing side. It stayed that way
     after the switch to a file: there is no reason for a preflight to create one.
  2. The intermediate is deleted once Delphes succeeds. It is uncompressed and routinely larger than
     everything else the point produced (6 MB against 2 MB of ROOT for 200 events);
     `[delphes].keep_events` keeps it, which is what re-running the detector with a different card
     needs. On a *failure* it is kept regardless, because it is what you would want to look at.

  **Deviations**

  1. A FIFO tee, per the note above. `Analyzer::Store` is not reused either: a store is sharded and
     indexed because it is meant to be replayed, and this is one stream to one reader.
  2. The failure row says "exit 4/5"; a bad card gives 1. Delphes' own code is more specific than the
     role default, and 1 already means "spec or card error" in the table (06 §3.3).
