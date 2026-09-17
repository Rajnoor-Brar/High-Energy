# Current plan — P0-S05 legacy-hotfixes

> Mirror of the step being executed (per bots/BOT.md). Source: `docs/rework/steps/P0-S05_legacy-hotfixes.md`.
> Step index: `docs/rework/steps/README.md`. Status: **in-progress** (2026-09-18).
> Approved by the user for P0: tags, `~/HEP` edits, local per-step commits (no push), `bots/` layout edits.

## Goal

Results produced by the legacy tools until P4-S06 are trustworthy: no correlated seeds, no partial YODA treated as
complete, correct labels, no mismatched data overlay, real error reporting.

## Corrections to the step's design (found in P0-S04)

- **B21** cannot compare `nWritten` with `nGenerated`: `PythiaParallel::run()` returns *attempts* and calls the
  callback only for successful events, so `nWritten < nGenerated` is normal (2 % at 5x41). Instead: count
  `writeNextEvent` failures, and check `toHepMC.output().failed()` right after opening. Exit 4 on either.
- **B3** cannot compare Rivet's count with `event_count` for the same reason. Instead: compare Rivet's
  `/RAW/_EVTCOUNT` with the generator's *written* count, parsed from its summary line (relayed through a pipe).
- **B3 suffix:** YODA rejects `X.yoda.part` ("Format cannot be identified"), so the partial file is `X.part.yoda`.

## Scope

- B3: rivet writes `<name>.part.yoda`; rename to `<name>.yoda` only when both processes exit 0 and the counts agree.
- B20: keep both exit statuses; report the first *real* failure (a knock-on SIGPIPE/SIGTERM does not mask Rivet's).
- B21: as corrected above.
- B2: `ConfigError` when a base seed is used with `threads > 1` and `seed_step < threads`; configs get `seed_step = 20`.
- B4: 27x920 label √s = 318.1 GeV (2·√(27.5·920)). B5: `use_data = false` in eic.toml. B10/B13/B23: comments.
- Record B11 (no action), B12 (v2 rename), B27 (pTHatMin above ETMIN).
- Re-capture fixtures; write `tests/golden/legacy_plan/EXPECTED_DELTAS.md`; add `tests/golden/test_hotfixes.py`.

## Verification

| Check | Expected |
|---|---|
| Kill test (B3) | no final `.yoda`; `.part.yoda` present; rerun regenerates |
| Bogus analysis (B20) | Rivet's status and message, not the generator's SIGPIPE |
| Unwritable output (B21) | non-zero exit |
| threads=20, seed_step=1 (B2) | `ConfigError` |
| `pytest tests/golden` | passes with the deltas recorded |
| ProcessType=2 (B13) | verify the claim before rewriting the comments |

## Next

P0-S06 `legacy-archive`, then P0-S07.
