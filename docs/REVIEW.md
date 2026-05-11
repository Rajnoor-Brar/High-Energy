# Review — current backlog

Updated: 2026-05-10.

This review supersedes the prior post-Batch07 backlog. `Probe::ProbeParallel`
and `Record::Writer` have been overhauled. Lambda no longer owns ROOT output;
it declares records into Writer and submits queued fill requests. Active
investigation around thread-count scaling lives in
[Issues.md](Issues.md); items here are expansions, alterations, and
improvements that are not the immediate scaling fight.

Companion docs:

- [CGPTsummary.md](CGPTsummary.md) — condensed design context for the overhaul.
- [MAP.md](MAP.md) — current file map and runtime ownership.
- [DataFlow.md](DataFlow.md) — current TOML/config flow.
- [Issues.md](Issues.md) — active performance-scaling investigation.

## Item map

- §1 Probe expansions/improvements
- §2 Writer expansions/improvements
- §3 Monitor and standardised Timer classes (answer to chat question)
- §4 Lambda analysis-loop tightening
- §5 Config / threading split (also referenced from Issues)
- §6 Cleanup after stabilization
- §7 Lower-priority backlog retained from older review
- §8 Non-issues for now

---

## §1 Probe expansions/improvements

### 1.1 Wire `[probe].callback_mode` and `[probe.index]`

`Probe::ProbeParallel` already supports both `CallbackMode::CollectorThread`
and `CallbackMode::WorkerThread` via `setCallbackMode`. Default is
`CollectorThread`. Currently the only way to flip it is a manual call from
the driver, which is exactly the kind of magic-knob the configure facade is
supposed to remove. Wire `[probe].callback_mode = "WorkerThread" |
"CollectorThread"` through `Config::configureProbe` →
`probe.setCallbackMode(...)`.

`[probe.index]` already exists in `configs/Lambda_Reconstruction.toml`
with `sorted`, `ascending`, `monotonic` fields, but `Probe::buildIndexSpecs`
hardcodes the result as `Ascending`/dense/grouped. Either parse the section
into the constructed `IndexSpec` array, or remove the section from sample
configs until it has meaning. Sparse/unordered/ungrouped indexed input is
explicitly listed as a deferred Probe feature; document the limitation
inline.

### 1.2 Vector-stream `CollectorThread` support

`ProbeParallel::run` throws on `StreamType::Vectors + CollectorThread`.
There is no fundamental obstacle: the same queue plumbing works with the
vector readers. Land it together with 1.1 so the callback-mode switch is
total.

### 1.3 Tighten queue-capacity heuristic

`configureProbe` sets the default capacity as
`std::max<std::size_t>(threadCount_, 10 * threadCount_)`, where the second
term always wins. Either intentionally cap at `10 * threadCount_` and drop
the `max` call, or pick a more deliberate heuristic (e.g. `2 *
threadCount_` for low memory profiles, or a configurable
`[probe].queue_capacity`). The current expression reads like a transcription
artefact.

### 1.4 `progress_` counters race with `stats()` reads

In `WorkerThread` mode, `progress_[t]` is mutated by worker thread `t`
without an atomic and without holding `queueMutex_` (workerThread path
increments inside the worker lambda directly). `stats()` reads the same
vector under the mutex. The values are advisory, so this is a benign race
for diagnostics, but it should be either an `std::vector<std::atomic<size_t>>`
or documented as advisory. In `CollectorThread` mode `progress_` is updated
inside `pushQueuedEvent` under the mutex; the two paths should agree.

### 1.5 Drop `runParallel` compatibility shim

`runParallel` ([utils/Probe/Parallel.hh:506–516](../utils/Probe/Parallel.hh))
is a thin compat wrapper that constructs a `ProbeParallel` per call,
forces `WorkerThread` mode, and forwards. New code should use
`ProbeParallel` directly so callback mode and stats are explicit.
Remove the shim once test/tooling callers migrate.

### 1.6 Better partition diagnostics

`prepareEntryBounds` throws `"Index branch ... is not ascending; CollectorThread
event bounds require grouped ascending data"` from a deep loop with no
information about which row triggered the violation. Include the offending
row index, branch name, and the previous/current value so users can find
the bad input file region quickly.

### 1.7 Probe stats: per-worker rates and per-stream timings

`stats()` reports `produced`, `consumed`, and per-worker `progress_`
counts but no time. After §3 lands, attach a `Monitor::Timer` to:

- per-worker event-build cost,
- per-worker queue-push wait,
- collector pop wait,
- collector callback dispatch.

These should publish into the timer registry (no special Probe console
output) so investigations from Issues §1 can read them directly.

### 1.8 Sparse / unordered indexed support

Listed as a deferred feature in `CGPTsummary.md`. Concrete shape:
when `[probe.index].sorted = false` or `monotonic = false`,
`prepareEntryBounds` falls back to a per-key map rather than a single-pass
ascending scan. Memory cost: `O(nEvents)` for the index map. Acceptable for
the typical 10⁷-event workload.

### 1.9 `EventStream` is per-worker; consider a stable-handle option

`EventStream` opens its own `TFile` per worker. ROOT thread safety
requires this. ROOT's `TThreadedObject<TFile>` would let workers share a
configured handle while ROOT issues per-thread copies underneath; worth
prototyping if file-open cost shows up in Timer data.

### 1.10 Compatibility shim's exception aggregation

`runParallel` shim and `runWorkerThread` rethrow only the first worker
exception. If multiple workers fail (a typical pattern when input is
malformed), the second/third diagnostics are lost. Aggregate into an
exception chain or accumulate `what()` strings and rethrow a composite.

---

## §2 Writer expansions/improvements

### 2.1 Multi-lane scribe (only after measurement)

The single-scribe design is correct for ownership. If `writer.stats()`
shows growing backlog and producer block, fan out by record-group ownership.
Safe shape:

- assign each `RecordKey` (particle group, hist, graph, profile, tree) to
  exactly one lane;
- one scribe thread per lane drains its private grand-queue;
- a final-write barrier joins all lanes before
  `Meta::writeAbout`/`outFile_->Write/Close` runs single-threaded;
- `checkpoint` becomes a barrier across all lanes (use the existing
  `BarrierState` pattern).

Per-object write order is preserved within a lane. The shared `outFile_`
is touched only at file open, checkpoint barrier, and finish — none of
which overlap producer fills. ROOT object creation (currently before
`start()`) does not need to change.

### 2.2 Move-aware fill APIs

`fillParticleEvent` accepts `std::initializer_list<ParticleFillView<Basis>>`
where each view holds `const std::vector<Physics::Lorentz>&`. The Writer
copies into `ParticleGroupFillRequest::particles`. For events with very
large candidate vectors this copy is unnecessary. Add an
`fillParticleEventMoved` (or rvalue-ref overload) that takes
`std::vector<Lorentz>&&` per group. Lambda's `Recording::fillCandidates`
can then move from the freshly-built `Candidates` struct.

### 2.3 Tree-row batching

`fillTree` enqueues one row per call. The data-generation driver writes one
`event_index` row per particle, so a 50-proton + 50-pion event submits 100
tickets. Batch by submitting `std::vector<TreeRowRequest>` per logical event,
or by a `fillTreeRows` API that takes a span of branch-value tuples. Reduces
queue pressure proportionally.

### 2.4 Pre-allocated payload pool

Per-event allocations: `ParticleRequest::groups`, each
`ParticleGroupFillRequest::particles` vector, plus the `QueueTicket`. A
small per-thread free-list pool would avoid the steady-state allocator
churn. Probably not the dominant cost today, but cheap to land once Timer
data exists.

### 2.5 Per-lane backlog in `stats()`

`writer.stats()` reports total `backlog`. Once §2.1 lands, expose per-lane
backlog. Even before §2.1, exposing per-lane queue size makes "particle
fills are the slow lane" obvious without instrumentation.

### 2.6 Auto-checkpoint policy

Pythia driver currently calls `writer.checkpoint(eventIndex)` on
`asyncLogger.checkInterval()` boundary. The Probe-driven Lambda
reconstruction does **not** call `writer.checkpoint` at all (see
`modules/Lambda.hh::rootAnalysis`). Either the Probe path should call it on
the same interval, or checkpoint policy should move into Writer (e.g. a
`writer.setCheckpointInterval(N)` and the scribe self-triggers based on
`consumed_`). Self-triggering is cleaner because it avoids producer-thread
contention on a "should I checkpoint now?" path.

### 2.7 Move ROOT object creation onto the scribe

