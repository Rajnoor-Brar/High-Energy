# Architecture — plan of plans

> Strategic plan for the next architectural sweep. Each item below names a
> direction, a decision (including rejections), the rough surface it touches,
> and what subordinate planning is required before execution. Implementation
> plans for each item are deferred to per-item docs (suggested filenames in
> each entry).
>
> Companion to [DataFlow.md](DataFlow.md) (current TOML→struct map),
> [REVIEW.md](REVIEW.md) (open backlog), [MAP.md](MAP.md) (file map),
> [ROADMAP.md](ROADMAP.md) (the previous, partially superseded phase plan).

---

## North star

**Config owns configuration; objects own state.** After the configure phase,
runtime objects (Pythia/Probe runners, the Record writer, the Monitor logger)
carry every field they need. `Watch` and `Register` shrink to whatever residue
is genuinely shared across object boundaries — and that residue may be small
enough that they cease to exist as named structs.

The canonical driver is **`_Lambda_Reconstruction.cc`**. Every restructuring
must leave it building, passing, and shrinking in line count. The other three
drivers (`_Lambda_Data.cc`, `_Lambda_Parallel.cc`, `_Lambda_Test.cc`) follow
the same pattern; where they diverge, they change.

Target shape of a driver `main()`:

```cpp
Probe::ProbeParallel  probe;       // or Pythia8::PythiaParallel pythia;
Record::Writer        writer;
Monitor::AsyncLogger  logger;

Config::configure(configPath, project, probe, writer, logger);

Lambda::Parameters phys;
Lambda::extractPhysics(configPath, phys, writer.histConfig());
Lambda::RootArray sets;
Lambda::declareObjects(sets, phys, writer.histConfig());

Record::FinalizerController finalizer(sets, writer, logger,
    [&]{ return Lambda::logString(phys); });
finalizer.installFatalStallHandler();

logger.start();   // marks startTime; no Config args
probe.run([&](const Probe::Event& ev, int tid){ Lambda::rootAnalysis(ev, tid, mtx, ctx); });

finalizer.setMeta(Record::Meta::capture(...));
finalizer.normalShutdown();
```

No `toml::parse_file` in the driver. No conversion glue (`toCollectionSpecs`)
in the driver. No `Watch&`/`Register&` threaded through call sites that don't
mutate them.

---

## Work items

Each item lists: **State** (today), **Decision**, **Touches**, **Depends on**,
**Subplan** (the per-item planning doc to produce when this item moves to
execution).

### W1. Stream-extract functions per object

- **State.** `Config::configuration` is a single function that fills `Watch` +
  `Register` from `[events]`, `[record]`, `[monitor]`, `[record.paths]`,
  `[record.file]` in one pass. `configurePythia`/`configureProbe` re-parse the
  TOML for their own section after calling `configuration`.
- **Decision.** Granularity is **per consuming object**, not per TOML section.
  TOML sections are an authoring convention; they should not dictate the C++
  decomposition. Introduce: `configureWriter(Writer&, ...)`,
  `configureMonitor(AsyncLogger&, ...)`, `configureProbe(ProbeParallel&, ...)`,
  `configurePythia(PythiaParallel&, ...)`. Each opens the TOML once internally
  (or accepts a parsed `toml::table&` from the facade — see W2 for the call
  graph). Lambda physics extraction stays separate
  (`Lambda::extractPhysics`) — it isn't a Config concern.
- **Touches.** `utils/Config.hh`, `utils/Config/Reader.hh`,
  `utils/Config/Defaults.hh`. Drop or thin `Config::configuration` once all
  consumers go through object-specific entry points.
- **Depends on.** W6 (Probe object), W7 (Writer object), W8
  (configureMonitor) — needs the target objects to exist first.
- **Subplan.** `docs/plans/Config_StreamExtract.md`.

### W2. Top-level `Config::configure` facade

- **State.** Drivers call `configureProbe` / `configurePythia` /
  `openOutputFile` separately, then construct `AsyncLogger` and
  `FinalizerController` with `Watch&`/`Register&` arguments.
