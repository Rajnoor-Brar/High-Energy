# Current plan — P1-S01 package-skeleton

> Mirror of the step being executed (per bots/BOT.md). Source: `docs/rework/steps/P1-S01_package-skeleton.md`.
> Step index: `docs/rework/steps/README.md`. Status: **in-progress** (2026-09-18). First step of P1.

## Goal

`pip install -e utils/python` gives a working `hep` command from any directory; errors use one type; a pytest
guard fails any test that writes into `results/` or `configs/` (00/B18).

## Plan

- `utils/python/pyproject.toml`: package `hekit`, entry point `hep = hekit.cli:main`, deps click/rich/tomli_w,
  extras `plot`/`ml`/`proc`.
- `hekit/errors.py`: one `HepError(message, where=, hint=)` with a plain renderer; `hekit/__init__.py` version.
- `hekit/env/paths.py`: `HEKIT_ROOT` (validated) else walk up from the package to a repo marker;
  `HEKIT_RESULTS` override; `configs/`, `sources/`, `output/`, `output/scratch/`, per-project helpers
  (idea from `legacy/utils/Utility/Paths.hh:25-54`).
- `hekit/prov/git.py`: short sha + dirty flag for `hep --version`.
- `hekit/cli.py`: click group with **lazy** subcommand loading (no rich/yoda import for `--help`); every command
  of 08 §2 listed, each mapped to the step that implements it, with a clear "arrives in step X" error until then.
- `tests/conftest.py`: the write guard (snapshot of `results/` and `configs/`), applied to **all** test
  directories; `tests/python/conftest.py`: `HEKIT_RESULTS` → tmp_path.
- `env/hep_env.sh`: cached shell completion, interactive shells only.

## Verification

| Check | Expected |
|---|---|
| `cd / && hep --version` | version + git sha |
| `pytest tests/python -q` | guard tests pass (planted write detected on a fake tree) |
| `time hep --help` | < 0.3 s |
| `pytest tests/golden` | still 55 passed, now under the guard |

## Next

P1-S02 `config-schema` (schema-2 loader with strict validation and layering).