Today, `declareParticleGroup`/`declareParticle*` create `TH1D`/`TH2D`/
`TTree` on the calling (setup) thread before `start()`. ROOT thread safety
makes this fine, but it means the `outFile_->cd()` calls and ROOT-internal
state mutations are not all funnelled through the same thread that does
mutation later. Cleaner to enqueue declaration tickets and let the scribe
realise them at `start()` time. Low-priority cosmetic.

### 2.8 Mark `meta()` access window explicitly

`writer.meta()` returns a non-const `Meta::Record&`. Drivers mutate it
between the event loop and `writer.finish()`. After `finish()`, the
scribe touches `meta_` inside `Meta::writeAbout`. There is currently no
synchronisation guarding the producer→scribe handoff because finish() is
itself a barrier — but the guarantee is implicit. Either document the
"mutate metadata before finish, no exceptions" rule on the accessor, or
provide a `Writer::updateMeta(std::function<void(Meta::Record&)>)` that
the scribe applies on its thread.

### 2.9 Particle tree branch validation

`fillParticleTree` asserts `tree.properties.size() == tree.branches.size()`
mid-event. That should be a declaration-time invariant verified once at
`declareParticleTree` exit, not a per-fill check.

### 2.10 String/Other branch types

`requireNumeric` rejects `DataType::String` and `DataType::Other` for
hists/graphs/profiles. `RootUtil::DataType` includes string but Writer
has no string-branch path. Either add it via `BranchBuffer<std::string>`
+ ROOT `string` leaf list, or document that only numeric trees are
supported.

### 2.11 `accepting_` semantics during `finish()`

`pushFinish` sets `accepting_ = false` before pushing the finish ticket
and notifies `queueNotFull_`. Producers blocked in `pushNormal` wake and
re-evaluate `throwIfCannotAcceptLocked`, which throws "writer is no
longer accepting requests." A producer can therefore see a spurious
exception when finish() races with the last fill. The exception is
correct (the fill is rejected), but the message reads like a programmer
error. Consider a separate `WriterClosed` exception type so callers can
distinguish "you closed too early" from "scribe died."

### 2.12 Record ordering across lanes

The grand queue preserves global FIFO. With multi-lane scribes (§2.1), a
hist-fill and a particle-fill submitted from the same producer call are
not guaranteed to apply in submission order across lanes. Document this
in the API: per-`RecordKey` order is preserved; cross-lane order is not.
Most analyses don't care, but graphs that span objects in different
lanes will need a barrier.

---

## §3 Monitor: standardised Timer classes

### 3.1 Current `BlockTimer` is broken in three ways

`utils/Monitor/Timer.hh` currently defines `BlockTimer` (in the global
namespace, not `Monitor`). Per instance:

1. opens `output/timer.log` in append mode in the **constructor** (one
   `std::ofstream` open syscall per construction);
2. writes the duration in milliseconds in the **destructor** with no label,
   so the file is a column of unlabeled numbers;
3. holds the `name_` member but never writes it.

It is also used inside
[`modules/Lambda.hh::rootAnalysis`](../modules/Lambda.hh) as
`BlockTimer timer("Whole Analysis");` — i.e. one file open + one file
write per event. Under multi-threaded reconstruction this is a serialised
I/O dependency and probably a real component of "scaling does not follow
nThreads." Remove or replace before benchmarking.

### 3.2 Proposed `Monitor::Timer` family

Self-sufficient, independent of `AsyncLogger`, can be enabled/disabled
without rebuilding, and produces both wall and CPU time per labelled
region.

```cpp
namespace Monitor {

    // Per-thread accumulated stats per label.
    struct TimerStats {
        std::string  label;
        std::uint64_t hits        = 0;
        std::uint64_t wallNanos   = 0;
        std::uint64_t cpuNanos    = 0;
        std::uint64_t minWallNs   = std::numeric_limits<std::uint64_t>::max();
        std::uint64_t maxWallNs   = 0;
    };

    // Singleton sink. Aggregates per-thread per-label stats; emits a CSV
    // when dump() is called (e.g. from writer.preCloseHook).
    class TimerRegistry {
      public:
        static TimerRegistry& instance();
        void record(const char* label,
                    std::uint64_t wallNs,
                    std::uint64_t cpuNs);
        void dump(const std::string& path) const;       // CSV
        std::vector<TimerStats> aggregated() const;     // for in-process inspection
        void clear();
        void setEnabled(bool on) { enabled_.store(on, std::memory_order_release); }
        bool enabled() const     { return enabled_.load(std::memory_order_acquire); }
      private:
        // thread_local map<label,TimerStats*> avoids cross-thread contention;
        // dump() merges by label.
    };

    // RAII per-block timer.
    class ScopeTimer {
      public:
        explicit ScopeTimer(const char* label);
        ~ScopeTimer();
        ScopeTimer(const ScopeTimer&)            = delete;
        ScopeTimer& operator=(const ScopeTimer&) = delete;
      private:
        const char* label_;
        std::chrono::steady_clock::time_point wallStart_;
        std::uint64_t                          cpuStartNs_;   // CLOCK_THREAD_CPUTIME_ID
    };

    // Manual start/stop for non-scoped use.
    class ManualTimer { /* same registry sink */ };

}
```

