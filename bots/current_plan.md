# Current plan — P1-S02 config-schema

> Mirror of the step being executed (per bots/BOT.md). Source: `docs/rework/steps/P1-S02_config-schema.md`.
> Step index: `docs/rework/steps/README.md`. Status: **in-progress** (2026-09-18).
> Note: this mirror was written mid-step, not before it started (recorded in the step Log).

## Goal

Any run TOML loads into typed dataclasses with origin tracking; unknown keys, wrong types and
out-of-range values fail with file:key, a did-you-mean hint and a fix; `extends`, the machine file and
`--set` layer in a defined order (03 §1–2, §6).

## Modules

- `hekit/config/fields.py` — `Field` (kind, default, doc, range, choices, item, free) and the value checks;
  `Section`; duration parsing.
- `hekit/config/schema.py` — every section of 03 §1 as a field table; the section dataclasses are
  generated from those tables (one source of truth for defaults, types and docs).
- `hekit/config/load.py` — TOML reading, a line scanner for origins (`tomllib` gives no line numbers),
  schema-aware flattening, layers, the machine allow-list, `extends` with cycle detection, `--set`.
- `hekit/config/model.py` — `Config`, `Study`, `load_config()`, `origin()`, `explain()`.
- `hekit/config/validate.py` — schema version (schema-1 files get a migration hint), quantity shape,
  cross-section rules; warnings collected rather than printed.

## Verification

| Check | Expected |
|---|---|
| `[plot] min_entry` | error suggests `min_entries`, with file:line |
| `[run] threads = -1` | range error, no wrap; `threads = true` is a type error |
| extends a↔b | cycle error naming both files |
| machine file sets `generator.card` | refused, listing the allow-list |
| origin chain | `default → extends → file → cli` for `run.threads` |
| `pytest tests/python tests/golden` | green |

## Next

P1-S03 `sweep-engine` (quantities, across, settle, studies, pins, overlay, naming, with fixes for
00/B6, B7, B9, B22).