- **Decision.** Two overloads:
  ```cpp
  Config::configure(path, project, Pythia8::PythiaParallel&, Record::Writer&, Monitor::AsyncLogger&);
  Config::configure(path, project, Probe::ProbeParallel&,    Record::Writer&, Monitor::AsyncLogger&);
  ```
  Internally: parse the TOML once, dispatch to the per-object configurators
  from W1. `Watch` and `Register` are no longer constructed by the driver — if
  they survive at all (see W9), they live inside `Writer` / `Logger`.
- **Touches.** `utils/Config.hh` (new entry points), all four drivers (drop
  `Watch`/`Register` locals).
- **Depends on.** W1, W6, W7, W8.
- **Subplan.** `docs/plans/Config_Facade.md`.

### W3. `collectionSpecs` lives inside `ProbeConfig` (then inside `ProbeParallel`)

- **State.** Driver calls `Probe::toCollectionSpecs(probeConfig)` and passes
  the result + `probeConfig.inputFile` + `eventCount` to `runParallel` as
  three separate arguments. `EventStream` takes the same three plus a key
  range.
- **Decision.** `configureProbe` produces a fully-compiled `ProbeConfig` that
  already contains `vector<CollectionSpec>` (the `ProbeParticle` intermediate
  is internal). When W6 lands, `ProbeConfig` is consumed by the
  `ProbeParallel` ctor and discarded; `ProbeParallel` owns the specs from
  there on. `runParallel` and `EventStream` accept `const ProbeConfig&` (or,
  after W6, are methods on `ProbeParallel`).
- **Touches.** `utils/Probe/ConfigAid.hh` (move conversion into a Probe ctor),
  `utils/Probe/Parallel.hh`, `utils/Probe/Event.hh`, `utils/Config/Types.hh`
  (extend `ProbeConfig` with the compiled specs; possibly drop `ProbeParticle`
  if W10 dissolves it).
- **Depends on.** W6 (target object); W10 (settles whether `ProbeParticle`
  disappears entirely).
- **Subplan.** Folded into `docs/plans/Probe_Object.md` (W6).

### W4. Event-count resolution moves into `configureProbe`

- **State.** `_Lambda_Reconstruction.cc:47–53` runs the two-tier fallback
  (`Probe::resolveEventCount` → `Probe::EventStream(...).nEvents()`) inline,
  mutating both `probeConfig.eventConfig.eventCount` and `logParams.nEvents`
  by hand.
- **Decision.** Move both fallbacks into `configureProbe`. After it returns,
  the resolved event count lives in one place inside `ProbeParallel`;
  `Watch::nEvents` either disappears (W9) or is set from the same source.
  **Subordinate question:** does `EventStream`'s ctor scan keys eagerly, or
  is it cheap? If eager, expose `Probe::countEvents(inputFile, specs)` that
  reuses the existing `BranchControl::scanIndexBranch` path without
  constructing the full `EventStream`. The W4 subplan must measure this
  before deciding.
- **Touches.** `utils/Probe/EventCount.hh` (extend), `utils/Config.hh`
  (`configureProbe` body), `_Lambda_Reconstruction.cc` (delete the two
  fallback blocks and the `<toml++/toml.hpp>` include).
- **Depends on.** W3 (ProbeConfig already carries compiled specs).
- **Subplan.** `docs/plans/Probe_EventCountResolution.md`.

### W5. Delete `Events::isPythia`

- **State.** Parsed but has zero readers (DataFlow.md confirms). Each driver
  picks its mode at link time.
- **Decision.** **Delete** the field, the `events.pythia`/`events.probe`
  TOML keys, and `readEventsSection`'s parsing of them. Reject the
  alternative ("single binary that branches on `isPythia`") — it doubles
  driver code paths to save a build target, and the two `_Lambda` modes
  pull mutually exclusive includes (Pythia8 vs Probe schema). Not worth it.
- **Touches.** `utils/Config/Types.hh`, `utils/Config/Reader.hh`, the
  TOML files in `configs/` (remove the dead keys).
