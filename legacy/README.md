# legacy/ — frozen code, kept for reference and porting

Everything here is **archived, not maintained**. It is the state the rework replaces (D14/D17,
[docs/rework/10_Roadmap.md](../docs/rework/10_Roadmap.md)). Moved here in P0-S06 with `git mv`, so
`git log --follow` still shows each file's full history.

**Nothing outside `legacy/` may include or import from it.** Snippets are copied or adapted into the new
code, never `#include`d — see [PORTING.md](PORTING.md).

## Tags to build from

| Tag | What it is |
|---|---|
| `legacy/lambda-final` | the last commit with Lambda, the old `utils/` and their tests in their original places |
| `rework/baseline` | same commit; the PhotoProduction workflow as it ran before the rework |

To work on the archived code, check out the tag rather than trying to build it in place:
`git checkout legacy/lambda-final`. In the current tree the Lambda make targets no longer resolve
(`sources/Lambda` is now `legacy/lambda/sources`), which is expected.

## What is here

| Path | Was | Notes |
|---|---|---|
| `lambda/modules/`, `lambda/sources/`, `lambda/configs/` | `modules/Lambda{,.hh}`, `sources/Lambda`, `configs/lambda` | the Λ → pπ⁻ study; does not run, see below |
| `utils/` | `utils/` | the old C++ framework (Config, Monitor, Paint, Physics, Probe, Record, Utility) |
| `tests/` | `tests/` except `tests/golden` | the old C++ unit tests and `run_all.sh` |
| `analyses/` | `sources/PhotoProduction/photo_{5x41,10x100,18x275}.*` | per-energy Rivet plugins, superseded by `photo_eic` (its options reproduce them: `WMIN`/`WMAX`) |
| `configs/` | `configs/{defaults,templates,all.toml,Paint.toml}`, `configs/photo_zeus/README_ZEUS.txt` | old config vocabulary and house plot style; `README_ZEUS.txt` describes deleted files (00/B28) |
| `misc/` | `_Paint.cc`, `_ThreadBench.cc`, `root_macros/` | drivers and the ROOT plotting macro |
| `docs/` | `docs/{MAP,Architecture,DataContract,UtilsAudit,UtilsDependencyMap,Audit}.md`, `docs/archive/`, `docs/plans/`, `bots/{CLAUDE,plan,GEMINI}.md` | stale documentation (00 §4.7); `docs/plans/` is superseded by `docs/rework/` |
| `results/PhotoProduction.inventory.json` | `tests/golden/results_inventory.json` | read-only inventory of `results/PhotoProduction` captured in P0-S04 |

## Lambda: what it did

Ne–Ne collisions with Angantyr at 7 TeV per nucleon; Λ → pπ⁻ only (no Λ̄). Particles are harvested by
`isFinal` and pid (2212, −211), paired, filtered by a mass window, then reduced by a greedy unique
selection capped at `Np − reserved_protons`. 21 histograms in 3 sets. The physics is about 100 lines and
needs only `isFinal`, pid and momentum, so it would port to a `GenEvent` module (P8-S01) without the ROOT
tree stage.

**Known defects (not fixed):**
- Every driver aborts at configure: `hist_limits` resolves to a missing `Lambda_Limits.toml`, and the
  `cmnd_file` and driver defaults point at old paths. A syntax-only compile passes.
- The `.cmnd` redefines ²⁰Ne with `m0 = 0` and `chargeType 20`.
- The angle cut is dead: cos θ ≡ −1 in the pair rest frame.
- `reserved_protons` does not correspond to Angantyr's `NucRem`.
- `HeavyIon:SigFitNGen` is set twice; the Pb `SigFitDefPar` is left in.
- The writer can emit rows out of `event_index` order.
- Histograms are scaled ×100 when `hist_scaling` is unset.
- `Momentum_Z` limits start at 0, so the negative half is lost.

A revival estimate and a piece-by-piece target list are in
[docs/rework/00b_PortingMap.md](../docs/rework/00b_PortingMap.md) §5: about 1.5 d faithful, 3–4 d with the
fixes and the mass fit (at generator level the peak is a spike, so smearing or truth matching is needed).

## Old `utils/`: known defects

Recorded so they are not reintroduced; the new design avoids them by construction
([docs/rework/00_Audit.md](../docs/rework/00_Audit.md) §4.5).

- Record checkpoints contain empty histograms: fills go to worker clones, but checkpoints write the
  unmerged masters.
- Final histograms are probably unscaled: `Write(kOverwrite)` rewrites the masters after the scaled
  snapshot (unverified).
- The Monitor bar interval is computed before the event count is known (default `nEvents = 100`).
- Negative section thread counts wrap around.
- `readFile`/`init()` return values are unchecked.
- `sum_weights` is a placeholder.
- Include cycles: Config ↔ Probe, Record ↔ Monitor.
- Probe: float-only array readers; reader-dependent column types; two array specs on one tree can read
  stale data (unverified); IMT re-reads earlier windows (quadratic I/O).
- Paint: overlay legends may be destroyed before the canvas is saved (unverified).
- `tests/run_all.sh` globs `tests/test_*.exe` while the binaries land in `output/tests/`, so it reported
  "0 passed" and exited 0; `test_utils_hardening` expects a config that has moved.

## Also archived here

`docs/plans/` (2026-09-16) asked how to integrate the new tools into the old module stack. It is superseded
by `docs/rework/`; its still-open items became P0 steps (0.1 → P0-S03, 0.3 → P0-S07, 0.4 → archived
instead of repaired, 0.7 → P0-S02). Its findings are cited as `plans/Bn` in the rework docs.
