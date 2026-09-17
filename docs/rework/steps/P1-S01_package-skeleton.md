# P1-S01 — Create the hekit package, CLI entry point and test guard

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P0-S07](P0-S07_makefile-hygiene.md) |
| Blocks | [P1-S02](P1-S02_config-schema.md), [P1-S07](P1-S07_doctor-pdf.md), [P2-S03](P2-S03_core-status.md) |
| Effort | 0.3 d |
| Findings / decisions | 00/B18; N10 |
| Updated | 2026-09-17 |

## Goal

`pip install -e utils/python` gives a working `hep` command from any directory; errors use one type; a pytest guard fails any test that writes into `results/` or `configs/`.

## Context

- 08 §2 (command tree), 09 §2 (packaging), 13 §4 (packages).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Utility/Paths.hh:25-54` | env var → walk up to an anchor | reimplement in `hekit.env.paths` |
| `tools/rivpyth_common.py:16` `ConfigError` | error shape | adapt to `HepError(msg, where, hint)` |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `utils/python/pyproject.toml` (entry `hep = hekit.cli:main`; deps click, rich, tomli_w; extras plot, ml, proc)
- `hekit/{__init__,cli,errors}.py`, `hekit/env/paths.py` (`HEKIT_ROOT`, `HEKIT_RESULTS`, repo root from package location)
- `tests/python/conftest.py`: autouse fixture sets `HEKIT_RESULTS=tmp_path`, snapshots mtimes of `results/` and `configs/`, fails the session on change

**Out (non-goals)**

- Any subcommand logic

## Design notes

- click groups registered lazily so `hep --help` stays fast (no yoda/ROOT import).
- `hep --version` prints hekit version + git sha (via `hekit.prov.git` stub).

## Tasks

- [ ] Write pyproject + skeleton
- [ ] Editable install into `~/HEP/.venv`
- [ ] Add completion line to `env/hep_env.sh` (cached)
- [ ] Write guard + a deliberately failing planted-write test (marked xfail-strict)

## Outputs

- `utils/python/**`
- `tests/python/conftest.py`
- `env/hep_env.sh` (completion)

## Verification

| Check | Command | Expected |
|---|---|---|
| Runs anywhere | `cd / && hep --version` | version string |
| Guard works | `pytest tests/python -q` | planted write detected (xfail passes) |
| Fast help | `time hep --help` | < 0.3 s |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

`pip uninstall hekit`; remove `utils/python`.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
