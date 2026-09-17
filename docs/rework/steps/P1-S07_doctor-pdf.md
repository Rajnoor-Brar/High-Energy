# P1-S07 — hep doctor and hep pdf

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P1-S01](P1-S01_package-skeleton.md), [P1-S05](P1-S05_plan-render.md) |
| Blocks | [P7-S06](P7-S06_decide-herwig-rebuild.md) |
| Effort | 0.5 d |
| Findings / decisions | F10; R13, R14; 08 §4 |
| Updated | 2026-09-17 |

## Goal

`hep doctor [--json|--brief]` reports tool versions, Python imports, generator capabilities (incl. ThePEG modules), HepMC compression support, `hep-run` capabilities and env sanity; `hep pdf check|list|install` manage LHAPDF sets referenced by a plan.

## Context

- `hep_status` becomes an alias of `hep doctor --brief`.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy` copy of `hep_status` in `env/hep_env.sh` | version parsing | port |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/env/{doctor,lhapdf,tools}.py`, `hekit/prov/{git,versions}.py`
- 24 h cache in `~/.cache/hekit/doctor.json` keyed by `$HEP_INSTALL`

**Out (non-goals)**

- Installing toolchain components

## Design notes

- `hep-run --capabilities` is optional until P2 (reported as 'not built').

## Tasks

- [ ] Implement
- [ ] Alias in `env/hep_env.sh`
- [ ] Tests with monkeypatched probes

## Outputs

- `utils/python/hekit/env/*`, `hekit/prov/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Herwig state | `hep doctor --json \| jq -r .generators.herwig.status` | `run-only` |
| PDF sets | `hep pdf check configs/PhotoProduction/eic.v2.toml` | 4 sets, all installed |
| Brief | `hep_status` | one screen, < 1 s cached |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