- **Depends on.** Nothing.
- **Subplan.** None — small enough to execute without a per-item doc.

### W6. `Probe::ProbeParallel` (and possibly `ProbeSerial`)

- **State.** `runParallel` is a free function template taking five arguments
  (file, collections, scalars, callback, threads, eventsHint). State is
  juggled across the call site.
- **Decision.** Introduce `Probe::ProbeParallel` mirroring
  `Pythia8::PythiaParallel`:
  ```cpp
  class Probe::ProbeParallel {
      ProbeConfig cfg_;     // owns inputFile + compiled specs + resolved nEvents + nThreads
  public:
      ProbeParallel() = default;
      template <typename Cb> void run(Cb&& callback);   // uses cfg_; no extra args
  };
  ```
  Reject a separate `ProbeSerial` for now — `ProbeParallel` with
  `nThreads = 1` is functionally serial. Revisit only if a future need
  surfaces (e.g. deterministic test ordering that single-thread guarantees).
  REVIEW item 6 (`ScalarSpec` plumbing) folds in here: drop the unused
  `scalars` parameter as part of the same diff.
- **Touches.** New `utils/Probe/ProbeParallel.hh` (or extend `Parallel.hh`).
  `utils/Probe.hh` (umbrella). `_Lambda_Reconstruction.cc` (and
  `tests/test_rootAnalysis_smoke.cc`).
- **Depends on.** W3.
- **Subplan.** `docs/plans/Probe_Object.md`.

### W7. `Record::Writer` + thinner `FinalizerController` — IN PROGRESS

**Status (2026-05-02).** Steps 1–8 of `bots/current_plan.md` (the W7
subplan) landed:

- `Record::Paths` and `Record::HistConfig` exist (`utils/Record/Configs.hh`).
- `Record::Writer` exists (`utils/Record/Writer.hh`) and owns the open
  TFile + Paths + HistConfig + `Meta::Record`.
- `Record::Meta::capture` split into `mergeFromToml` / `mergeFromProbe` /
  `fillDerived` with **Probe > TOML > defaults** priority. The
  `[record.metadata]` silent-empty-string bug (DataFlow.md) is fixed.
- `Record::configureWriter` lives in `Record::` (not `Config::` — the
  layering call: keep Record→Config one-way; drivers already include
  `Record.hh`).