Design points:

- **No file I/O on the hot path.** `ScopeTimer` writes into a thread-local
  bucket; `dump()` is called once at shutdown.
- **Thread-local storage** removes cross-thread contention. The registry
  merges thread-local maps in `dump()`.
- **Wall + CPU.** `clock_gettime(CLOCK_MONOTONIC)` for wall;
  `clock_gettime(CLOCK_THREAD_CPUTIME_ID)` for per-thread CPU. The ratio
  reveals whether a hotspot is CPU-bound or stalled (lock wait, I/O wait).
- **Compile-time off-switch.** A `MONITOR_TIMERS_OFF` macro turns
  `ScopeTimer` into an empty-body class so production builds pay nothing.
- **Self-sufficient.** The registry owns its enable flag and dump path.
  No dependency on `AsyncLogger`. The Writer's `preCloseHook` is a natural
  place to call `TimerRegistry::instance().dump(paths.logDirectory + "/timers.csv")`,
  but the registry has no compile-time dependency on Writer.
- **Cheap call site.** `Monitor::ScopeTimer t{"reconstructCandidates"};`
  is one line, no std::string construction (label is `const char*`).

### 3.3 First labels to instrument

Once the class lands, the Probe/Writer scaling investigation
([Issues.md §1](Issues.md)) wants:

- `rootAnalysis` total
- `reconstructCandidates`
- `writer.fillParticleEvent` enqueue
- `writer.applyParticleRequest` (scribe side)
- `Probe::EventStream::next` (per worker)
- `Probe collector pop wait`
- `AsyncLogger::publish` and `publishThreadStats` per call
- `writer.finish`

Wall+CPU on each of these answers the bulk of the open performance
questions without further infrastructure.

### 3.4 Replace the existing `BlockTimer`

After 3.2 lands:

- delete `utils/Monitor/Timer.hh`'s `BlockTimer` class;
- delete its include and the `BlockTimer timer("Whole Analysis");` line in
  `modules/Lambda.hh::rootAnalysis`;
- delete the commented-out `BlockTimer` line in
  `modules/Lambda/Reconstruction.hh::reconstructCandidates`;
- replace any retained call sites with `Monitor::ScopeTimer`.

### 3.5 Other Monitor improvements

- `AsyncLogger::publish` and `publishThreadStats` both lock `mutex_` and
  are called twice per event. Move the snapshot mutation into atomics or
  per-thread buffers and have `runLoop` drain on a tick rather than on
  every publish.
- `ConfigAid.hh` accepts `[monitor]`, `[log]`, `[logging]` aliases. After
  configs migrate, drop the aliases and keep only `[monitor]`.
- `terminalRefreshInterval` defaults to 60 s on `start(bool)` and 300 s on
  `initialise(writer)` — pick one and document.

---

## §4 Lambda analysis-loop tightening

These are referenced from [Issues.md §1](Issues.md) as suspects #1; they
also stand alone as code-quality improvements.

- `rootAnalysis` copies `ev[label]` into local `std::vector<Lorentz>`. Use
  const refs; the `Probe::Event` lives for the duration of the synchronous
  callback.
- `reconstructCandidates` computes `cosTheta(...)` (boost-to-CM + dot) on
  every pair before checking the cheaper invariant-mass cut. Reorder so
  mass cut runs first; only surviving pairs pay for the boost.
- `lambda.M()` is called twice per pair for the mass cut. Cache once.
- `result.unvalidated.push_back(lambda)` materialises every proton×pion
  pair before any filtering. For a 50p × 50pi event that's 2500 entries.
  Reserve and document the worst-case size; if `unvalidated` is only ever
  used for the mass-distribution histogram, consider streaming it
  (one fillHist1D per pair) and dropping the staging vector entirely.
