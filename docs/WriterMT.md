# WriterMT — multithreaded `Record::Writer` + per-section `thread_count`

Updated: 2026-05-11.  Plan-mode artifact for the next batch of work
following the xctrace finding that the single Writer scribe is the
real CPU floor (61% of total samples), not the read path.
Companion: [ROOTMT.md](ROOTMT.md).

## Context — why this work

The Phase 2 trace (`Launch__Lambda_Reconstruction.exe_2026-05-11_12.37.05`)
attributed time as:

| Thread | Samples | % | Identity |
| --- | --- | --- | --- |
| 12480 | 72 470 | **61%** | `Record::Writer` scribe |
| 1891  | 10 399 |   8.8% | `AsyncLogger` (printf) |
|     2 |  4 476 |   3.8% | main |
| 12421–12468 | ~3200 ea | ~22% combined | 8 flush workers |

Scribe-thread leaf frames inside `Writer::applyParticleRequest`:

```
14.5%  TH1::Fill
12.1%  log                          ← inside kParticleTraits::lambda
11.6%  TAxis::FindBin
10.4%  applyParticleRequest         (parent)
 5.8%  PxPyPzE4D::Eta
 3.5%  kParticleTraits::lambda      (other observables)
```

So the scribe is not just doing `TH1::Fill` — it's also computing the
per-fill observable (`M`, `Eta`, `log`-heavy kinematics) before the fill.
That entire computation is single-threaded today.  Reads are ~6.5% of
total samples; they are not the limiter.

**Goal:** push fill + observable computation into a worker pool with
per-worker histogram clones, merge at finalize.  Keep the simple
"one writer thread mutates the TFile" invariant by isolating the TFile
into a dedicated watchdog thread that handles checkpoint / finalize /
fatal — those are the only paths that touch the on-disk file.

**Non-goals** (this round):
- Logger throttling (user will adjust print interval manually if needed).
- Chunked Probe streaming (orthogonal; revisit if memory pressure
  shows up again).
- Eliminating ROOT global mutex on the read path (Phase 2 / ProbeIMT
  already established the workaround there).

---

## Phase 0 — TOML migration

Standalone change.  No behavior shift.  Ship and validate before
touching the Writer.

### 0.1 TOML surface

```toml
[probe]
thread_count = 4
input_file   = "..."
# (root_imt, splitting flags — unchanged for now)

[record]
thread_count       = 8
serial             = 37
sr_padding         = 2
bin_count          = 400
# (paths, file — unchanged)

[pythia]
thread_count = 8         # no functional change until Pythia drivers consume it

[monitor]
save_checkpoints    = false       # existed
save_log_threads    = false       # existed
save_heartbeat      = false       # existed
save_final_log      = true        # existed
checkpoint_interval = 100_000     # NEW; events between auto-checkpoints
heartbeat_interval  = 10_000      # NEW; events between heartbeat log entries
```

### 0.2 Removed keys

`[events].nThreads` — removed.  Loud parse error on encounter:

> "[Config] `[events].nThreads` was removed; set
> `[probe|record|pythia].thread_count` instead."

`[events].event_count` stays.

### 0.3 Hard-coded defaults

For every section's `thread_count`:

```
default = max(1, floor((hardware_concurrency - 2) / 3))
```

Logic: leave 2 cores for OS + interactive tasks, share the rest
across the three pipeline stages.

For the monitor intervals:

```
default checkpoint_interval = 100_000
default heartbeat_interval  = 10_000
```

### 0.4 File-level changes

| File | Change |
| --- | --- |
| `utils/Config/Types.hh` | Drop `Events::nThreads`.  Add `ProbeConfig::thread_count`, `PythiaConfig::thread_count`, new `RecordConfig::thread_count`, monitor interval fields. |
| `utils/Config/Reader.hh` | Drop `nThreads` parse from `[events]`.  Add per-section thread_count parsers.  Add `readMonitorSection` (rename of `readLogSection` is optional). |
| `utils/Config/Configure.hh` | Forward per-section thread counts to `probe.configureProbe(...)`, `writer.setRecordThreadCount(...)`, etc. |
| `utils/Probe/Parallel.hh` | Read `probe.thread_count`. |
| `utils/Probe/ParallelIMT.hh` | Read `probe.thread_count`. |
| `utils/Record/Writer.hh` | New setter `setRecordThreadCount(std::size_t)` (private member, set during configuration).  Used later in Phase 2; harmless no-op in Phase 0. |
| `configs/Lambda_Reconstruction.toml` | Migrated.  Remove `[events].nThreads`; add new keys per §0.1. |
| `configs/*.toml` (remaining) | Same migration. |
| `tests/fixtures/lambda_fixture.toml` | Same. |

