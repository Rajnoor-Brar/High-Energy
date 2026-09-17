# Current plan — P0-S04 golden-fixtures

> Mirror of the step being executed (per bots/BOT.md). Source: `docs/rework/steps/P0-S04_golden-fixtures.md`.
> Step index: `docs/rework/steps/README.md`. Status: **in-progress** (2026-09-17).
> Approved by the user for P0: tags, `~/HEP` edits, local per-step commits (no push), `bots/` layout edits.

## Goal

Freeze the legacy behaviour as data before any fix: plan expansions for every study, a mini run with plot
intermediates, an inventory of the existing results.

## Design

- **Frozen inputs** `tests/golden/inputs/PhotoProduction/{eic.toml,zeus_validation.toml,photo_ep.cmnd}`: copies taken
  at capture time. Fixtures and tests use these, not the live `configs/` (which the user edits), so the tests stay
  stable. A separate test only checks that the live configs still parse.
- `tests/golden/capture_legacy.py` imports `tools/rivpyth_common.py` (pure functions), runs in a temp CWD with
  `configs/PhotoProduction` → inputs; subcommands:
  - `plan` → `legacy_plan/<cfg>/<case>.json`. Cases: every study, the default, and a few CLI overrides
    (`--pin`, `--across … --overlay …`). Each file holds points (number, suffix, settings + origin, analysis,
    plugin, legend, curve legend, page, relative plan paths, point-cmnd text) and pages (suffix, merged YODA,
    output dir, members, legends).
  - `mini` → runs `rivpyth`/`ydmrg`/`ydplt` on `legacy_mini.toml` in `output/scratch/legacy/`, then recomputes the
    plot intermediates (voided YODAs, remapped data, auto-range `.plot`, mkhtml arguments) into `legacy_run/`.
  - `inventory` → read-only `results_inventory.json` for `results/PhotoProduction` (path, bytes, sha256,
    `/RAW/_EVTCOUNT` numEntries/sumW, `/_XSEC`, analyses, cmnd sha + header, serial, flags).
- `legacy_mini.toml`: 2 PDF points (MSTW, NNLO) at 27x920 e⁺p, 5k events, 1 thread, seed 12345, ZEUS data overlay.
- `test_legacy_counts.py`: point/page counts per study (frozen inputs); fixture equality (live expansion of the frozen
  inputs == stored JSON); the mini-run YODAs are complete; the live configs parse.

## Verified fact (affects P0-S05)

`PythiaParallel::run()` returns **attempts** per thread: `eventsPerThread` is incremented before the success check,
and the callback only runs on success (`PythiaParallel.cc:186-208`). The 1M-event results hold
`/RAW/_EVTCOUNT` = 999 903. So:
- B21 must count write failures, not compare `nWritten` with `nGenerated`;
- B3 must compare Rivet's count with the generator's *written* count, not with `event_count`.

## Verification

| Check | Expected |
|---|---|
| `touch output/scratch/stamp` before; after: `find results configs -newer output/scratch/stamp \| wc -l` | 0 |
| `pytest tests/golden -q` | pass |
| `legacy_run/*.yoda` | 2 files; `/RAW/_EVTCOUNT` = the generator's written count (≈ 5000) |

## Next

P0-S05 `legacy-hotfixes` (with the corrected B3/B21 design), then P0-S06.
