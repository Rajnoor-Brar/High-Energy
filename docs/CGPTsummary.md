# Condensed Agent Context: docs/Chat

This file summarizes `docs/Chat/*.md` for agents that need maximum context with
minimal reading. The Chat docs are design and migration notes for the Probe
parallel event reader and the Record Writer overhaul. Treat them as historical
planning context: always inspect current code before editing, because parts of
the plan may already be implemented.

## Source Documents

- `docs/Chat/ProbeOverhaul.md`: short plan for the new `Probe::ProbeParallel`
  shape, collector queue, event partitions, config mirroring, and tests.
- `docs/Chat/Probe_Inspection.md`: detailed status/risk review after the Probe
  overhaul. It explains why Writer must change before Lambda callbacks can
  safely run as true worker-thread analysis.
- `docs/Chat/WriterSketch.md`: architectural sketch for moving all ROOT output
  ownership and mutation into `Record::Writer`.
- `docs/Chat/WriterPlan.md`: concrete implementation plan, public API shape,
  queue/scribe details, migration slices, tests, and acceptance criteria.

## Core Change

The intended system boundary is:

- `Probe` reads input ROOT data and builds `Probe::Event` objects.
- Lambda modules do physics reconstruction and declare desired output records.
- `Record::Writer` owns every output ROOT object and is the only normal code
  path that mutates, writes, closes, or deletes those objects.
- Analysis callbacks enqueue typed fill requests. They must not call
  `TH1::Fill`, `TTree::Fill`, `TGraph::SetPoint`, etc. directly.
- Writer's scribe thread drains queues in order and performs all ROOT output
  mutation, checkpoint writes, final writes, and fatal writes.

The old architecture had Lambda owning `RootArray` / `RootObjects`, counters,
histograms, and data-generation trees while `Record::Writer` mostly owned paths,
metadata, file open/write/finalize behavior, and a broad `recordingScope()` lock.
That split caused unclear ROOT ownership, serialized callback work, checkpoint
races, and fatal-write capture of external object containers.

## Probe Context

`Probe::ProbeParallel` was reshaped to own probe configuration and execution:
input path, particle specs, index specs, stream type, thread count, event count,
event range, partitions, per-worker entry bounds, queue state, callback mode,
progress, and stats.

Important Probe behavior:

- Default callback mode is `CallbackMode::CollectorThread`.
- Workers read/build `Probe::Event`; a bounded FIFO sends events to one
  collector thread; the collector serially invokes the analysis callback.
- `CallbackMode::WorkerThread` remains for direct worker callbacks and is what
  the old `runParallel` compatibility shim uses.
- Event count resolution order is explicit config, ROOT metadata, then fallback
  scan of index keys/vector entries.
- Indexed event streams precompute logical event partitions and per-worker entry
  bounds. Vector streams are supported only in worker-thread mode for v1.
- Indexed mode assumes ascending, dense, grouped event-index branches. Sparse or
  unordered index metadata is a deferred feature.
- CollectorThread fixes output correctness for old shared ROOT output, but it
  serializes Lambda callback execution. True callback parallelism needs the
  Writer overhaul first.

The Probe docs warn that remaining performance limits are likely serial
collector callbacks, candidate materialization cost, ROOT I/O behavior, static
partitions, monitor overhead, and old output ownership. Increasing thread count
alone is not a real fix.

## Shared ROOT Types

The Writer plan introduces shared ROOT value/type support in
`utils/Utility/RootTypes.hh` so `Probe` and `Record` do not duplicate branch type
logic.

Expected concepts:

- `RootUtil::DataType`: ROOT-compatible scalar/string type enum.
- `RootUtil::Value`: typed value variant used in request payloads.
- Helpers such as `typeName`, `leafListSuffix`, `detectBranchType`, and
  `toDouble`.
- `Probe::BranchType` and `Probe::BranchControl` should bridge to this shared
  type layer without breaking existing Probe configs.
- `toDouble` is for numeric histogram/graph/profile fills; strings and other
  non-numeric values should throw when used as numeric fill values.

## Record Identity And Branch Buffers

Writer records are identified by typed enum domains, not plain strings or raw
integers. The plan uses:

- `Record::RecordKey { std::type_index domain, int64_t value }`
- `Record::keyOf(enumValue)` to preserve enum domain identity
- Hash/equality that keep two different enum classes with the same underlying
  value distinct

Branch buffers are required because ROOT branches need stable addresses:

- `BranchBufferBase`
- `BranchBuffer<T>`
- `BranchRecord`

Explicit trees can mix branch types, for example `event_index/I` plus
`Energy/D`, `pX/D`, `pY/D`, `pZ/D`. Particle trees are simpler and use fixed
numeric branches derived from particle properties.

## Writer Public Shape

Declarations happen before `writer.start()`. Fill/checkpoint/finish happen after
start. Writer is noncopyable/nonmovable. Keep C++17; do not rely on `std::span`.

Declaration APIs planned/expected:

- `declareParticleGroup`
- `declareParticleCount`
- `declareParticleHist1D`
- `declareParticleHist2D`
- `declareParticleGraph`
- `declareParticleProfile`
- `declareParticleTree`
- independent `declareHist1D`, `declareHist2D`, `declareGraph`,
  `declareProfile`, and `declareTree`

Fill/lifecycle APIs planned/expected:

- `fillParticleEvent`
- `fillHist1D`, `fillHist2D`, `fillGraph`, `fillProfile`, `fillTree`
- `start()`
- `checkpoint(eventIndex)`
- `finish(eventCount)`
- `fatalWrite(eventCount, timeout)`
- queue capacity/stats accessors

Temporary compatibility for old `RootArray` APIs is acceptable only during
migration. Final Lambda drivers should not construct or pass `RootArray`.

## Writer Internal Model

Writer owns registries for:

- particle-derived groups and objects
- particle counts and candidate counters
- particle histograms, graphs, profiles, and trees
- independent histograms, graphs, profiles, and explicit trees
- branch buffers
- output file, directories, paths, histogram config, metadata, and pre-close
  hooks

Particle event application is ordered per logical event:

1. For each submitted particle group, reset the group candidate count.
2. For each particle, fill declared particle histograms, graphs, profiles, and
   tree branches.
3. After the group is processed, fill the group count histogram once.

Independent requests map directly to one object mutation:

- 1D/2D histograms convert values to numeric scalars and call ROOT fill.
- graphs append with an owned `nextPoint` counter.
- profiles fill numeric x/y.
- explicit tree rows set branch buffers and call `TTree::Fill`.
- tree rows should provide exactly all declared branches unless current code
  intentionally chose a different validation rule.

## Queue And Scribe Rules

The plan uses separate payload queues plus one grand queue of tickets:

- payload lanes hold request bodies, such as particle events, hist fills, tree
  rows, barriers, checkpoint, finish, and fatal requests.
- the grand queue preserves global request ordering.
- bounded capacity applies to the grand queue.
- one mutex plus condition variables coordinates producers and the scribe.
- never enqueue a grand-queue ticket without the matching payload already
  present.

Producer threads may call fill APIs concurrently. They only copy/allocate
payloads and push queue requests. They never mutate ROOT output objects.

The scribe thread:

- is the only normal thread that mutates output ROOT objects;
- processes tickets in global FIFO order;
- owns checkpoint/final/fatal writes;
- stores exceptions and propagates them to `finish()`, `checkpoint()`, and
  future producer calls.

Fatal write should bypass normal queue capacity and wake blocked producers so
they fail instead of deadlocking behind a full queue. Fatal write cannot recover
if the scribe is already stuck inside a ROOT call; it only avoids queue-level
deadlock.

## Write, Checkpoint, Finish

Writer should have non-template owned write paths, not templated methods that
need external `RootArray` references.

Rules from the plan:

- `checkpoint(eventIndex)` is an ordered barrier: all earlier queued fills must
  be applied before checkpoint output is written.
- `finish(eventCount)` drains prior requests, writes final output and metadata,
  closes the `TFile`, and joins the scribe.
- `fatalWrite(eventCount, timeout)` requests a best-effort emergency write
  without relying on external ROOT object containers.
- Histograms are cloned before scaling, preserving existing
  `Record::scaleAndWrite` behavior.
- `TH1`-like objects use `histScale / nEvents` when `nEvents > 0`.
- Width scaling remains for 1D histograms where the existing code expects it.
- Trees are skipped during checkpoint unless explicitly enabled later.
- Metadata mutation should happen before `finish()`.
- `TFile::Write`, `TFile::Close`, and file deletion must happen only on the
  scribe path.

## Lambda Migration Target

Reconstruction target:

- `Lambda::configure(parameters, writer, configPath)` loads module parameters
  and declares output records into Writer.
- `Lambda::AnalysisContext` no longer stores `RootArray&`.
- `Lambda::fillCandidates` becomes a Writer adapter that calls one
  `writer.fillParticleEvent<HistogramSet>(...)` per logical event.
- `Lambda::rootAnalysis` and `Lambda::pythiaAnalysis` reconstruct candidates and
  enqueue Writer fill requests without `recordingScope()`.
- Drivers call `writer.start()` after declarations and before event loops.
- Drivers call `writer.finish(eventCount)` after metadata updates.

Data-generation target:

- Replace Lambda-owned `DataObjects`, `TTree*`, branch arrays, and `treeMutex`
  with Writer-owned explicit trees.
- Preserve tree names expected by Probe: `Protons`, `Pions`.
- Preserve branch names/types expected by Probe: `event_index`, `Energy`, `pX`,
  `pY`, `pZ`.
- Preserve any index-building pre-close hook by running it on the scribe before
  final file write/close, or by converting it into a Writer pre-close hook.

## Driver Lifecycle Target

The intended reconstruction flow is:

1. Configure `Probe`, `Record::Writer`, and `Monitor::AsyncLogger`.
2. Load Lambda parameters and declare Lambda output into Writer.
3. Bind Writer/logger hooks as needed.
4. Initialize logger from Writer paths/config.
5. Call `writer.start()`.
6. Run Probe and call Lambda analysis from callbacks.
7. Fill Writer metadata and integrity fields.
8. Call `writer.finish(asyncLogger.watch().nEvents)` or the correct actual
   event count.
9. Finish logger output after Writer final output exists.

The exact logger finalization call is less important than the ownership rule:
Writer final ROOT output must be complete before final terminal/log reporting
points at the output file.

## Monitor And Fatal Handling

`Monitor::AsyncLogger::initialise(const Record::Writer&)` can keep reading
writer paths and histogram config.

Fatal-stall handling should be logger-owned:

1. logger detects fatal stall;
2. logger writes emergency/fatal log state;
3. logger calls `writer.fatalWrite(eventCount, timeout)`;
4. logger reports the result and exits/finalizes.

The old pattern where `Writer::installFatalStallHandler` captures external
`RootArray&` should disappear. Monitor should not need direct access to ROOT
objects.

## Implementation Order From WriterPlan

1. Add shared `RootUtil` types and bridge Probe branch types.
2. Add `RecordKey`, branch buffers, object record structs, and focused tests.
3. Add Writer registries and declaration APIs.
4. Add request payloads, queue lanes, bounded queue behavior, scribe lifecycle,
   barriers, exception propagation, and stats.
5. Move checkpoint/final/fatal write logic into Writer-owned non-template
   methods.
6. Migrate Lambda reconstruction to Writer declarations and
   `fillParticleEvent`; remove callback-side `recordingScope()`.
7. Migrate Lambda data generation to Writer-owned explicit trees.
8. Move fatal-stall orchestration into Monitor.
9. Remove compatibility APIs once no callers remain.

Keep `make test` passing after each slice when practical.

## Tests To Preserve/Add

Important tests listed by the plan:

- `RootUtil::DataType` detection, suffixes, names, and value conversion.
- `RecordKey` equality/hash across different enum domains with same raw value.
- branch buffer value setting, branch declaration, and wrong-type throws.
- duplicate/missing declaration validation and declaration-after-start throws.
- concurrent producers, bounded queue drain/block behavior, and finish rejection
  of later fills.
- producer wake/throw after scribe exception.
- particle requests fill histograms/counts correctly.
- graph/profile appends/fills.
- explicit trees require declared branches and write rows correctly.
- checkpoint waits for earlier fills.
- finish waits for earlier fills and writes metadata.
- fatal write bypasses a full normal queue.
- Lambda smoke tests inspect final ROOT output after `writer.finish()`.
- data-generation output remains readable by Probe.

Manual/build checks requested:

- `make test`
- `make _Lambda_Reconstruction.exe`
- `make _Lambda_Parallel.exe`
- `make _Lambda_Data.exe`
- `make _Lambda_Test.exe`
- run small fixed Lambda configs across thread counts and compare output
  entries/integrals.

Test outputs should go to generated/ignored temp paths so test runs do not dirty
tracked logs or ROOT files.

## Acceptance Criteria

The overhaul is done when:

- `Record::Writer` owns all Lambda output ROOT objects.
- Lambda callbacks never mutate ROOT output objects directly.
- no module outside Writer owns output `TFile`, `TDirectory`, `TH1`, `TH2`,
  `TGraph`, `TProfile`, `TTree`, or `TBranch` objects.
- `writer.finish(eventCount)` writes and closes final output without external
  object containers.
- `writer.checkpoint(eventIndex)` is an ordered barrier over queued fills.
- fatal write no longer captures external `RootArray&`.
- final Lambda drivers do not construct/pass `RootArray`.
- tests pass and Lambda smoke output remains consistent.

## Known Risks And Guardrails

- The scribe serializes output mutation by design. This improves correctness but
  can become the throughput ceiling if output filling dominates runtime.
- Queue payloads copy particles or values. Very large candidate lists may need a
  move-oriented API later.
- ROOT string branches require special handling and tests.
- ROOT object creation currently may happen on the setup thread before
  `writer.start()`; moving creation to the scribe can be a later enhancement.
- During migration, old and new paths must not write the same ROOT object.
- Do not disable ROOT thread safety as a scaling shortcut.
- Existing user edits, especially in configs such as
  `configs/Lambda_Reconstruction.toml`, must be preserved.

## Fast Orientation For Future Agents

If you need to continue implementation, inspect current code first with searches
such as:

```sh
rg "RootArray|RootObjects|recordingScope|installFatalStallHandler|shutdown\\("
rg "fillParticleEvent|declareParticle|fatalWrite|checkpoint\\("
rg "RootTypes|RecordKey|BranchBuffer|QueueTicket|scribe"
```

If these old symbols remain in active source, use the implementation order above
to finish migration. If they remain only in docs or deliberate compatibility
stubs, focus on tests, cleanup, and current failing behavior rather than
re-implementing the plan from scratch.