### 0.5 Tests for Phase 0

- `test_record_writer.exe`, `test_probe_parallel.exe`, `test_rootAnalysis_smoke.exe`, `test_reconstructCandidates.exe` — must all still pass.
- Add a `Config::Reader` unit test that:
  - Parses a TOML with `[events].nThreads` and asserts a clear error.
  - Parses a TOML with only some sections setting `thread_count`; missing sections fall back to the hardware-derived default.

### 0.6 Phase 0 done when

- `make test` passes on the migrated TOMLs.
- `_Lambda_Reconstruction.exe` runs end-to-end against the migrated config (same behavior as today — scribe Writer, ProbeIMT).
- One commit, scoped strictly to TOML + Config plumbing.

---

## Phase 1 — Logger `countEvent` + watch sink

Standalone change.  Lays the foundation for the watchdog without
yet rewriting the Writer.

### 1.1 New API on `AsyncLogger`

```cpp
namespace Monitor {

class AsyncLogger {
public:
    // Atomic increment of watch_.iEvent.  Returns the new count.
    // If save_heartbeat / save_checkpoints are configured and the
    // count crosses an interval, pushes a WatchRequest through the
    // watch sink.
    std::size_t countEvent();

    // Set the sink the logger pushes WatchRequest objects into.
    // Optional — when unset, countEvent only increments + returns.
    // (Phase 1 ships with sink unset; Phase 2 wires it to Writer.)
    using WatchSink = std::function<void(Record::WatchRequest)>;
    void bindWatchSink(WatchSink sink);

    // Existing API: start(), stop(), watch(), etc. — unchanged.

private:
    WatchSink   watchSink_;
    std::size_t heartbeatInterval_ = 10000;
    std::size_t checkpointInterval_ = 100000;
    bool        saveHeartbeat_   = false;
    bool        saveCheckpoints_ = false;
    // ... existing members
};

} // namespace Monitor
```

### 1.2 `Record::WatchRequest` (lives in `utils/Record/Types.hh`)

```cpp
namespace Record {

struct WatchRequest {
    enum class Kind {
        Heartbeat,    // logger sample, no file write needed in v1
        Checkpoint,   // quiesce workers, write checkpoint TFile
        Finalize,     // drain workers, merge, write final TFile, exit
        Fatal,        // best-effort drain + write, exit
    } kind = Kind::Heartbeat;

    std::size_t                    eventIndex = 0;
    std::shared_ptr<BarrierState>  barrier;   // present for Checkpoint, Finalize, Fatal
};

} // namespace Record
```

`utils/Monitor/Logger.hh` will `#include "Record/Types.hh"` for this
forward.  (User-confirmed.  Layering: Monitor depends on Record types,
which depend on nothing from Monitor.)

### 1.3 `countEvent` body

```cpp
std::size_t AsyncLogger::countEvent() {
    const std::size_t n =
        watch_.iEvent.fetch_add(1, std::memory_order_relaxed) + 1;

    if (saveHeartbeat_ && (n % heartbeatInterval_) == 0)
        emitHeartbeat(n);

    if (saveCheckpoints_ && (n % checkpointInterval_) == 0)
        requestCheckpoint(n);   // synchronous barrier wait inside

    return n;
}
```

`emitHeartbeat(n)` pushes `WatchRequest{Kind::Heartbeat, n, nullptr}`
(no barrier) — fire-and-forget.

`requestCheckpoint(n)` pushes `WatchRequest{Kind::Checkpoint, n,
sharedBarrier}` and blocks the calling thread on the barrier until
the watchdog signals completion.  The calling thread is the analysis
worker that happened to cross the interval — it pauses until
checkpoint flush returns.

For Phase 1, the sink is unset by default and the heartbeat /
checkpoint paths are dead code — the writer still uses its existing
`Writer::checkpoint(eventIndex)` synchronous path.  We turn the sink
on in Phase 2 once the watchdog exists.

