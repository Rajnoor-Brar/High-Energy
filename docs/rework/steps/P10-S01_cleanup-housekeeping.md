# P10-S01 — Remove transition shims; housekeeping commands

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P10 — Cleanup, docs, release |
| Depends on | [P4-S06](P4-S06_retire-legacy-tools.md) |
| Blocks | [P10-S02](P10-S02_docs-final.md) |
| Effort | 0.5 d |
| Findings / decisions | rule 1 (end state) |
| Updated | 2026-09-20 |

## Goal

No transitional code remains outside `legacy/`: v1 reading only inside `migrate`, no `.v2` names, `sources/` gone; `hep clean` and `hep new analysis|project` exist.

## Context

- 07 §6.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| — | — | — |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- shim removal
- renames
- `hep clean`
- `hep new analysis|project`

**Out (non-goals)**

- —

## Design notes

- `hep clean --dry-run` reports sizes before deleting anything.

## Tasks

- [x] Remove shims
- [x] Rename
- [x] Implement commands

## Outputs

- `utils/python/hekit/results/clean.py` + `hep clean`; `utils/python/hekit/env/scaffold.py` + `hep new`
- `tests/python/env/test_housekeeping.py` (17), and `test_skeleton.py` gains the end-state assertion
- 07 §6 and 08 §2 updated

## Verification

| Check | Command | Expected | Measured |
|---|---|---|---|
| Clean greps | the row as written, then the question it means | empty | **Not empty, and should not be** — see the Log. Replaced by an AST check (`test_no_executable_code_speaks_v1_outside_migrate`): **zero** executable references outside `config/migrate.py` and `config/validate.py`. Proved to discriminate by reintroducing a `raw.get("rivpyth", …)` and watching it fail. `NtupleSink`/`RNTuple`: zero anywhere in code. `sources/`: gone |
| Dry run | `hep clean --dry-run` | size report | per-category sizes, then the largest directories regardless of category; `1.0 MiB could be freed` on a real results tree |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated (07 §6, 08 §2)
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-20 — **done.** 17 new tests. The command tree of 08 §2 is now complete: no entry in
  `hekit.cli.COMMANDS` is a placeholder, and a test asserts that rather than skipping once it
  becomes true.

  **The grep row cannot pass, and making it pass would be a mistake.** Run as written it finds 345
  hits. In *code* it finds 24, and every one of them is one of three things:

  - **7 lines in `config/migrate.py`** — reading `[rivpyth]` out of a v1 file, which is precisely
    what this step's own Goal says is allowed ("v1 reading only inside `migrate`");
  - **1 line in `config/validate.py`** — a map of v1 section names used to *detect* an old file and
    answer "run `hep config migrate`" instead of a wall of unknown-key errors. That is the error
    path, not a shim, and deleting it makes the experience strictly worse;
  - **the rest are docstrings** recording where a function was ported from ("Ported from
    `rivpyth_common`'s `void_bins`…"). Deleting those to satisfy a grep would destroy the only
    record of why some of this code is shaped the way it is, and would not remove one line of
    transitional behaviour.

  So the row was replaced with the question it *means*: **is there executable code outside `migrate`
  that still speaks v1?** `test_no_executable_code_speaks_v1_outside_migrate` parses every module
  and inspects string literals and identifiers with docstrings excluded **by parsing** — the only
  way to tell "this code reads `[rivpyth]`" from "this comment says the old tool did". The answer is
  zero. It was proved to discriminate by appending a `raw.get("rivpyth", …)` to an unrelated module
  and watching it fail, then restoring.

  The other two clauses of the Goal hold outright: `sources/` does not exist, and `NtupleSink` and
  `RNTuple` — the storage design D13 rejected — appear nowhere in code. The `.v2` names that remain
  are `plan/spec_v2.json` (the *current* spec schema, version 2, which `hep-run` reads) and test
  fixtures named `.v2.toml`; neither is transitional.

  **`hep clean` is shaped by its second column, not its first.** 07 §6 lists what may be removed and
  then says YODA files, `fits.json` and provenance are never touched. So no category is on by
  default — a cleaner whose default is to delete is one you run once by accident — every removal
  asks unless `--yes`, and `--older-than` makes `--events` safe on a live tree. Two details worth
  keeping: removing a store **empties it but keeps `events.index.json`**, so a cleaned store can
  still say what it held (11 §1); and `--dry-run` ends with the largest directories *regardless of
  category*, because "what is taking the space" is the question actually being asked and the answer
  is often something this command will never remove.

  **The scaffolds build, and that was checked rather than assumed.** `hep new analysis` compiles
  against `rivet-config --cppflags`; `hep new module` compiles against the `hekit` headers; `hep new
  project` produces a config `hep plan` expands to one point. A template with a `TODO` where the
  important line goes teaches nothing and costs a search through the docs anyway, so each is the
  smallest real thing — the module scaffold in particular already obeys the scaling contract and
  carries the `threadSafe()` note, because those are the two things a first module gets wrong.
  Nothing is ever overwritten.

  **Deviations.** `hep clean` takes a config argument (it has to know whose results to look at, and
  `[output].root` plus `HEKIT_RESULTS` is the only thing that knows). `hep new` takes `--project`
  and `--into` rather than 08 §2's positional `PROJECT`, and also scaffolds a **module**, which the
  step's Scope did not list but P8-S01's Log had assigned here.
