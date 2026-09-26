# P3-S01 — Decide the serial label and the fate of legacy results

| Field | Value |
|---|---|
| Status | done |
| Kind | decision |
| Phase | P3 — Supervision, results layout, terminal |
| Depends on | [P0-S04](P0-S04_golden-fixtures.md) |
| Blocks | [P3-S03](P3-S03_results-provenance.md) |
| Effort | 0.1 d |
| Findings / decisions | Q3, Q4; 00 §4.1 (results series 01–04, serial drift) |
| Updated | 2026-09-18 |

## Goal

Q3 and Q4 are decided and recorded before the results layout is implemented (P3-S03).

## Context

- 07 §1; inventory `legacy/results/PhotoProduction.inventory.json` (P0-S04/S06).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| results inventory | series, partial flags, serials | evidence |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- Decision records; if approved, a plain `mv results/PhotoProduction/* results/PhotoProduction/legacy/` (gitignored dir) with a README

**Out (non-goals)**

- Converting legacy YODAs

## Decision record

- **Question:** Q3: keep a numeric serial in names/paths? Q4: import legacy results into the new layout, or freeze them?
- **Options:**
  - Q3-A (proposed): no serial in paths; optional free-text `run.label` in manifests
  - Q3-B: keep `NN_` prefix
  - Q4-A (proposed): no import; move to `results/PhotoProduction/legacy/` + README; `[plot].extra` overlays by path
  - Q4-B: `hep import-legacy` converting to point dirs
- **Criteria:**
  - legacy hashes cannot be rebuilt (seed/serial drift, reconstructed cmnds, possible partial files)
  - effort
  - risk of mixing untrusted outputs with new ones
- **Evidence** (from `legacy/results/PhotoProduction.inventory.json`, P0-S06):
  - 25 YODA files, 7 plot directories, 541 files, 16.0 MB; **all 25 readable**, none named `partial`/`tmp`.
  - Serials do not identify physics: `01` → `eic28.toml` (one entry unknown, `"?"`), while `02`, `03`
    **and** `04` all come from the same `eic.toml`. The serial records when a run happened.
  - The analysis name drifted across the archive: `photo_5x41` (9 files), `photo_eic` (15),
    `photo_10x100` (1) — so their YODA paths do not match what the current plugin writes.
  - Event counts are accidental: 977 047 … 999 914, because the old generator counted `next()`
    *attempts* (00/B21). A 1 000 000-event rerun cannot reproduce them.
  - 5 of the 7 plot directories have an `index.html` mentioning `.tmp` files (the non-atomic writer,
    00/B3), so a page's inputs were not what its final names say.
- **Decision** (user sign-off 2026-09-18):
  - **D-Q3 — keep the numeric serial, as an option, on the study directory only.** The user asked for
    `NN` serials back with an enable switch ("pre-label/post-label, whatever you see fit"), and left the
    shape to me. Recorded shape: `results/<project>/studies/[NN_]<study>[_<label>]/`, prefix form,
    controlled by `[run].serial` (default **on**), with the existing free-text `[run].label` appended
    when set. A **point** path never carries a serial: points are keyed by name + hash so that the same
    physics is shared between studies and the skip rule can recognise it — putting a serial there is
    exactly the drift the audit recorded (the same physics at four paths). Implemented in P3-S03.
  - **D-Q4 — no import; move and freeze** (Q4-A), approved by the user.
- **Consequences:** 07 §1 table; P3-S03 layout; P4-S02 `[plot].extra`
- **Docs to update:** 07_Outputs.md §1, 10_Roadmap.md §5, steps/README.md decision register

## Tasks

- [x] Summarise inventory
- [x] Ask user
- [x] Record
- [x] Move legacy results if approved

## Outputs

- decision records D-Q3, D-Q4
- `results/PhotoProduction/legacy/README.md` (if moved)

## Verification

| Check | Command | Expected |
|---|---|---|
| Sign-off recorded | Decision record | filled |
| Move complete | `find results/PhotoProduction/legacy -type f \| wc -l` vs inventory | equal (if moved) |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

`mv` back (gitignored files).

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — both questions decided with the user; the Decision record above holds the evidence and
  the outcome.

  **The move is done.** `results/PhotoProduction/*` → `results/PhotoProduction/legacy/`, by
  `shutil.move` with the file list compared before and after, and then every YODA re-hashed:

  | Check | Result |
  |---|---|
  | files before the move | 541 |
  | files under `legacy/` after | 541, identical relative paths |
  | left outside `legacy/` | nothing but `legacy/` itself |
  | YODA checksums vs the P0-S06 inventory | **25 of 25 match** |

  `results/PhotoProduction/legacy/README.md` travels with them: where they came from, why they are
  frozen (drifted analysis names, attempt-based event counts, unknown inputs for serial 01, `.tmp`
  references in 5 of 7 plot pages), what they may still be used for (`[plot].extra` overlays, direct
  YODA reading) and what they must not be used for (merging with new results, or a comparison claiming
  a shared configuration).

  **Docs updated:** 07 §1 (the layout line and the "changes from today" table now describe the serial on
  the study directory), 10_Roadmap §2 (Q3 and Q4 marked answered), and the decision register in
  `steps/README.md` (D-Q3, D-Q4).

  **Deviation from the proposal.** The roadmap proposed *no* serial (Q3-A); the user chose to keep one.
  The recorded compromise keeps the user's serial while protecting what the new identity scheme needs:
  the serial labels a **run of a study**, not a result, so two studies that reach the same physics still
  share one point directory and one generation. If the shape does not suit in practice the user has said
  they will have it altered; `[run].serial = false` already gives the roadmap's original behaviour.