### 1.4 Driver call-site change

Replace any direct `watch.iEvent++` in the analysis callback path
with `logger.countEvent()`.  Audit:

```bash
grep -rn "iEvent++\|++.*iEvent\|iEvent\.fetch_add" utils/ modules/ _Lambda_*.cc
```

Likely call sites: the analysis callback inside
`_Lambda_Reconstruction.cc`, and any other driver doing per-event
bookkeeping.

### 1.5 File-level changes

| File | Change |
| --- | --- |
| `utils/Record/Types.hh` | Add `WatchRequest` struct. |
| `utils/Monitor/Logger.hh` | Include `Record/Types.hh`.  Add `countEvent`, `bindWatchSink`, `emitHeartbeat`, `requestCheckpoint` + private interval state. |
| `utils/Monitor/Configure.hh` (or whichever populates the AsyncLogger from TOML) | Read `[monitor].save_*`, `checkpoint_interval`, `heartbeat_interval`. |
| `_Lambda_Reconstruction.cc` | Replace event-counter increment with `logger.countEvent()`. |
| `_Lambda_Parallel.cc`, `_Lambda_Data.cc` | Same audit; replace if applicable. |
| Other drivers in `_*.cc` at repo root. | Same. |

### 1.6 Tests for Phase 1

- All existing tests pass unchanged (sink is unset).
- New `tests/test_logger_countevent.cc`: increment counter from
  N producer threads, assert final count equals N×iterations,
  assert that with a captured sink, the correct number of
  Heartbeat / Checkpoint requests fire at the configured intervals.

### 1.7 Phase 1 done when

- `make test` passes including the new logger test.
- `_Lambda_Reconstruction.exe` runs end-to-end (sink unset; Writer
  path identical to Phase 0).
- One commit, scoped to Logger + WatchRequest type.

---

## Phase 2 — Writer rewrite (the load-bearing one)

This is the big change.  Multiple sub-steps inside one PR; commit
checkpoints at each sub-step but the whole PR ships atomically.

### 2.1 New types in `utils/Record/Types.hh`

#### 2.1.1 Cloned histogram-family wrappers

```cpp
namespace Record {

struct ClonedTH1 {
    TH1* master = nullptr;                       // owned by outFile_; written at finalize
    std::vector<std::unique_ptr<TH1>> clones;    // size = nRecordThreads_; in-memory only
};

struct ClonedTH2 {
    TH2* master = nullptr;
    std::vector<std::unique_ptr<TH2>> clones;
};

struct ClonedTGraph {
    TGraph* master = nullptr;
    std::vector<std::unique_ptr<TGraph>> clones;
    std::vector<std::int32_t>            nextPoint;   // per-worker write head
};

struct ClonedTProfile {
    TProfile* master = nullptr;
    std::vector<std::unique_ptr<TProfile>> clones;
};

struct SharedTTree {
    TTree* tree = nullptr;
    std::mutex mutex;
    // existing branch state
};

} // namespace Record
```

#### 2.1.2 Modified storage structs

```cpp
struct ParticleTH1Cloned {
    ClonedTH1                 hist;
    Physics::ParticleProperty property{};
};
// similarly ParticleTH2Cloned, ParticleGraphCloned, ParticleProfileCloned

struct ParticleObjects {
    RecordKey     basis{};
    std::string   name;
    TDirectory*   dir{};
    ClonedTH1     count;                           // was TH1*
    // candidateCount: REMOVED.  Was scribe-local mutable state; now
    // local to the worker fill function.
    std::vector<ParticleTH1Cloned>     hists1D;
    std::vector<ParticleTH2Cloned>     hists2D;
    std::vector<ParticleGraphCloned>   graphs;
    std::vector<ParticleProfileCloned> profiles;
    SharedTTree                        tree;       // unchanged shape, mutex inside
};

// Independent records similarly: Hist1DRecord uses ClonedTH1, etc.
// ExplicitTreeRecord wraps SharedTTree.
```

### 2.2 Simplified `ParticleRequest`

```cpp
struct ParticleRequest {
    RecordKey basis{};
    std::vector<Physics::Lorentz> particles;
};
// ParticleRequestKind: REMOVED.
// ParticleGroupFillRequest: REMOVED.
// ParticleRequest::groups: REMOVED.
```

