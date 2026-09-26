# P1-S06 — Migration tool and schema-2 configs

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P1-S05](P1-S05_plan-render.md) |
| Blocks | [P4-S06](P4-S06_retire-legacy-tools.md) |
| Effort | 0.5 d |
| Findings / decisions | 00/B12, B14; 03 §6 |
| Updated | 2026-09-18 |

## Goal

`hep config migrate|reference|init|validate` exist; `eic.v2.toml` and `zeus_validation.v2.toml` are committed next to the originals; the config reference is generated.

## Context

- Transition: v2 files replace v1 at P4-S06; `.v2` suffix dropped in P10-S01.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Config/Reader.hh:79-102`, `legacy/utils/Monitor/Configure.hh:20-60` | removed-key tables | idea |
| `tools/rivpyth_common.py:90-100` | `MOVED_*` dicts | port |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- v1 → v2 map per 03 §6 (lepton → beams side b; old beams → energies; sections)
- Hand-reviewed v2 configs: B12 tag renames with a legacy alias map; B14 invalid quantities removed; explicit `[plot.data].map` or no data
- `docs/rework/reference/config.md` generated from schema metadata

**Out (non-goals)**

- Deleting v1 configs

## Design notes

- `migrate --stdout` for review; never overwrites without `--write`.

## Tasks

- [x] Implement commands
- [x] Migrate + hand-review both configs (approval for commit)
- [x] Generate reference

## Outputs

- `utils/python/hekit/config/{migrate,reference}.py`
- `configs/PhotoProduction/{eic,zeus_validation}.v2.toml`
- `docs/rework/reference/config.md`

## Verification

| Check | Command | Expected |
|---|---|---|
| Round trip | `hep config migrate eic.toml --stdout \| hep config validate -` | valid |
| Same plan | pytest: plan(migrated file) vs plan(in-memory migration) | equal except documented renames |
| Deterministic reference | generate twice; diff | identical |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Delete the `.v2` files; revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **done.**
  - **`hekit/config/migrate.py`** translates schema 1 → 2 per 03 §6 and **reports every change** as notes,
    which become the header comment of the generated file. It refuses rather than guesses: a table-valued
    quantity with no `setting`, a file that is already schema 2, or a file that is not a run config.
    - Quantities are renamed so that a name matches its type: v1 `cmnd.beams` held *energies* and becomes
      `energies`; the `Beams:idB` setting becomes `beams` with `side = "b"` (03 §3). Every reference
      follows (`across`, `overlay`, `pin`, `[static.use]`).
    - **00/B12:** the PDF tags are renamed — `MSTW → MSTW08lo`, `NNLO → NNPDF23lo`,
      `NNNLO → NNPDF23nlo`, `LHC21 → PDF4LHC21` — and the old names are kept in the quantity's `note`
      and in the migration report, so old result names can still be traced.
    - **00/B14:** an option quantity whose analysis does not declare the option is dropped, with the
      reason. On `zeus_validation.toml` that removes `radius` and `etmin`, because
      `ZEUS_2012_I1116258` declares no options at all. References to a dropped quantity are removed too.
    - **00/B5:** a v1 `use_data` overlay migrates with an **empty** `[plot.data].map` and a note, because
      schema 2 overlays reference data only where it is mapped explicitly.
    - **D-B22:** a v1 integer selector meant a position and becomes `"#N"`.
  - **Deviation — a TOML emitter.** `tomli_w` puts every array element on its own line, which turned a
    four-value quantity into twenty lines. `migrate.to_toml` emits the document with short arrays inline
    (96-column budget), no empty parent headers (`[quantity]` above `[quantity.pdf]`), and quoting only
    where a key needs it; each scalar is still formatted by `tomli_w`, so escaping is not reimplemented.
  - **`hekit/config/reference.py`** generates the reference from the same field tables the loader uses, so
    it cannot drift, plus the `hep config init` starter.
  - **Commands:** `hep config migrate|validate|reference|init`. `migrate` writes `<name>.v2.toml` next to
    the original, never overwriting without `--force`; with no TTY it says so instead of **hanging on a
    prompt** (found while running it here).
  - **`hep config init`** produces a deliberately incomplete scaffold: `[rivet].analyses` is empty, so
    loading it says "nothing would consume the events" and names the key to fill in. The command prints
    that as the next step.
  - **Committed configs:** `configs/PhotoProduction/{eic,zeus_validation}.v2.toml`, hand-reviewed; the
    v1 files stay until P4-S06. A test asserts the committed files are byte-identical to what the tool
    produces today.
  - **Deviation:** `tests/python/sweep/v1_to_v2.py` (the P1-S03 test translator) is deleted; the golden
    tests now call this migration with `rename_tags=False, drop_undeclared_options=False`, so there is one
    implementation and the golden comparison also exercises it.
  - **Verification:**
    | Check | Result |
    |---|---|
    | Round trip | `hep config migrate … --stdout` → `hep config validate -` → "valid schema-2 configuration" |
    | Same plan | the committed `.v2.toml` plans exactly like a fresh in-memory migration (names and identity hashes); `hep plan eic.v2.toml --study energy_pdf --json` → 16 points, 4 pages, no warnings |
    | Deterministic reference | generated twice → identical; a test fails if the committed `docs/rework/reference/config.md` is stale |
    | Renames | point names differ from the legacy ones exactly by the four tag renames |
    | Suite | `pytest tests/python tests/golden -q` → **294 passed in 4.6 s** (31 new) |
