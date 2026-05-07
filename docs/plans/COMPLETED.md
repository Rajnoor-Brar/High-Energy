# Completed batches — post-W7 streamline (Batch01–07)

> Historical record of the seven implementation batches that delivered the
> ROADMAP P1/W1–W10 sweep plus Batch07 streamline cleanup. Each batch was
> a single commit (or small commit chain) verified by `make` + `make test`
> before the next batch began. Per-batch detail files have been removed —
> this file is the surviving summary.
>
> Companion to [../REVIEW.md](../REVIEW.md), [../ROADMAP.md](../ROADMAP.md),
> [../MAP.md](../MAP.md), [../Architecture.md](../Architecture.md),
> [../DataFlow.md](../DataFlow.md).

---

## Batch01 — Pre-flight + dead-config drop (P1 + W5)

- Added `Config::extractConfiguration` alias and closed the
  `namespace Config` block in `utils/Config.hh` — restores green builds.
- Deleted `Events::isPythia` field, parser line, and dead TOML keys
  (`events.pythia` / `events.probe`).

## Batch02 — Writer absorbs Finalizer (W7)

- `installFatalStallHandler`, `setMeta`, `shutdown(sets)`, `checkpoint`,
  private `fatalShutdown`, and `bind(...)` moved from
  `Record::FinalizerController` onto `Record::Writer`.
- `Writer` gains a private `std::mutex histMutex_` plus `recordingScope()`
  RAII; drivers no longer declare a local `histMutex`.
- `Lambda::pythiaAnalysis`'s inline checkpoint logic collapsed into
  `writer.checkpoint(ctx.histograms, eventIndex)`.
- `FinalizerController` deleted as a class; a thin `Record/Finalizer.hh`
  remains only as the inline-bodies file for the Writer methods (split
  to break the `Monitor::Logger` ↔ `Writer` include cycle).
- All four drivers + smoke test migrated to `writer.bind(...)` /
  `writer.shutdown(sets)`.

## Batch03 — `Probe::ProbeParallel` + Logger absorbs Watch (W6 + W8)

- New class `Probe::ProbeParallel` (`utils/Probe/ProbeParallel.hh`) with
  members `inputFile`, `collections`, `nThreads`, `nEvents` and methods
  `resolveEvents()` + `template <class Cb> void run(Cb&&)`.
- `runParallel` / `EventStream` lost the unused `scalars` parameter
  (`ScalarSpec` plumbing dead).
- `AsyncLogger` gained a private `Config::Watch watch_` member and a
  `watch()` accessor (mutable + const).
- New `Config::configureMonitor(AsyncLogger&, configPath, project)`
  loads pacing/interval fields off the TOML directly into the logger;
  `Watch::*_interval` fields removed.
- All four drivers + smoke test pass `logger.watch()` instead of a
  local `Config::Watch`.

## Batch04 — `Config::configure` facade (W2 + W1)

- New `utils/Config/Configure.hh` (separate from `Config.hh` to avoid
  the Probe ↔ Config include cycle) with two overloads:
  - `configure(path, project, Probe::ProbeParallel&, Writer&, AsyncLogger&)`
  - `configure(path, project, PythiaT&, Writer&, AsyncLogger&)`
- Probe overload calls `probe.resolveEvents()` before
  `configureWriter` so the output filename embeds the resolved count.
- Pythia overload reads `Beams:eCM` from the already-loaded settings as
  fallback when `[pythia].beam_energy` is absent.
- Drivers replace their `Config::Register reg; Config::Watch watch; ...`
  block with a single `Config::configure(...)` call.

## Batch05 — Type-bleed collapse (W10)

- `Config::ProbeParticle` deleted; `[probe]` parser moved into
  `Probe::parseCollectionsFromToml(const toml::table&)` returning
  `vector<Probe::CollectionSpec>` directly.
- `Config::ProbeConfig::particles` (legacy `vector<ProbeParticle>`)
  replaced with `collections` (`vector<Probe::CollectionSpec>`).