`Writer::fillParticleEvent` fans out:

```cpp
template <typename Basis>
void fillParticleEvent(std::initializer_list<ParticleFillView<Basis>> fills) {
    requireEnumBasis<Basis>();
    for (const auto& fill : fills) {
        pushFill(ParticleRequest{
            keyOf(fill.basis),
            std::vector<Physics::Lorentz>(fill.particles.begin(),
                                          fill.particles.end())
        });
    }
}
```

### 2.3 Unified fill queue

Replace the per-lane deques + `grandQueue_` ticket with one
`std::variant`-based queue:

```cpp
using FillRequest = std::variant<
    ParticleRequest,
    Hist1DRequest,
    Hist2DRequest,
    GraphRequest,
    ProfileRequest,
    TreeRowRequest
>;

std::deque<FillRequest> fillQueue_;
std::mutex              fillMutex_;
std::condition_variable fillNotEmpty_;
std::condition_variable fillNotFull_;
std::size_t             fillQueueCapacity_;   // 10 * nRecordThreads_
```

Control requests (`CheckpointRequest`, `FinishRequest`,
`FatalWriteRequest`) move to the watchdog's own queue (§2.5) and do
NOT travel through the high-volume fill lane.

### 2.4 Worker pool

```cpp
class Writer {
private:
    std::vector<std::thread> workers_;
    std::size_t              nRecordThreads_ = 0;   // set by setRecordThreadCount()
    // ...

public:
    // Called once during configuration, before start().
    void setRecordThreadCount(std::size_t n);
};
```

Set in `Config::configure` from `[record].thread_count`.  Validated
at `start()` — must be ≥1, must be set before any declare-time
clone allocation.

Worker body:

```cpp
void Writer::workerLoop(int workerIdx) {
    while (true) {
        if (quiesceRequested_.load(std::memory_order_acquire)) {
            arriveAtQuiesceBarrier();   // wait on hold cv, then resume
            continue;
        }

        std::optional<FillRequest> req = popFill();   // blocks
        if (!req) break;                              // stop signal

        try {
            std::visit([&](auto& r) { apply(r, workerIdx); }, *req);
        } catch (...) {
            recordWorkerException(std::current_exception());
            break;
        }
    }
}
```

`apply(ParticleRequest, workerIdx)` iterates particles, computes
each observable via `Physics::valueOf`, fills into
`obj.hists1D[i].hist.clones[workerIdx]` etc.  TTree fills take
`obj.tree.mutex` first.

### 2.5 Watchdog thread + control queue

```cpp
class Writer {
private:
    std::thread             watchdog_;
    std::deque<WatchRequest> watchQueue_;
    std::mutex               watchMutex_;
    std::condition_variable  watchCv_;

    void watchdogLoop();
public:
    // Called by AsyncLogger via the watch sink.
    void signalWatch(WatchRequest req);
};
```

```cpp
void Writer::watchdogLoop() {
    while (true) {
        WatchRequest req = popWatch();   // blocks
        try {
            switch (req.kind) {
                case WatchRequest::Kind::Heartbeat:
                    writeHeartbeatLog(req.eventIndex);
                    break;

                case WatchRequest::Kind::Checkpoint:
                    quiesceWorkers();
                    snapshotToCheckpointFile(req.eventIndex);
                    releaseWorkers();
                    completeBarrier(req.barrier);
                    break;

                case WatchRequest::Kind::Finalize:
                    accepting_.store(false, std::memory_order_release);
                    drainAndStopWorkers();   // join all worker threads
                    mergeClonesIntoMasters();
                    writeMastersToFileAndClose();
                    completeBarrier(req.barrier);
                    return;

                case WatchRequest::Kind::Fatal:
                    accepting_.store(false, std::memory_order_release);
                    stopRequested_.store(true, std::memory_order_release);
                    fillNotEmpty_.notify_all();
                    bestEffortDrainAndJoin();
                    bestEffortMergeAndWrite();
                    completeBarrier(req.barrier);
                    return;
            }
        } catch (...) {
            completeBarrier(req.barrier, std::current_exception(), false);
            recordWriterException(std::current_exception());
            return;
        }
    }
}
```

### 2.6 Worker quiesce for Checkpoint

