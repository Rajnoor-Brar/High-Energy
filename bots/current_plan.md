# Current plan — P1-S05 plan-render (done) → next P1-S06

> Source: `docs/rework/steps/P1-S05_plan-render.md`. Index: `docs/rework/steps/README.md`.
> Status: **done** (2026-09-18).

## What P1-S05 delivered

`hep plan` and `hep studies`; `hekit.plan` (build, naming, model, spec + `spec_v2.json`) and
`hekit.adapters` (pythia, rivet). Generations are named after their events and carry their aliases,
seed block, analyses, stage chain and resolved spec. Rivet options are checked against the analysis
`.info` (00/B14). Cards reproduce the legacy settings modulo seeds.

## Next: P1-S06 config-migrate

`hep config migrate/reference/init/validate`; the v1 → v2 map with the B12 PDF-tag renames and an alias
map, B14 cleanup and an explicit data map; commit `eic.v2.toml` and `zeus_validation.v2.toml` next to the
originals; generated reference at `docs/rework/reference/config.md`.
