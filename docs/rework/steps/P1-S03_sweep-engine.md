# P1-S03 — Port quantities, across, static, studies and pins (with fixes)

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P1-S02](P1-S02_config-schema.md) |
| Blocks | [P1-S04](P1-S04_identity-seeds-hash.md) |
| Effort | 1 d |
| Findings / decisions | 00/B6, B7, B9, B22; golden counts |
| Updated | 2026-09-18 |

## Goal

The sweep semantics of `eic.toml` work on schema 2 — coupled/grid groups, overlay, static, studies, pins — and the four legacy bugs are fixed with regression tests.

## Context

- 03 §3–4; legacy semantics in `docs/plans/04_Roadmap.md` §1.4 (now in `legacy/docs/`).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth_common.py:235-760` | Quantity, Sweep, Static, read_*, flat_groups, set_groups, parse_across, apply_*, expand_points, naming helpers | port per 00b §1 |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- Types: setting (key), beams (ids; `side`), energies, seed, card, generator, events, analysis, option
- B6: overlay/style never re-flatten coupled groups
- B7: validation after study and pins
- B9: lossless value rendering (`repr` for floats; exact ints/bools)
- B22: pin selector precedence (decide here: tag → exact value → `#N` index; record the rule)

**Out (non-goals)**

- Seeds and hashing (S04)
- card rendering (S05)

## Design notes

- Each legacy bug gets a test that first reproduces the old behaviour via `tools/rivpyth_common` (while it exists).

## Tasks

- [x] Write `hekit/sweep/{quantity,select,expand,pages}.py`
- [x] Regression tests
- [x] Golden sweep test against `tests/golden/legacy_plan` (points/pages/legends, via in-memory v1→v2 read)

## Outputs

- `utils/python/hekit/sweep/*`
- `tests/python/sweep/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Bugs fixed | `pytest tests/python/sweep -q` | B6/B7/B9/B22 tests pass |
| Golden sets | `pytest tests/python/sweep/test_golden.py` | point sets and page groupings equal legacy for all studies |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **done.**
  - **Modules:** `hekit/sweep/{quantity,select,expand,pages}.py` as planned.
    - `quantity.py` — value text, tags, labels, legends, the selector rule, `use`.
    - `select.py` — `Selection` (groups, overlay, pins with their origins, study, only), `across` parsing
      for both the TOML and the CLI form, and `validate_selection`.
    - `expand.py` — `Point` and `Assignment`; generation-side values stay **structured** (`beams`,
      `energies`, `events`, `seed`, `cards`, `generator`, native `settings`) so each adapter renders them
      in its own language (P1-S05); analysis-side values become the `analyses` strings.
    - `pages.py` — pages, **event groups** (03 §4: analysis-only variants share one generation), page
      names and curve legends.
  - **The four bugs**, each with a test that first reproduces the legacy behaviour through
    `tools/rivpyth_common` and then the new one (`tests/python/sweep/test_legacy_bugs.py`):
    | Finding | Legacy behaviour reproduced | Now |
    |---|---|---|
    | 00/B6 | `--overlay c` on `across = [[a, b], c]` turned 4 points into 8: the groups were rebuilt from a flat name list | overlay only re-selects which group is drawn; `--style grid` still uncouples when asked |
    | 00/B7 | a `yodamerge` file was rejected at load, even when the study it runs scans seeds | the file loads; the rule is checked against the scan that actually runs |
    | 00/B9 | `format_value(0.123456789)` → `0.123457`, and two distinct values shared a tag | `text_value` is lossless (`repr` for floats); close values get distinct tags |
    | 00/B22 | `--pin pthatmin=6` meant "the sixth value" → "outside 1..4" | tag → value (numeric-aware) → `#N` index; `pthatmin=6` selects 6.0 |
  - **D-B22 decided:** selector order is tag, then exact value (numerically when both sides are numbers),
    then `#N` for an index; `[quantity.<q>].use` stays a 1-based index. Recorded in the register and in
    03 §4.
  - **Golden comparison** (`tests/python/sweep/test_golden.py`): the frozen legacy inputs are translated to
    schema 2 in memory by `tests/python/sweep/v1_to_v2.py` (test scaffolding; the real `hep config migrate`
    is P1-S06) and expanded by the new engine. All **17 cases** match the P0-S04 fixtures on point count,
    point suffixes, legends, analysis strings, page count, page members and curve legends.
    - **Expected difference:** analysis option text is now lossless, so the radius study renders
      `photo_eic:R=1.0` where the legacy tool wrote `photo_eic:R=1` (00/B9). Rivet parses the option as a
      double, so the physics is identical; the test compares option values numerically.
    - The translation keeps the legacy quantity *names*, so the energy quantity is still called `beams`
      (v1 `cmnd.beams` held energy pairs) and the lepton quantity `lepton`; P1-S06 renames them to
      `energies`/`beams` with an alias map.
  - **Two schema defects found by the new tests** (fixed in `config/fields.py`): a field's own default must
    not be judged by its `choices` or its range — `[sweep].style = ""` names no style and `[beams].ids = []`
    means "not given" while a given list must hold exactly two ids. The type is still always checked.
  - **Verification:**
    | Check | Result |
    |---|---|
    | `pytest tests/python/sweep -q` | **51 passed** (B6/B7/B9/B22 each demonstrated old vs new) |
    | golden point sets and pages | 17/17 cases equal to the legacy fixtures |
    | whole suite | `pytest tests/python tests/golden -q` → **209 passed in 1.9 s** |