```cpp
struct Writer::Quiesce {
    std::atomic<bool>           requested{false};
    std::atomic<std::size_t>    arrived{0};
    std::condition_variable     hold;          // workers wait here
    std::condition_variable     resume;        // watchdog wakes workers
    std::mutex                  mutex;
    bool                        release = false;
} quiesce_;
```

Watchdog `quiesceWorkers()`:
1. Set `quiesce_.requested = true` (release order).
2. Notify `fillNotEmpty_` to wake any worker blocked on an empty queue.
3. Wait until `quiesce_.arrived == nRecordThreads_`.
4. (Critical section: now no worker is mid-fill; safe to read clones.)

Worker `arriveAtQuiesceBarrier()`:
1. Lock `quiesce_.mutex`.
2. Increment `quiesce_.arrived`.  Notify the watchdog (the wait in
   step 3 above can spin or use a notify).
3. Wait on `quiesce_.hold` until `quiesce_.release == true`.
4. Re-decrement `quiesce_.arrived`; unlock; loop back to worker top.

Watchdog `releaseWorkers()`:
1. Set `quiesce_.requested = false`.
2. Set `quiesce_.release = true`.
3. Notify all on `quiesce_.hold`.
4. Wait until `quiesce_.arrived == 0`.
5. Set `quiesce_.release = false`.

Cost per fill: one atomic load on `quiesce_.requested`.  Negligible.
Cost per checkpoint: one round-trip through the condvars.

### 2.7 `snapshotToCheckpointFile`

```cpp
void snapshotToCheckpointFile(std::size_t eventIndex) {
    TFile cpFile(paths_.checkpointOutName.Data(), "RECREATE");

    // For each particle group's directory:
    //   Create the directory in cpFile.
    //   For each Cloned* family member:
    //     Build a temporary merged TH1 from clones (master->Clone(), then Add).
    //     Write the merged temporary to cpDir.
    //     Discard temporary.
    //   The running clones are not touched.

    // Same for independent objects.
    // Shared TTrees: snapshot via TTree::CloneTree(-1, "fast") into cpFile.

    cpFile.Write("", TObject::kOverwrite);
    cpFile.Close();
}
```

Heavy operation — that's expected.  Cadence is controlled by
`[monitor].checkpoint_interval`; user opts in knowing the cost.

### 2.8 Lifecycle order

```
1. Writer ctor
2. open(paths, hist, meta)                  ← creates TFile, master objects
3. setRecordThreadCount(n)                  ← from Config; must be > 0
4. declare*(...) for every histogram        ← creates master + n clones
5. bind(logger, ...)                        ← logger.bindWatchSink(...)
6. start()                                  ← spawns n workers + 1 watchdog
7. fill*(...) from analysis threads         ← lock-free into clones
   ↳ may interleave with:
     - countEvent → signalWatch(Heartbeat / Checkpoint) → watchdog handles
8. finish(eventCount)                       ← pushes Finalize WatchRequest, blocks on barrier
                                              watchdog: drain → merge → write → close
9. dtor                                     ← cleanup() best-effort
```

If the user constructed the Writer without setting thread count by
the time `start()` is called, that's a configuration error — throw
loudly.

### 2.9 Public API changes summary

| Method | Phase 0 | Phase 2 |
| --- | --- | --- |
| `open(Paths, HistConfig, Meta::Record)` | unchanged | unchanged |
| `setRecordThreadCount(std::size_t)` | added (no-op until Phase 2) | functional |
| `bind(AsyncLogger&, ...)` | unchanged | unchanged; also wires watch sink |
| `start()` | unchanged signature | spawns workers + watchdog instead of scribe |
| `fill*(...)` | unchanged signatures | pushes into unified fill queue |
| `checkpoint(eventIndex)` | unchanged | builds Checkpoint WatchRequest, signals watchdog, blocks |
| `finish(eventCount)` | unchanged | builds Finalize WatchRequest, signals watchdog, blocks |
| `fatalWrite(eventCount, timeout)` | unchanged | builds Fatal WatchRequest |
| `signalWatch(WatchRequest)` | — | new; called by AsyncLogger via sink |
| `setQueueCapacity(std::size_t)` | unchanged | applies to fill queue |
| `queueCapacity()`, `stats()` | unchanged | updated internals |

All `declare*` and `fill*` template overloads keep their signatures.
No call-site changes outside the Writer for users of the existing API.

### 2.10 Merge math at finalize

