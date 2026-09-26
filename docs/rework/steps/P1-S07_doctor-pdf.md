# P1-S07 — hep doctor and hep pdf

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P1-S01](P1-S01_package-skeleton.md), [P1-S05](P1-S05_plan-render.md) |
| Blocks | [P7-S06](P7-S06_decide-herwig-rebuild.md) |
| Effort | 0.5 d |
| Findings / decisions | F10; R13, R14; 08 §4 |
| Updated | 2026-09-18 |

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

- [x] Implement
- [x] Alias in `env/hep_env.sh`
- [x] Tests with monkeypatched probes

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

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **done.**
  - **`hekit/prov/versions.py`** probes the 13 toolchain components (the `*-config` tools, `rivet`,
    `Herwig`, `Sherpa`, `whizard`, and file checks for MadGraph, Delphes and ONNX Runtime). A missing tool
    is "not installed", never an exception. Herwig reports ThePEG's version alongside its own, and Sherpa
    keeps its codename ("3.0.5 (Erebus)"), the way its releases are referred to.
  - **`hekit/env/doctor.py`** answers the questions that have actually cost debugging time: the 15 Python
    modules (probed in a subprocess, so nothing heavy is imported into `hep`), generator capabilities,
    HepMC3 compression, `hep-run --capabilities` (reported as "not built" until P2), the PDF-set count,
    and environment sanity — empty path entries (which silently mean the current directory), duplicated
    entries, a wrong `HEKIT_ROOT`, an unloaded environment. Every failed check carries its fix.
  - **Herwig** is classified from ThePEG's plugin directory: with no `HepMC`/`Rivet` module the status is
    `run-only`, with the fix "rebuild ThePEG --with-hepmc --with-rivet (P7-S06)". On this machine there
    are 0 such modules out of 60-odd, confirming the audit's finding 5.
  - **Caching:** `~/.cache/hekit/doctor.json`, 24 h, invalidated when `$HEP_INSTALL` changes; an
    unwritable cache degrades to probing rather than failing.
  - **`hekit/env/lhapdf.py` + `hep pdf`:** `list` (installed sets), `check CONFIG [--study]` (which sets a
    plan needs, from the applied settings *and* the base card, exit 1 when any is missing), `install`
    (the only command here that reaches the network).
  - **`hep_status`** is now a thin shell function calling `hep doctor --brief`; the old probe survives as
    `_hep_status_probe` for a shell without `hep` on PATH.
  - **Verification:**
    | Check | Result |
    |---|---|
    | Herwig state | `hep doctor --json` → `generators.herwig.status = "run-only"` |
    | PDF sets | `hep pdf check configs/PhotoProduction/eic.v2.toml --study pdf` → 4 sets needed, 4 installed |
    | Brief | `hep_status` → 7 lines in **0.04 s** cached (the cold probe is ~1.5 s) |
    | Suite | `pytest tests/python tests/golden -q` → **318 passed in 5.0 s** (24 new) |
