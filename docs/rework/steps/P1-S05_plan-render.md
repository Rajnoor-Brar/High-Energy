# P1-S05 — Plan groups, stage chains, resolved specs and point cards

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P1-S04](P1-S04_identity-seeds-hash.md) |
| Blocks | [P1-S06](P1-S06_config-migrate.md), [P1-S07](P1-S07_doctor-pdf.md), [P2-S04](P2-S04_source-run-loop.md), [P6-S02](P6-S02_event-groups.md) |
| Effort | 1 d |
| Findings / decisions | 00/B14; F2 |
| Updated | 2026-09-18 |

## Goal

`hep plan` and `hep studies` show points → groups → stage chains and write resolved `run.toml` + `point.cmnd` to a temporary directory; the Pythia and Rivet adapters validate their parts.

## Context

- 02 §3–4, 03 §7, 04 §3; spec contract shared with C++ tests.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth_common.py:786-840` | `execution_plan`, `write_point_cmnd`, `plot_file_for`, `common_analysis` | port |
| `tools/rivpyth:128-146` | `print_point` output shape | adapt for `hep plan` |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/plan/{model,build,naming,spec}.py` + `spec_v2.json` (JSON Schema)
- `hekit/adapters/{base,pythia,rivet,store}.py`: card header (base sha256, origin); ids/energies rendering; `Parallelism:seeds`; reject raw `Beams:*` and `processAsync` in cards/overrides; √s-with-different-ids warning; Rivet options checked against the plugin `.info` `Options:`
- `hep plan [--json] [--explain KEY]`, `hep studies`

**Out (non-goals)**

- `--check` preflight (needs `hep-run`, P2-S04)
- external adapters (P7)

## Design notes

- Rendered files go to a per-invocation temp dir; never into `results/`.

## Tasks

- [x] Implement modules
- [x] CLI wiring
- [x] Golden tests against legacy point cmnds (settings modulo seeds)
- [x] Test that zeus R/ETMIN option quantities are rejected

## Outputs

- `utils/python/hekit/{plan,adapters}/*`
- `tests/python/plan/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Counts | `hep plan configs/PhotoProduction/eic.v2.toml --study energy_pdf --json \| jq '.points\|length, .pages\|length'` (after S06; before: in-memory v1) | 16, 4 |
| Cards | pytest golden | settings equal legacy except seeds |
| Option validation (B14) | pytest: zeus config | error naming R/ETMIN |
| Guard | pytest session | no writes to results/configs |

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
  - **Modules:** `hekit/plan/{model,build,naming,spec}.py` + `spec_v2.json`, and
    `hekit/adapters/{__init__,pythia,rivet}.py`. (`store` is declared in the adapter registry but
    implemented in P5-S02; the other tools in P7.)
  - **Generations, not points.** A group is named after the **events** it produces
    (`eic_18x275_ep_NNLO_pt32_mpi`), not after the first analysis variant, so the radius study is one
    directory with three analysis variants in one Rivet handler and three aliases. `Point` gained
    `generation_name` for this.
  - **Pythia adapter** (04 §3): renders the header (base sha256, origin, point, identity, analyses), the
    run control (`Main:numberOfEvents`, `Parallelism:numThreads`, `Random:setSeed`, `Random:seed`,
    `Parallelism:seeds` when threads > 1, `Next:numberCount = 0`, `Init:showChangedSettings = on`),
    `[beams]` (ids → `Beams:idA/idB`; a pair → `frameType 2` + `eA`/`eB`; a scalar → `frameType 1` +
    `eCM`), then the overrides grouped by origin. It **refuses** what the plan owns: `Beams:*`,
    `Main:numberOfEvents`, `Parallelism:*`, `Random:*` in an override, and `Parallelism:processAsync`
    anywhere, each with the key to use instead. A scalar √s with different beams warns about the CM
    frame.
  - **Rivet adapter** (00/B14): reads the analysis `.info` (config `[rivet].paths`, then
    `analyses/<project>`, `output/<project>`, then `RIVET_ANALYSIS_PATH` and `rivet-config --datadir`)
    and rejects options the analysis does not declare. Verified on the real case: `ZEUS_2012_I1116258`
    declares **no** options, so scanning `R` on it now fails with "does not take R … it declares: none".
    A missing `.info` is a warning, not an error, because the plugin may simply not be built yet.
  - **Resolved spec** (03 §7): `[meta]` (schema, point, aliases, hash, origin), `[run]` + `[run.seeds]`,
    `[source]`, `[output]`, `[[sink]]` (rivet, module, store), `[status]`. `spec_v2.json` is the shared
    contract, validated with `jsonschema` (added to the `dev` extra) and by a structural fallback when it
    is absent. Every spec of every study validates.
  - **Commands:** `hep plan CONFIG [--study/--pin/--across/--style/--overlay/--set] [--index]
    [--explain KEY] [--json] [--write DIR]` and `hep studies CONFIG [--json]`. Rendering goes to a
    per-invocation temporary directory unless `--write` names one; nothing touches `results/`.
  - **Verification:**
    | Check | Result |
    |---|---|
    | Counts | `hep plan … --study energy_pdf --json` → 16 points, 4 pages, 16 distinct generations |
    | Cards | every setting of the legacy point cmnd is reproduced with the same value, modulo the seeds and the four keys the plan now owns; no unexpected extra settings |
    | Seed blocks | `Parallelism:seeds` holds exactly the identity block; across a 4-point study no instance seed repeats; a 1-thread run writes no block |
    | Option validation (00/B14) | zeus + `--across radius` → "analysis 'ZEUS_2012_I1116258' does not take R" |
    | Guard | the project directory is byte-identical after planning; the session guard covers `results/` and `configs/` |
    | Suite | `pytest tests/python tests/golden -q` → **263 passed in 4.0 s** (30 new) |
  - **Deviation:** the step listed `hekit/plan/naming.py` for names; point and page *naming* stayed in
    `hekit.sweep.pages` (it belongs with the tags), and `plan/naming.py` holds the output **paths**
    (07 §1) instead.