For each `ClonedTH1`:
```cpp
master->Reset("ICESM");
for (auto& clone : clones) master->Add(clone.get());
```

For each `ClonedTH2`: same (`TH2` inherits `TH1::Add`).

For each `ClonedTProfile`: `TProfile::Add` exists, same shape.

For each `ClonedTGraph`:
```cpp
master->Set(0);
int p = 0;
for (auto& clone : clones) {
    const int n = clone->GetN();
    for (int i = 0; i < n; ++i)
        master->SetPoint(p++, clone->GetPointX(i), clone->GetPointY(i));
}
```

Final master TGraph contains the concatenation of per-worker points.
Order across workers is not deterministic but the master semantic is
"all candidates seen, in some valid order" — same as today's single
scribe.

For `SharedTTree`: no merge — the master IS the only TTree (mutex-guarded).

### 2.11 Files touched in Phase 2

| File | Change |
| --- | --- |
| `utils/Record/Types.hh` | Add Cloned* wrappers, SharedTTree.  Modify ParticleObjects / Hist1DRecord / Hist2DRecord / GraphRecord / ProfileRecord / ExplicitTreeRecord to use Cloned/Shared. |
| `utils/Record/Requests.hh` | Strip ParticleRequestKind / ParticleGroupFillRequest / ParticleRequest::groups.  ParticleRequest becomes `{ basis, particles }`. |
| `utils/Record/Writer.hh` | Big rewrite.  Worker pool, watchdog, quiesce, unified fill queue, declare-time cloning, merge-at-finalize. |
| `utils/Record/Histogram.hh` | Helpers for clone construction (`cloneTH1`, `cloneTH2`, etc.). |
| `utils/Record/Finalizer.hh` | Updated for new finalize path. |
| `utils/Monitor/Logger.hh` | Connect `bindWatchSink` to `Writer::signalWatch` in `bind` or `start`. |
| `tests/test_record_writer.cc` | Drop scribe-specific assertions; add multi-thread fill test; assert merged master after finalize. |

### 2.12 Tests for Phase 2

1. **Single-thread fills** — existing test cases should pass byte-equivalent.
2. **Multi-thread fills** — N producer threads × M fills each → final
   master has N×M entries, correct integral.  `n_record = 4`.
3. **Quiesce semantics** — fire a checkpoint mid-run; assert that the
   checkpoint TFile snapshot has exactly the entries seen so far,
   AND the post-checkpoint final master has all entries (checkpoint
   did not consume any).
4. **Worker exception propagation** — one worker throws on a fill;
   `finish()` re-throws on the calling thread; remaining writers
   in flight complete or are cleanly dropped.
5. **TTree mutex correctness** — N producer threads fill into one
   shared TTree concurrently; final entry count matches sum of fills,
   no entry corruption.
6. **Watchdog Heartbeat path** — fire-and-forget; ensure no barrier
   left dangling.

### 2.13 Phase 2 done when

- All tests above pass.
- `_Lambda_Reconstruction.exe` runs end-to-end with `ProbeIMT` driver,
  produces a histogram-equivalent output to the pre-rewrite reference run.
- CPU% during run no longer pinned at ~150%; should rise toward
  `n_record * 100%` during the steady-state fill phase.
- New trace shows scribe-thread footprint eliminated.

---

## Phase 3 — Validate with `ProbeIMT`

After Phase 2 lands, run the full reconstruction and confirm wall-time
improvement.

### 3.1 Validation runs

For `event_count = 100_000` and `event_count = 10_000_000`, at
`record.thread_count = {1, 4, 8}`, with the current `Probe::ProbeIMT`
driver:

- Wall time
- Peak RSS
- CPU% sample via `top` or a fresh xctrace
- Output equivalence: `hadd`-diff of the produced TFile against a
  pre-Phase-2 reference run (entry counts, integrals, per-bin content).

Expected: ~2-3× wall-time speedup at `record.thread_count = 8` on the
100k workload; better on larger inputs.

### 3.2 If wall time doesn't move

The trace points squarely at the scribe; not moving means our new
worker pool is contending somewhere we didn't predict.  Likely
suspects:

- Fill queue contention (mutex per push).  Mitigation: lock-free
  MPMC queue, or per-worker queues with round-robin.