- All four drivers + smoke test migrated. `_Lambda_Data.exe` builds and
  runs (resolves REVIEW #1).
- `Lambda::extractPhysics`, `declareObjects`, `declareDataObjects` take
  `HistConfig&` / `Writer&`. `Monitor::Render` + `AsyncLogger::start` +
  `FinalizerController` + `pythiaAnalysis` all take `Writer&`.
- `Config::openOutputFile` deleted. `Register::outFile` and
  `Register::inputPath` fields deleted. The `reg.outFile` mirror in
  `configureWriter` deleted. No code outside the Config namespace reads
  `Register` anymore.
- Verified end-to-end: `_Lambda_Reconstruction.exe` produces a ROOT file
  with `About/dataset/name = "Lambda_MC_pp"` (sourced from
  `[record.metadata]` per the new TOML pass), and
  `parent_files = output/Lambda_Data/.../Lambda_Recons_7000GeV_10M.root`.

**Remaining (deferred to W9).** Residual `Register` fields used only by
`Config::Reader` parsing are still present as transitional scaffolding.
Full deletion + the parallel cleanup of `Watch::*_interval` fields is the
W9 task.



- **State.** `FinalizerController` owns the open `TFile*` (via `Register&`),
  the histogram sets, the meta record, four callbacks (`programLogBuilder`,
  `printStats`, `listChangedSettings`, `preCloseHook`), and the fatal-stall
  installer. It's load-bearing in three different ways at once.
- **Decision.** Split into:
  - `Record::Writer` — owns `TFile*`, the path templates, and the
    HistConfig fields (binCount, histScale, limits maps). Methods:
    `open(path)`, `write(sets, scale, nEvents)`, `close(preCloseHook)`,
    accessors for the path templates that `AsyncLogger` and `Meta::capture`
    need.
  - `Record::FinalizerController` — wraps `Writer` + `AsyncLogger` + the
    program-log/stat callbacks. Becomes responsible only for the shutdown
    choreography (fatal-stall handler, `terminalReport`, `outputLog`) and
    delegates the file work to `Writer::close`.
  Note: `preCloseHook` already exists on `FinalizerController` (currently
  filed under REVIEW #1 as a missing parameter, but the field was added —
  REVIEW #1 is now stale on that point and should be edited). The split
  here moves the hook to its more natural home on `Writer::close`.
- **Touches.** New `utils/Record/Writer.hh`. `utils/Record/Finalizer.hh`
  (slim down). All four drivers. REVIEW items 1, 11 (HistConfig split), 12
  fold in.
- **Depends on.** W9 (Register split / HistConfig extraction). Can be
  prototyped before W9 if Writer initially holds the existing `Register&`.
- **Subplan.** `docs/plans/Record_Writer.md`.

### W8. `configureMonitor(AsyncLogger&)`

- **State.** `AsyncLogger::start(Register&, Watch&)` reaches into `Register`
  for three path strings and into `Watch` for six pacing intervals.
- **Decision.** `Config::configureMonitor(AsyncLogger&, configPath, project)`
  extracts only what the logger needs (the three path strings + `RunPacing`
  intervals) and stores them inside the logger as private fields. After
  this, `AsyncLogger::start()` takes no arguments (or only a `TimePoint`
  for `startTime`). The `Watch::*_interval` fields disappear — they exist
  today only because Render.hh prints three of them in the log; that line
  becomes a `logger.echoPacing()` accessor.
- **Touches.** `utils/Monitor/Logger.hh`, `utils/Config.hh`,
  `utils/Config/Reader.hh` (new extractor or refactored `readLogSection`),
  `utils/Monitor/Render.hh` (echo lines).
- **Depends on.** W7 (Writer holds path templates that `configureMonitor`
  reads from).
- **Subplan.** `docs/plans/Monitor_Configure.md`.

### W9. Purge `Watch` and `Register`; redraw the residual

- **State.** `Watch` carries 14 fields mixing live counters, set-once
  pacing, and identity (serial/sr_padding). `Register` carries 18 fields
  spanning the open file, path templates, hist config, and a dead
  `inputPath`.
- **Decision.** After W6/W7/W8 land, audit which fields any object outside
  `Config` still reads. Expected residual:
  - **`RunCounters`** (the only mutable runtime state): `iEvent` atomic,
    `n_real_events` (made atomic — REVIEW item: drop `eventMutex_`),
    `start`, `elapsed`. Lives wherever the per-event handlers can reach
    it; candidate owner is `AsyncLogger` or a free `RunCounters` instance
    threaded only through `AnalysisContext`.
  - **`HistConfig`** (REVIEW #11): `binCount`, `histScale`, limits maps,
    `histLimitsFile`. Owned by `Writer` or extracted as a free struct
    consumed by `Lambda::declareObjects` and `Writer::write`.
  - **Path templates**: live inside `Writer`. Drivers no longer hold
    them.
  - **Identity** (`serial`, `sr_padding`, `serialStr`, `fileTitle`,
    `beamEnergy`): immutable after configure; keep as `const` accessors
    on `Writer`. The `Watch::serial`/`sr_padding` fields disappear
    (consumed by `readPathsAndFile`, then read once in two log lines —
    can be re-derived from `Writer::serial()`).
  - **Dead**: `inputPath` (use `ProbeParallel.cfg().inputFile`),
    `Events::isPythia` (W5), all `*_interval` Watch fields (W8).
- **Touches.** `utils/Config/Types.hh` (delete `Watch`/`Register` if
  reduced to nothing; otherwise rename to reflect what they actually
  hold), every consumer that reads what was deleted (audit via grep on
  the field names).
- **Depends on.** W6, W7, W8.
- **Subplan.** `docs/plans/Config_PurgeAudit.md`.

### W10. Type bleed across utils — collapse Config↔Probe duplication

- **State.** `Config::ProbeParticle` is a parallel description of what
  `Probe::ParticleSpec`/`CollectionSpec` already represents.
  `Config/ConfigAid.hh` already imports `Config::Types.hh` into Probe
  (Pipeline A allowed this). The duplication exists only because
  `readProbeSection` historically built into Config-owned types.
- **Decision.** Allow `utils/Config/*.hh` to `#include` other utils' type
  headers (`Probe/Types.hh`, future `Record/Writer.hh` types,
  `Monitor/Types.hh`) when doing so eliminates duplicated structs.
  Specifically: delete `Config::ProbeParticle`; have `readProbeSection`
  build `vector<Probe::CollectionSpec>` directly (re-using
  `BranchControl::detectType`). The `[probe]` parser becomes a thin
  TOML→`CollectionSpec` translator that lives wherever it reads best —
  most naturally `utils/Probe/ConfigAid.hh` (already exists), with
  `Config::configureProbe` as a one-line forwarder.
  General principle going forward: duplicating a type to avoid a Config
  → utils dependency is **not** preferred. The dependency direction
  Config → Probe/Record/Monitor is acceptable; the reverse (utils →
  Lambda module) is not.
- **Touches.** `utils/Config/Types.hh` (drop `ProbeParticle`),
  `utils/Config/Reader.hh` (`readProbeSection` rewrite or relocation),
  `utils/Probe/ConfigAid.hh` (gains the parser),
  `utils/Probe.hh` (umbrella).
- **Depends on.** W3, W6 (so ProbeParallel exists to consume the
  result).
- **Subplan.** `docs/plans/Config_TypeBleed.md` — also documents the
  layering rule for future contributors.

---

## Suggested execution order

```
W5  ── trivial; clears dead config first
W4  ── localised; doesn't depend on object split (ok before W6 if EventStream is cheap)
W6  ┐
W7  ├── parallel; create the three target objects
W8  ┘
W3  ── folds into W6
W10 ── after W3/W6 (needs ProbeParallel/CollectionSpec consumer ready)
W1  ── stream-extract per object; needs the objects to extract into
W2  ── facade on top
W9  ── final audit & purge once the picture is stable
```

W6/W7/W8 are the structural pivot; they can run in parallel branches if the
team has the bandwidth, with W2 as the join point. W1 collapses gracefully
into W2 if both are done by the same author.

---

## Decision log — proposals rejected or deferred

- **Single-binary driver branching on `events.pythia` (W5 alt b).** Rejected.
  Doubles include surface and runtime branching for a build-time concern.
- **`ProbeSerial` as a separate class (W6 alt).** Deferred. `ProbeParallel`
  with `nThreads=1` covers the case; revisit only if a deterministic
  serial path is actively needed.
- **Templatize `RootArrayT` to subsume `DataObjects` (ROADMAP item 2 alt 2).**
  Rejected in favour of `preCloseHook`, which is now in tree. W7 moves the
  hook from `FinalizerController` to `Writer::close` — same callback, better
  home.
- **Snake_case → camelCase sweep on `Watch`.** Out of scope; W9 may delete
  most of those fields anyway.
- **PCH (ROADMAP item 5).** Independent; stays in REVIEW backlog. Architecturally
  orthogonal to W1–W10.

---

## Cross-references

- TOML key inventory and abandonment table → [DataFlow.md](DataFlow.md).
- Per-item backlog entries (some superseded by this doc) → [REVIEW.md](REVIEW.md).
  After W1–W10 are filed as subplans, REVIEW items 1, 6, 11, 12, 14, 20, 21
  should be re-anchored to point at this file.
- Phase 4 plan → [ROADMAP.md](ROADMAP.md). Items 6/7 in that file
  (`Log`/`Root` rename and `Register` split) are subsumed by W7 and W9; mark
  them superseded when this plan begins execution.
