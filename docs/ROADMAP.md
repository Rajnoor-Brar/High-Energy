# Roadmap — post-streamline status

> The post-W7 streamline (Batch01–07) executed the full P1 + W1–W10 slice
> plus the Batch07 cleanup. This file captures the resulting driver shape,
> the deferred observations that survive as orthogonal future work, and
> any subsequent slice when one is queued.
>
> Companion to [Architecture.md](Architecture.md) (strategic plan-of-plans
> — items W1–W10 marked complete), [REVIEW.md](REVIEW.md) (open backlog),
> [MAP.md](MAP.md) (current state), [DataFlow.md](DataFlow.md) (TOML key
> inventory), [plans/COMPLETED.md](plans/COMPLETED.md) (per-batch
> summary).

---

## North star — achieved

> **Config owns configuration; objects own state.** Drivers are now thin
> wrappers around three interface objects: a runner (`Probe::ProbeParallel`
> or `Pythia8::PythiaParallel`/`Pythia`), a `Record::Writer`, and a
> `Monitor::AsyncLogger`. `Config::configure` populates all three from a
> single TOML path. No `Watch` / `Register` / `ProbeConfig` locals in
> driver scope; no per-event `histMutex`; no separate `FinalizerController`
> declaration.

Reference driver shape (current `_Lambda_Reconstruction.cc`):

```cpp
Probe::ProbeParallel  probe;
Record::Writer        writer;
Monitor::AsyncLogger  asyncLogger;

Config::configure(configPath, project, probe, writer, asyncLogger);

Lambda::Parameters physParams;
Lambda::RootArray  histogramSets;
Lambda::configure(physParams, histogramSets, writer, configPath);

writer.bind(asyncLogger, asyncLogger.watch(),
            [&]{ return Lambda::logString(physParams); });
writer.installFatalStallHandler(histogramSets);

asyncLogger.watch().start = std::chrono::system_clock::now();
asyncLogger.start(writer);

Lambda::AnalysisContext ctx{
    histogramSets, physParams, asyncLogger.watch(), asyncLogger, writer};
probe.run([&](const Probe::Event& ev, int threadId) {
    Lambda::rootAnalysis(ev, threadId, ctx);
});

writer.shutdown(histogramSets);
```

---

## Completed work items

| Item | Title                                                         | Landed in |
| ---- | ------------------------------------------------------------- | --------- |
| P1   | `extractConfiguration` alias + `namespace Config` close        | Batch01   |
| W5   | Delete `Events::isPythia`                                      | Batch01   |
| W7   | `Record::Writer` absorbs `FinalizerController`                 | Batch02   |
| W6   | `Probe::ProbeParallel` class                                   | Batch03   |
| W8   | `configureMonitor`; `AsyncLogger` absorbs `Watch`              | Batch03   |
| W2   | `Config::configure` facade (folds W1)                          | Batch04   |
| W10  | Type-bleed collapse (`Config::ProbeParticle` → `Probe::CollectionSpec`) | Batch05 |
| W9   | Purge `Watch`/`Register`; lock-free counters                   | Batch06   |
| —    | Batch07 streamline (Lambda::configure, TreeRecord wire-up, Pythia cmnd from TOML, optional Limits load, reproducibility metadata, umbrella docs, doc cross-links) | Batch07 |

Per-batch detail: [plans/COMPLETED.md](plans/COMPLETED.md).

---

## Deferred / orthogonal observations

These are real but architecturally orthogonal to the streamline that just
landed. Listed here so they don't get lost; not on any active execution
path. Several have been re-anchored from the previous ROADMAP §B.5.

- **Silent `hist_limits` resolution.**
  [utils/Config/LimitAid.hh:7–15](../utils/Config/LimitAid.hh) silently
  expands a bare name into `configs/<name>.toml`. If the user typoed or
  moved the file, the only signal is a downstream `Histogram limits file
  does not exist` exception in
  [Lambda/Loaders.hh](../modules/Lambda/Loaders.hh). Print the resolved
  path on first read.
- **`AsyncLogger::runLoop` shuttles five `std::optional<…>` across one
  lock boundary** ([utils/Monitor/Logger.hh](../utils/Monitor/Logger.hh)).
  Works; a small `std::queue<Action>` drained outside the lock would
  make adding a new heartbeat tick a one-line change instead of editing
  six places.
- **`Probe::runParallel` swallows then rethrows the *first* worker
  exception** ([utils/Probe/Parallel.hh](../utils/Probe/Parallel.hh)).
  Aggregate or chain so a second fault's diagnostic isn't lost.
- **`tests/run_all.sh:30` `break`s on first failure.** Drop the `break`;
  report total pass/fail at the end so a regression in
  `test_reconstructCandidates` doesn't mask a regression in
  `test_rootAnalysis_smoke`.
- **Every `runParallel` worker re-opens the input file** via a fresh
  `EventStream` ([utils/Probe/Parallel.hh](../utils/Probe/Parallel.hh)).
  Shared `TThreadedObject<TFile>` pool — paid-once cost at scale.
- **`Lambda::reconstructCandidates` ordering**
  ([modules/Lambda/Reconstruction.hh](../modules/Lambda/Reconstruction.hh))
  computes `cosTheta` *before* the mass cut. Reorder so `cosTheta` is
  computed only on survivors.
- **`Recording.hh::fillCandidates` three-pass loop**
  ([modules/Lambda/Recording.hh](../modules/Lambda/Recording.hh))
  calls `Record::resetAllCounts`, then per-particle fill, then
  `Record::countAll`. Combine into one pass with a state machine, or
  document why three is the right choice.
- **`Histogram::write` and `writeToDir` are near-twins**
  ([utils/Record/Histogram.hh](../utils/Record/Histogram.hh)) —
  identical except for `dir->cd()` placement. Parameterize or drop one.
- **Limits — struct-init defaults fallback** (REVIEW §2): make
  `extractPhysics`'s missing-property error path seed defaults from
  `Physics::ParticleTraits` instead of throwing.

---

## Future direction (not yet planned)

Possible next-slice candidates the user has flagged in chat or the
author considers natural follow-ups. None are currently in execution.

- **`Lambda::Module` class** — own `Parameters` + `RootArray` +
  per-event handlers. Drivers would shrink further:
  ```cpp
  Lambda::Module lambda;
  Lambda::configure(lambda, writer, configPath);
  probe.run([&](const Probe::Event& ev, int tid){ lambda.analyse(ev, tid); });
  ```
  Requires updating `AnalysisContext` / `GenerationContext` to hold a
  `Lambda::Module&` instead of separate `RootArray& + Parameters&`.
  Subsumes REVIEW §1 (context unification) by making it irrelevant.
- **Investigation A** — sub-namespacing under `Probe`
  (`Probe::TreeControl`, `Probe::LeafControl`, `Probe::EventControl`).
  Design note first; code change only if the readability win is
  substantial.
- **Watch dissolution** — the lock-free `Watch` (Batch06) is now small
  enough that absorbing it directly into `AsyncLogger` (no separate
  type) would remove one indirection. Currently kept as a struct
  because handlers reference `ctx.logging.iEvent` etc. directly.

When any of these become an active slice, a new per-batch plan goes into
`docs/plans/` alongside [COMPLETED.md](plans/COMPLETED.md).