- TTree mutex contention.  Mitigation: per-worker TTrees + `hadd`-merge
  at finalize (drops the v1 mutex-shared simplification).
- `Physics::valueOf` allocation hot.  Mitigation: per-worker scratch
  buffer reuse.

Triage with a fresh xctrace before changing anything.

### 3.3 Phase 3 done when

- Output equivalence confirmed.
- Wall-time speedup ≥ 2× at `record.thread_count = 8`.
- Trace shows no single thread at >25% of total CPU.

---

## Phase 4 — Switch driver back to `ProbeParallel`

Once Phase 2 + 3 validate, swap the reconstruction driver back to the
manual-threads Probe.  Phase 2's Writer is now fast enough that we
don't need IMT-on-reads.

### 4.1 Change set

```cpp
// _Lambda_Reconstruction.cc — line 18
Probe::ProbeParallel probe;   // was Probe::ProbeIMT
```

(No other change to the driver.  `Config::configure` is templated;
ProbeParallel is the original SFINAE branch.)

### 4.2 Validation runs

Same matrix as Phase 3.  Compare ProbeParallel vs ProbeIMT at
identical Writer config.  Three outcomes:

- ProbeParallel is faster or equal → ship it as default; ProbeIMT becomes
  opt-in (Phase 5).
- ProbeParallel is slower by a margin → keep ProbeIMT as default; revisit
  whether the IMT-on-reads win exists independently of Writer parallelism.
- They are within noise → ship ProbeParallel.  Simpler code; less memory.

### 4.3 Phase 4 done when

- One of the three decisions above is made and acted on.
- Output equivalence is confirmed under the chosen driver.

---

## Phase 5 — ProbeIMT cleanup

Final cleanup pass.  Goal: codebase looks like the state-from-before
plus the Writer-parallel work, minus any half-built scaffolding.

### 5.1 ProbeIMT lives behind `[probe].root_imt = true`

Default `false`.  When false, the Writer-parallel ProbeParallel path
runs.  When true, ProbeIMT runs — but a NEW ProbeIMT that streams
events through the analysis callback without the full-buffer pattern.

### 5.2 Streaming ProbeIMT redesign

Strip the per-event `BufferT` allocation.  New shape:

```cpp
template<typename Callback>
void ProbeIMT::run(Callback&& cb) {
    ROOT::EnableImplicitMT(threadCount_);
    // For each spec: TTreeProcessorMT::Process with callback that
    // assembles partial events and invokes the analysis callback
    // directly (no per-event buffer; no flush phase).
}
```

Event assembly across multiple trees with `event_index` joining
becomes the hard problem again.  Three options:

| Option | Effort | Notes |
| --- | --- | --- |
| One TTreeProcessorMT per spec, lockstep merge under shared sequence number | medium | matches today's logic; loses per-event ordering across workers |
| Friend trees | small if BuildIndex works in IMT | requires testing; some ROOT versions buggy here |
| Use ProbeParallel for multi-tree, ProbeIMT only for single-tree | smallest | exposes single-tree fast path as opt-in only |

Recommend the third: ProbeIMT in Phase 5 only supports single-tree
specs and errors loudly on multi-tree.  Multi-tree uses ProbeParallel.
This matches the actual measurement: ProbeIMT's win was always per-spec
read-throughput; the multi-tree join was never the bottleneck.

### 5.3 Deprecated paths

- `Probe::Splitter` — remove or fold into a "tools/" splitter binary
  for users who want to pre-shard inputs manually.
- `[probe].split_input`, `[probe].temp_space`, `[probe].keep_shards` —
  warn and ignore on parse.  Remove in a follow-up after one release.
- `EventReaderMT` if the new ProbeIMT is single-tree only — fold its
  type dispatch into a simpler inline reader.
- `spike_imt_read.exe` — keep.  It stays useful as a measurement tool.
- Phase 1 doc text in `ROOTMT.md` — update to reflect that Phase 1 is
  deprecated in production but the splitter primitive remains
  available for ad-hoc use.

### 5.4 Files touched in Phase 5