- Spurious `#include "Config.hh"` removed from
  `Probe/BranchControl.hh` (it never used Config types) — eliminated
  the potential circular-dep risk.
- Dependency-direction comment block added to top of `utils/Config.hh`.

## Batch06 — Watch / Register purge (W9)

- `Watch` slimmed to live counters only:
  `iEvent`/`n_real_events` atomic, `nEvents`/`n_threads` plain,
  `start` `TimePoint`, `elapsed` atomic. `serial`/`sr_padding`/
  `n_digits` removed (serial moved onto `Register` then onto
  `Writer::paths()`).
- `eventMutex_` removed; `recordEvent(now)` is now lock-free
  (`fetch_add` + relaxed `store`).
- All consumers updated to use `.load(memory_order_relaxed)` for
  `n_real_events` and `elapsed`.
- `<mutex>` include removed from `Config/Types.hh`.

## Batch07 — Streamline cleanup

- **`Lambda::configure(parameters, sets, writer, configPath)`** wrapper
  added to `modules/Lambda.hh`; collapses `extractPhysics + declareObjects`
  into one call. Drivers replace four lines with two.
- **Pythia cmnd from TOML.** `[pythia].cmnd_file` added to
  `configs/Lambda_Reconstruction.toml`; the three hardcoded
  `pythia.readFile("configs/Lambda_Reconstruction.cmnd")` calls deleted
  from drivers (`configurePythia` already calls it internally).
- **TreeRecord wire-up.** New `Lambda::Parameters::writeTree` field;
  `extractPhysics` parses `[lambda.analysis].writeTree` (array of set
  names); `declareObjects` calls `Record::declareTree(...)` for each
  enabled set. Dead `kTreeEnabledSets` and `Lambda::SpecsArray`
  deleted.
- **Limits load optional.** `configs/defaults/Limits.toml` load wrapped
  in `fs::exists` guard; absent file silently skipped, project limits
  still required.
- **Reproducibility metadata.** Makefile bakes
  `-DGIT_SHA=...` and `-DGIT_DIRTY=0/1` at build time. `Meta::Integrity`
  gains `git_sha`, `git_dirty`, `host_uname`, `file_shas`. New
  `sha256File()` helper shells out to `shasum`/`sha256sum`. New
  `integrityAddFileSha(rec, path)` lets drivers tag config + limits.
  `_Lambda_Reconstruction.cc` records both.
- **Umbrella doc-comments.** Role + submodule blocks added to
  `Monitor.hh`, `Record.hh`, `Physics.hh`, `Probe.hh`, `Utility.hh`,
  `Paint.hh`. (`Config.hh` already had its dependency-rule block.)
- **Cross-link docs.** `DataFlow.md`, `MAP.md`, `REVIEW.md` cross-link
  to all sibling docs.

---

## Verification invariants (post-Batch07)

```sh
grep -n 'extractPhysics\|declareObjects' _Lambda_*.cc tests/*.cc
# empty — drivers go through Lambda::configure

grep -n 'pythia\.readFile' _Lambda_*.cc
# empty — cmnd_file comes from TOML

grep -rn 'kTreeEnabledSets\|SpecsArray' modules/ utils/
# empty — dead symbols removed

grep -nE 'Config::Register|Config::Watch|Config::ProbeConfig|extractConfiguration' \
     _Lambda_*.cc tests/*.cc
# empty — drivers use Config::configure facade only

grep -n 'FinalizerController\|histMutex' _Lambda_*.cc tests/*.cc modules/Lambda.hh
# empty — Writer absorbs Finalizer; mutex internal to Writer
```

All five targets (`_Lambda_Reconstruction.exe`, `_Lambda_Parallel.exe`,
`_Lambda_Test.exe`, `_Lambda_Data.exe`, `tests/test_rootAnalysis_smoke.exe`)
build clean. `make test` passes T1–T5 and S1–S5.