- `Particle::lambda` is a full `Lorentz` copy; only `lambda` is needed
  later. Acceptable, but if reconstruction cost dominates, `Particle`
  could store an index pair plus `massDiff` and rebuild the Lorentz on
  selection.
- `protonsTaken[candidate.protonIndex] && pionTaken[candidate.pionIndex]`
  greedy-match loop is fine; flag if profiling shows it.

---

## §5 Config / threading split

(Cross-referenced from [Issues.md](Issues.md) §3 and
[DataFlow.md](DataFlow.md).)

Move from `[events].nThreads` (a single global key) to per-pool keys:

```toml
[probe]
nThreads      = 8
callback_mode = "WorkerThread"

[pythia]
nThreads = 8

[record]
writer_threads        = 1     # multi-lane Writer §2.1 lifts this
writer_queue_capacity = 1024
```

Migration:

- keep `[events].nThreads` as fallback during transition;
- Probe prefers `[probe].nThreads`, then `[events].nThreads`, then auto;
- Pythia prefers `[pythia].nThreads`, then `[events].nThreads`;
- Writer reads the new keys; default to single scribe;
- `_Lambda_Parallel.cc` should apply the resolved Pythia thread count
  (currently it does not; `_Lambda_Data.cc` does);
- after `[probe].callback_mode` lands (§1.1), drop manual
  `probe.setCallbackMode` calls from drivers.

---

## §6 Cleanup after stabilization

- `utils/Record/Types.hh` and `utils/Record/Histogram.hh` still retain
  legacy `RootObjects` / `RootArray` compatibility helpers. They no
  longer appear in active Lambda drivers, but keep until tests and any
  downstream callers are checked. Then delete with the corresponding
  `Record/Histogram.hh::write*` helpers.
- `utils/Probe.hh` umbrella's doc-comment lists a `ProbeParallel.hh`
  subfile. The class actually lives in `Probe/Parallel.hh`. Either rename
  the file to match the doc, or update the doc to match the file. The
  symbol path users `#include` is `Probe.hh` either way.
- `[record].save_checkpoints`, `save_log_threads`, `save_heartbeat`,
  `save_final_log` appear in sample configs but no code reads them.
  Either wire each one or remove from the templates and from
  [DataFlow.md](DataFlow.md).
- `_Lambda_Reconstruction.cc` has not been updated to switch callback
  mode after Writer overhaul. Keep tracked alongside §1.1.
- `Monitor::configureMonitor` currently runs before `[events]` is parsed
  in `Config::configure` (Probe overload). Pacing's `barInterval`
  derivation may use the default event count. Either move
  `configureMonitor` after the probe configure, or have it lazily
  recompute pacing the first time `start(writer)` is called.
- `Lambda::Parameters::thetaTolerance` is read from TOML and immediately
  consumed by `cosThetaTolerance = std::cos(thetaTolerance)`; nothing
  downstream reads `thetaTolerance` again. Kept for log readability;
  document or drop.

---

## §7 Lower-priority backlog retained from older review

- `Config::LimitAid::resolveLimitsPath` silently expands bare names into
  `configs/<name>.toml`; print the resolved path on first read.
- `AsyncLogger::runLoop` still moves several `std::optional<...>` actions
  across one lock boundary. A small action queue would be easier to
  extend.
- `tests/run_all.sh` should report all failing tests instead of stopping
  at the first failure (`break` at line 30).
- `Histogram::write` / `writeToDir` legacy helpers in
  `utils/Record/Histogram.hh` are near-duplicates. Remove with §6's
  `RootArray` compatibility cleanup.
- Investigation A (sub-namespacing under `Probe`) — design note before
  any code change. Defer until file-level reorganisation has another
  reason.

---

## §8 Non-issues for now

- Replacing ROOT TFile output with RNTuple.
- Disabling ROOT thread safety as a scaling shortcut.
- C++20 / 23 migration.
- Cosmetic axis-label, README, or comment-style passes.
- Snake_case ↔ camelCase sweep on TOML keys / `Config::Watch`.
- Splitting the long `*Limits.toml` files in `configs/defaults/` and
  `configs/`.
- Async I/O on writes.
- Pre-compiled headers (PCH).