| File | Change |
| --- | --- |
| `utils/Probe/ParallelIMT.hh` | Streaming rewrite; reject multi-tree specs. |
| `utils/Probe/EventReaderMT.hh` | Inline or simplify. |
| `utils/Probe/Splitter.hh` | Remove or extract to tools/. |
| `utils/Probe.hh` | Drop deprecated headers from the umbrella. |
| `utils/Config/Types.hh`, `Reader.hh` | `splitInput`, `tempSpace`, `keepShards` parse with deprecation warning. |
| `_Lambda_Reconstruction.cc` | `Probe::ProbeParallel probe;` (or read `[probe].root_imt` and pick at runtime via variant — both options OK). |
| `docs/ROOTMT.md` | Final state section. |
| `docs/WriterMT.md` (this file) | Mark Phase 5 done. |

### 5.5 Phase 5 done when

- Default ProbeParallel + multithreaded Writer is the production path.
- ProbeIMT (streaming) opt-in via TOML works on single-tree inputs.
- Splitter no longer shipped as part of `Probe.hh`.
- `make test` green; full reconstruction output equivalence holds.

---

## Order of execution

```
Phase 0 — TOML migration                       (1-2 hours, isolated commit)
Phase 1 — Logger countEvent + watch sink       (3-4 hours, isolated commit)
Phase 2 — Writer rewrite                       (full day, single PR with sub-commits)
Phase 3 — Validate on ProbeIMT                 (measurement + comparison)
Phase 4 — Switch to ProbeParallel              (one-line change + revalidation)
Phase 5 — ProbeIMT/Splitter cleanup            (half day)
```

Each phase ends with `make test` green and an end-to-end run against
the real input.  No phase land into main without that gate.

---

## Open items / decisions deferred

- **TGraph merge semantics**: current behaviour writes one master with
  every candidate point.  Confirmed equivalent across master + clone
  topology by concatenating points; order is non-deterministic across
  clones but within-clone order is preserved.  If a downstream
  consumer assumes strict insertion order, this changes their
  observation.  Re-evaluate if a test asserts it.
- **Counter histograms** (`ParticleObjects::count`): currently
  filled once per request with `candidateCount`.  With per-worker
  clones, candidateCount becomes per-request local.  Master sum
  matches the previous scribe behaviour.  No semantic change.
- **Fill-queue capacity**: `10 * nRecordThreads_` per the user's
  prescription.  May need tuning if producers stall; revisit only
  after Phase 3 measurement.
- **Lock-free MPMC queue**: not in v1.  Add as a Phase 6 optimisation
  if Phase 3 shows queue mutex contention dominates.
- **Per-worker TTree** (instead of shared mutex): not in v1.  Add
  if Phase 3 shows TTree mutex contention dominates.
- **Logger throttle**: deferred per user.  Re-evaluate after Phase 2
  trace.
- **Pythia drivers**: read `[pythia].thread_count` in Phase 0 but the
  actual handover to PythiaParallel happens via existing wiring.  No
  Pythia-side change in this work.

---

## Risks

- **Worker exception during fill**: today the scribe sets
  `scribeException_` and rethrows on the next producer call.  With
  N workers, the first worker to throw stores into a shared
  `workerException_`; remaining workers detect on next iteration
  and exit.  Subsequent producer calls observe the exception via
  the queue push path.  Pattern is well-trodden but needs careful
  ordering of `accepting_ = false` and the wake-ups.
- **Lifecycle ordering bugs** are the biggest risk.  Worker join
  before merge.  Watchdog join after merge.  All barriers honoured
  on the exception path.  Will be the place tests focus on.
- **Output equivalence**: per-bin content must match the pre-rewrite
  baseline.  TGraph point order is the one place we relax that
  invariant.  Test suite needs an "approximate equivalence" comparator
  for graphs (compare sorted point arrays).
- **Phase 1 + Phase 2 cohabitation**: if Phase 1 ships first with
  the watch sink unset, the legacy `Writer::checkpoint` path still
  works.  In Phase 2 we switch the sink on and route checkpoint
  through the watchdog.  The transition needs a clean cut, not a
  half-state where both paths can fire.

---

## Layering invariants (must not regress)

```
Physics  ←  Probe, Record, Config, Monitor
Config   ←  Probe, Record, Monitor                  (Configure.hh aside)
Record   ←  Monitor (via WatchRequest #include)     ← NEW in Phase 1
Monitor  ←  drivers
Probe    ←  drivers
```

No backward edges.  `Record/Types.hh` must NOT include any Monitor
header (it carries `WatchRequest` which Monitor's Logger consumes).
