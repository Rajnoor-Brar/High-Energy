# Plan

Updated: 2026-05-16.

One phase per individual problem, drawn from
[Issues.md](Issues.md), [REVIEW.md](REVIEW.md), and
[PaintReview.md](PaintReview.md). Phases are grouped by concern; within a
group they are ordered by priority and dependency.

Scope legend: **XS** < 30 min · **S** < 2 h · **M** < 1 day · **L** multi-day.

---

## Phase Index

| # | ID | Title | Source | Scope |
|---|---|---|---|---|
| 1 | I-P0 | Stage-level throughput measurement | Issues § P0 | L |
| 2 | R3.1 | Replace `BlockTimer` with `TimerRegistry` | REVIEW § 3.1 | M |
| 3 | R3.2 | Instrument pipeline bottleneck boundaries | REVIEW § 3.2 | M |
| 4 | R1.1 | Document `analysis_threads` contract | REVIEW § 1.1 | S |
| 5 | R1.2 | Vector-stream CollectorThread support | REVIEW § 1.2 | M |
| 6 | I-P1a | Complete `configurePythia` | Issues § P1 | S |
| 7 | I-P1b | Resolve branch name drift (`Index` vs `event_index`) | Issues § P1 | XS |
| 8 | R4.3 | Split parse side effects in Probe facade | REVIEW § 4.3 | S |
| 9 | I-P2-pp | Rebuild `test_probe_parallel` | Issues § P2 | M |
| 10 | I-P1c | Writer lifecycle/concurrency stress tests | Issues § P1 | M |
| 11 | R2.2 | Watchdog barrier resilience tests | REVIEW § 2.2 | M |
| 12 | R2.1 | Per-worker and per-record stats on `Writer` | REVIEW § 2.1 | M |
| 13 | R3.3 | Reduce per-event monitor locking | REVIEW § 3.3 | S |
| 14 | I-P2-wt | Rebuild `test_writer` | Issues § P2 | M |
| 15 | I-P2-cfg | Add `test_config` round-trip | Issues § P2 | S |
| 16 | I-P2-rA | Extend `test_rootAnalysis_smoke` | Issues § P2 | S |
| 17 | R4.1 | Remove inline module-level docs from headers | REVIEW § 4.1 | S |
| 18 | R4.2 | Keep branch names honest in configs | REVIEW § 4.2 | XS |
| 19 | R5.1 | Log resolved path in `resolveLimitsPath` | REVIEW § 5.1 | XS |
| 20 | R5.2 | `run_all.sh` — report all failures, not first | REVIEW § 5.2 | XS |
| 21 | R5.3 | Replace `runLoop` option snapshots with action queue | REVIEW § 5.3 | S |
| 22 | R5.4 | Structured JSON/CSV stats dump | REVIEW § 5.4 | M |
| 23 | PR-P0.1 | Fix `hasMaximum` key-driven logic | PaintReview § P0.1 | XS |
| 24 | PR-P0.2 | Fix `source_search` silent mode override | PaintReview § P0.2 | S |
| 25 | PR-P0.3 | Guard `Color_t` offset overflow | PaintReview § P0.3 | XS |
| 26 | PR-P0.4 | Fix overlay stats-box overwrite | PaintReview § P0.4 | S |
| 27 | PR-P0.5 | RAII-restore batch mode in `renderPlan` | PaintReview § P0.5 | XS |
| 28 | PR-P0.6 | Fix `TImage` leak in `savePng` | PaintReview § P0.6 | XS |
| 29 | PR-P1.1 | Throw on unknown colour token | PaintReview § P1.1 | XS |
| 30 | PR-P1.2 | Throw on type mismatch in `readValue` | PaintReview § P1.2 | XS |
| 31 | PR-P2.1 | Lift `detail::` merge helpers to public namespace | PaintReview § P2.1 | S |
| 32 | PR-P2.2 | Unify duplicate preset-resolution walk | PaintReview § P2.2 | S |
| 33 | PR-P2.3 | Registry-based `ObjectKind` dispatch | PaintReview § P2.3 | M |
| 34 | PR-P1.5 | Add `TProfile` kind; throw for unsupported types | PaintReview § P1.5 | S |
| 35 | PR-P1.3 | Per-source colour palette in `source_search` | PaintReview § P1.3 | S |
| 36 | PR-P1.4 | Glob/regex matching in `source_search` | PaintReview § P1.4 | S |
| 37 | PR-P1.6 | Canonicalise `assertExpectedKind` type tokens | PaintReview § P1.6 | XS |
| 38 | PR-P1.7 | Support `default_style = ""` opt-out | PaintReview § P1.7 | XS |
| 39 | PR-P1.8 | Allow `output_name` in visual presets | PaintReview § P1.8 | XS |
| 40 | PR-P1.9 | Configurable stats-box fill colour / style | PaintReview § P1.9 | S |
| 41 | PR-P1.10 | Derive legend marker type from draw option | PaintReview § P1.10 | S |
| 42 | PR-P1.11 | Route all formats through `TCanvas::Print` | PaintReview § P1.11 | XS |
| 43 | PR-P1.12 | Remove or harden `mutate_input` flag | PaintReview § P1.12 | S |
| 44 | PR-P2.4 | Move `Paint.hh` doc block to Architecture.md | PaintReview § P2.4 | XS |
| 45 | PR-P2.5 | Make `modeName`/`objectKindName` unreachable-safe | PaintReview § P2.5 | XS |
| 46 | PR-P2.6 | Cap recursion depth in `searchDirectory` | PaintReview § P2.6 | XS |
| 47 | PR-P2.7 | Rename `detachFromDirectory` → `detachHistFromDirectory` | PaintReview § P2.7 | XS |
| 48 | PR-P2.8 | Add resolved-style output to `printPlan` | PaintReview § P2.8 | S |
| 49 | PR-P2.9 | Fix `dryRun` const-correctness | PaintReview § P2.9 | XS |
| 50 | PR-P2.10 | Replace magic strings with named constants | PaintReview § P2.10 | S |
| 51 | PR-TG | Paint test gaps | PaintReview § Tests | M |

---

## Group 1 — Measurement and Timer Infrastructure

### Phase 1 · I-P0 · Stage-level throughput measurement

**Source:** Issues.md § P0  
**Priority:** P0  
**Scope:** L  
**Depends on:** Phase 2 (TimerRegistry), Phase 3 (instrumentation)

Add per-stage timing so thread-count changes are data-driven. The current
`BlockTimer` is unsuitable (file I/O on the hot path, no labels, no CSV). This
phase only defines the measurement plan and the sequence to run once Phases 2
and 3 are done:

1. Run a fixed-event matrix `probe_threads × analysis_threads × writer_threads ∈ {1,2,4,8}`.
2. Collect `TimerRegistry::dump()` CSV from each run.
3. Identify the bottleneck stage (Probe read, queue wait, Lambda, Writer fill, Writer merge).
4. File a follow-on phase for the winning intervention.

**Files (measurement scripts / docs only):**
- `docs/ROOTMT.md` — add measurement matrix results table
- `tests/run_timing_matrix.sh` — new script (optional; can be manual)

---

### Phase 2 · R3.1 · Replace `BlockTimer` with `TimerRegistry`

**Source:** REVIEW.md § 3.1  
**Priority:** P1 (blocks Phase 1 and Phase 3)  
**Scope:** M

Replace `Monitor/Timer.hh`'s file-I/O `BlockTimer` with a thread-safe scoped
timer backed by thread-local accumulators and a shutdown CSV dump.

Design:
- `Monitor::ScopeTimer` — RAII; increments a per-label, per-thread accumulator.
- `Monitor::TimerRegistry` — global (or injected) singleton; holds all
  accumulators; `dump(std::ostream&)` writes CSV `(label, wall_ns, cpu_ns, count)`.
- Compile-time flag `MONITOR_TIMERS=0` disables to zero overhead in production.
- No file I/O inside the timed scope; dump only at shutdown.

**Files:**
- `utils/Monitor/Timer.hh` — replace `BlockTimer` with `ScopeTimer` + `TimerRegistry`
- `utils/Monitor.hh` — add `Timer.hh` to the wrapper if not already included
- Any `Lambda/` call sites that referenced `BlockTimer` — uncomment using new API
- `docs/Architecture.md` — update Monitor § timer subsection

---

### Phase 3 · R3.2 · Instrument pipeline bottleneck boundaries

**Source:** REVIEW.md § 3.2  
**Priority:** P1  
**Scope:** M  
**Depends on:** Phase 2

Wrap the 16 label sites listed in Issues.md § P0 with `ScopeTimer`:

| Label | File | Site |
|---|---|---|
| `ProbeParallel.EventStream.next` | `Probe/Directives.hh` | reader loop |
| `ProbeParallel.queue.push_wait` | `Probe/Directives.hh` | bounded push |
| `ProbeParallel.queue.pop_wait` | `Probe/Directives.hh` | collector pop |
| `ProbeParallel.collector.callback` | `Probe/Directives.hh` | callback invoke |
| `ProbeIMT.allocate` | `Probe/Methods.hh` | buffer alloc |
| `ProbeIMT.read` | `Probe/Methods.hh` | TTree read loop |
| `ProbeIMT.flush` | `Probe/Methods.hh` | parallel flush |
| `Lambda.rootAnalysis` | `modules/Lambda/Recording.hh` | outer wrapper |
| `Lambda.reconstructCandidates` | `modules/Lambda/Reconstruction.hh` | inner loop |
| `Record.Writer.pushFill` | `Record/Directives.hh` | enqueue |
| `Record.Writer.applyParticleRequest` | `Record/Directives.hh` | fill body |
| `Record.Writer.treeMutex` | `Record/Directives.hh` | mutex scope |
| `Record.Writer.mergeAllClones` | `Record/Cloning.hh` | merge |
| `Record.Writer.writeCheckpointFile` | `Record/Administration.hh` | checkpoint write |
| `Record.Writer.writeAllToCurrentFile` | `Record/Administration.hh` | final write |
| `Monitor.AsyncLogger.publish` | `Monitor/Administration.hh` | lock scope |

Add `TimerRegistry::dump()` call at the end of `_Lambda_Reconstruction.cc` main.

**Files:** as listed in the table above, plus `_Lambda_Reconstruction.cc`

---

## Group 2 — Probe Improvements

### Phase 4 · R1.1 · Document `analysis_threads` contract

**Source:** REVIEW.md § 1.1  
**Priority:** P1  
**Scope:** S

The old mental model ("CollectorThread = serial callback") is stale. Document
the current behaviour clearly in code and in docs:

- `Probe/Parallel.hh` class doc: add a comment block describing CollectorThread
  vs WorkerThread modes, that both can be concurrent, and that callbacks must
  be thread-safe regardless.
- `configs/Lambda_Reconstruction.toml`: add an inline comment on
  `analysis_threads` explaining its effect and that it is ignored in
  WorkerThread mode.
- `docs/Architecture.md` Probe section: update the mode table.

**Files:**
- `utils/Probe/Parallel.hh`
- `configs/Lambda_Reconstruction.toml`
- `docs/Architecture.md`

---

### Phase 5 · R1.2 · Vector-stream CollectorThread support

**Source:** REVIEW.md § 1.2  
**Priority:** P2  
**Scope:** M

Remove the `throw` in `ProbeParallel::run` that rejects
`StreamType::Vectors + CollectorThread`. The queue plumbing already supports
multiple collectors; the missing work is:

1. Reader parity: `VecReader` must push events into the shared queue instead of
   invoking the callback directly.
2. Tests: add a `test_probe_parallel` case with a vector-stream fixture and
   CollectorThread mode.

**Files:**
- `utils/Probe/Methods.hh` (or `Directives.hh`) — remove the guard throw
- `utils/Probe/Readers.hh` / `Probe/Directives.hh` — queue push for VecReader path
- `tests/test_probe_parallel.cc` — new vector-stream CollectorThread case

---

## Group 3 — Config and Data-Flow Cleanup

### Phase 6 · I-P1a · Complete `configurePythia`

**Source:** Issues.md § P1  
**Priority:** P1  
**Scope:** S

`Config::configurePythia` sets `Parallelism:numThreads` but beam energy, random
seed, and cmnd_file are still set ad-hoc in driver `.cc` files. Move them into
the facade:

1. Add `[pythia]` TOML keys: `beam_energy`, `seed`, `cmnd_file`.
2. Parse and apply them inside `Config::configurePythia`.
3. Remove the ad-hoc setup from `_Lambda_Data.cc` and any other Pythia driver.

**Files:**
- `utils/Config/Configure.hh` — `configurePythia` method body
- `utils/Config/Reader.hh` — parse new keys into `Events` or a new `PythiaConfig`
- `utils/Config/Types.hh` — add fields if needed
- `_Lambda_Data.cc` — remove manual Pythia setup lines
- `configs/Lambda_Generation.toml` — add new keys
- `docs/DataFlow.md` — update `[pythia]` section

---

### Phase 7 · I-P1b · Resolve branch name drift

**Source:** Issues.md § P1, REVIEW.md § 4.2  
**Priority:** P1  
**Scope:** XS

`Lambda::declareDataObjects` writes branch `event_index`; the reconstruction
config reads `Index`. Fix by:

1. Add a `# Writer-generated data` comment block to
   `configs/Lambda_Reconstruction.toml` showing the correct branch name for
   Writer output vs old external files.
2. Either rename the reconstruction config key to `event_index` (breaking for
   old files) or add a second config file `configs/Lambda_Reconstruction_Writer.toml`.
3. Update `docs/DataFlow.md` to note the two input conventions.

**User Note :** Do not get stuck up in OCD obsession with index branch, it can be anything user specifies in toml, let it be anything
**Files:**
- `configs/Lambda_Reconstruction.toml` (comment + possible key change)
- `configs/Lambda_Reconstruction_Writer.toml` (optional new file)
- `docs/DataFlow.md`

---

### Phase 8 · R4.3 · Split parse side effects in Probe facade

**Source:** REVIEW.md § 4.3  
**Priority:** P2  
**Scope:** S

`Config::configure<ProbePipeline>()` calls configuration steps that create
output directories before the metadata-derived event count is known, then
re-reads paths and creates directories again. Separate the two concerns:

1. Phase A: read config values; resolve thread counts and event count.
2. Phase B: create output directories using the fully-resolved counts.

**Files:**
- `utils/Config/Configure.hh`
- `utils/Config/Reader.hh` (if directory creation lives here)

---

### Phase 17 · R4.1 · Remove inline module-level docs from headers

**Source:** REVIEW.md § 4.1  
**Priority:** P2  
**Scope:** S

Remove multi-paragraph doc blocks from the listed headers; keep only
one-line `// <purpose>` summaries. The authoritative descriptions live in
Architecture.md / MAP.md.

Remaining headers to audit:
- `utils/Probe/Parallel.hh`
- `utils/Probe/ConfigAid.hh`
- `utils/Record/Writer.hh`
- `utils/Monitor/Logger.hh`
- `utils/Config/Configure.hh`

**Files:** the five headers above

---

### Phase 18 · R4.2 · Keep branch names honest in configs

**Source:** REVIEW.md § 4.2  
**Priority:** P2  
**Scope:** XS

Covered by Phase 7. This phase is a tracking alias; mark complete when Phase 7
is done.

---

## Group 4 — Test Infrastructure

### Phase 9 · I-P2-pp · Rebuild `test_probe_parallel`

**Source:** Issues.md § P2  
**Priority:** P2  
**Scope:** M

Current tests were written against a prior codebase. Rebuild to cover:

- CollectorThread mode with multiple collectors.
- WorkerThread mode direct dispatch.
- Queue back-pressure with artificially small `queueCapacity`.
- `[probe.index]` parsing applied to `ParticleSpec.indexSorted` /
  `indexAscending` / `indexMonotonic` fields.
- Error paths: empty input file, zero thread count.

**Files:**
- `tests/test_probe_parallel.cc` — rewrite

---

### Phase 10 · I-P1c · Writer lifecycle / concurrency stress tests

**Source:** Issues.md § P1  
**Priority:** P1  
**Scope:** M

New test cases for the paths not currently exercised:

- Checkpoint while fill producers are blocked on a full queue.
- Checkpoint after one worker records an exception.
- Finalize after a worker exception with pending `WatchRequest`s.
- Fatal write while workers hold the tree mutex.
- `save_checkpoints = true` driven through Logger `WatchRequest` chain.

Also validate the `quiesceWorkers()` risk: confirm the watchdog detects a stored
`writerException_` before blocking on the barrier when a worker exits early.

**Files:**
- `tests/test_writer.cc` — new or extended

---

### Phase 11 · R2.2 · Watchdog barrier resilience tests

**Source:** REVIEW.md § 2.2  
**Priority:** P1  
**Scope:** M  
**Note:** overlaps with Phase 10; can be a sub-section of `test_writer.cc`

Explicit stress cases for the watchdog watch-barrier sequence:

- Multiple queued barriers after the first failure.
- Barrier sequence: checkpoint → fatal → finalize (out-of-order).
- Worker re-entry guard: verify a completed worker does not enter a second barrier.

---

### Phase 14 · I-P2-wt · Rebuild `test_writer`

**Source:** Issues.md § P2  
**Priority:** P2  
**Scope:** M  
**Depends on:** Phase 10, Phase 11

Combine the concurrency cases from Phases 10–11 into a single `test_writer.cc`
that covers the full watchdog matrix. Include:

- Clone management per worker (histogram/graph/profile).
- `mergeAllClones` correctness (sum invariant for histograms).
- `scaleAndWrite` round-trip through a temp file.

**Files:**
- `tests/test_writer.cc`

---

### Phase 15 · I-P2-cfg · Add `test_config` round-trip

**Source:** Issues.md § P2  
**Priority:** P2  
**Scope:** S

New `tests/test_config.cc` that exercises `Config::configure<ProbePipeline>()`
end-to-end with the live TOML fixture. Verify:

- Probe, Record, and Monitor keys parsed and applied.
- Thread counts resolved correctly.
- `event_count` cap applied.
- `[probe.index]` section applied to specs.

**Files:**
- `tests/test_config.cc` — new
- `tests/fixtures/lambda_fixture.toml` — extend if keys missing

---

### Phase 16 · I-P2-rA · Extend `test_rootAnalysis_smoke`

**Source:** Issues.md § P2  
**Priority:** P2  
**Scope:** S

Extend the existing smoke test to:

- Compare unvalidated / validated candidate counts against analytic bounds
  (at least: validated ≤ unvalidated; both > 0 for known input).
- Assert that at least one mass-window histogram has entries in the correct
  range.

**Files:**
- `tests/test_reconstructCandidates.cc` (or `test_rootAnalysis_smoke.cc`)

---

## Group 5 — Monitor Improvements

### Phase 12 · R2.1 · Per-worker and per-record stats on `Writer`

**Source:** REVIEW.md § 2.1  
**Priority:** P2  
**Scope:** M

Extend `Writer::stats()` to report:

- Configured worker count and active worker count.
- Per-request-kind counts (Hist1D, Hist2D, Graph, Profile, Tree, Particle).
- Current and max fill-queue depth.
- Tree mutex wait time (from Phase 3 timer labels).
- Checkpoint / merge / write timings.

Lightweight text output first; can adopt TimerRegistry CSV later.

**Files:**
- `utils/Record/Writer.hh` — extend stats struct
- `utils/Record/Administration.hh` — populate counters
- `utils/Record/Directives.hh` — increment per-kind counters
- `_Lambda_Reconstruction.cc` — print stats at exit

---

### Phase 13 · R3.3 · Reduce per-event monitor locking

**Source:** REVIEW.md § 3.3  
**Priority:** P2  
**Scope:** S  
**Depends on:** Phase 3 (confirm it shows up in timing)

`AsyncLogger::publish` locks a single mutex per publish. Only do this if Phase 3
timing shows it on the critical path. Options:

- Per-thread log buffers flushed on a timer tick rather than on each `publish`.
- Atomic snapshot for progress counters, lock only for string-payload publishes.

**Files:**
- `utils/Monitor/Administration.hh`
- `utils/Monitor/Directive.hh`
- `utils/Monitor/Logger.hh`

---

## Group 6 — Lower-Priority Backlog

### Phase 19 · R5.1 · Log resolved path in `resolveLimitsPath`

**Source:** REVIEW.md § 5.1  
**Priority:** P2  
**Scope:** XS

`Config::LimitAid::resolveLimitsPath` silently expands a bare name to
`configs/<name>.toml`. Print or return the resolved path so callers can log it.

**Files:**
- `utils/Config/LimitAid.hh`

---

### Phase 20 · R5.2 · `run_all.sh` — report all failures

**Source:** REVIEW.md § 5.2  
**Priority:** P2  
**Scope:** XS

Replace `set -e` (stop on first failure) with a loop that records exit codes
and prints a summary table at the end.

**Files:**
- `tests/run_all.sh`

---

### Phase 21 · R5.3 · Replace `runLoop` option snapshots with action queue

**Source:** REVIEW.md § 5.3  
**Priority:** P2  
**Scope:** S

`AsyncLogger::runLoop` carries several optional action snapshots across a lock
boundary. Replace with a small `std::queue<PendingAction>` drained inside the
lock to simplify extension.

**Files:**
- `utils/Monitor/Directive.hh`
- `utils/Monitor/Types.hh` — update `PendingActions`

---

### Phase 22 · R5.4 · Structured JSON/CSV stats dump

**Source:** REVIEW.md § 5.4  
**Priority:** P2  
**Scope:** M  
**Depends on:** Phase 2, Phase 12

Once the timer registry and writer stats exist, add a single-file dump at
shutdown: `output/run_stats.json` containing probe/writer/monitor stats and
per-label timer CSV rows. Schema TBD; agree format before implementing.

**Files:**
- `utils/Monitor/Report.hh`
- `_Lambda_Reconstruction.cc`

---

## Group 7 — Paint P0 (Correctness)

### Phase 23 · PR-P0.1 · Fix `hasMaximum` key-driven logic

**Source:** PaintReview.md § P0.1  
**Priority:** P0  
**Scope:** XS

In `Paint/Style.hh::mergeStyle`, change:

```cpp
// before
style.hasMaximum = std::abs(style.maximum) > 0.0;

// after
style.hasMaximum = true;
```

The flag must be set whenever the key is present, matching `hasMinimum`. If
opting out of a maximum is needed, add an explicit `auto_maximum = true` key.

**Files:**
- `utils/Paint/Style.hh`
- `tests/test_paint.cc` — add test: `maximum = 0.0` keeps `hasMaximum = true`

---

### Phase 24 · PR-P0.2 · Fix `source_search` silent mode override

**Source:** PaintReview.md § P0.2  
**Priority:** P0  
**Scope:** S

In `Paint/Resolve.hh::resolveSources`:

1. Track whether `mode` was set explicitly (add a `bool modeExplicit` field to
   `RenderResult` or `PaintBook` parse result).
2. Only auto-promote to `Grid` when mode was not set by the user.
3. If `mode = "single"` was explicit and `source_search` returns >1 results,
   let `finaliseLayout` reject it cleanly.

**User note :** let source be hard path, source_match hard search name, source_search search if string is part of nae, then source_regex is self-explanatory.
**Files:**
- `utils/Paint/Types.hh` — add `modeExplicit` flag
- `utils/Paint/Resolve.hh` — conditional promotion
- `utils/Paint/Book.hh` — set flag when parsing `mode` key

---

### Phase 25 · PR-P0.3 · Guard `Color_t` offset overflow

**Source:** PaintReview.md § P0.3  
**Priority:** P0  
**Scope:** XS

In `Paint/Style.hh::parseColor`:

```cpp
// before
return static_cast<Color_t>(it->second + offset);

// after
int raw = it->second + offset;
if (raw < std::numeric_limits<Color_t>::min() ||
    raw > std::numeric_limits<Color_t>::max())
    throw std::runtime_error("color offset out of Color_t range: " + ...);
return static_cast<Color_t>(raw);
```

**Files:**
- `utils/Paint/Style.hh`

---

### Phase 26 · PR-P0.4 · Fix overlay stats-box overwrite

**Source:** PaintReview.md § P0.4  
**Priority:** P0  
**Scope:** S

In `Paint/Render.hh::drawOverlay`, replace the `applyStatsBox` call inside the
per-source loop with explicit per-source `TPaveStats` creation:

- In overlay mode, create a new `TPaveStats` for each source with y-coordinates
  stacked (e.g. top row at `[0.70, 0.90]`, next at `[0.48, 0.68]`, etc.).
- Apply source line colour and style to each stats box.
- Alternative: add a `stats.enabled = false` default for overlay mode and let
  Phase 40 (configurable stats style) drive the design.

**Files:**
- `utils/Paint/Render.hh`
- `utils/Paint/Style.hh` (if stacking offset is configurable)
- `tests/test_paint.cc` — overlay stats test

---

### Phase 27 · PR-P0.5 · RAII-restore batch mode in `renderPlan`

**Source:** PaintReview.md § P0.5  
**Priority:** P0  
**Scope:** XS

```cpp
inline void renderPlan(RenderPlan& plan) {
    Bool_t wasBatch = gROOT->IsBatch();
    gROOT->SetBatch(kTRUE);
    struct Restore { Bool_t prev; ~Restore() { gROOT->SetBatch(prev); } } guard{wasBatch};
    ...
}
```

**Files:**
- `utils/Paint/Render.hh` (or wherever `renderPlan` is defined)

---

### Phase 28 · PR-P0.6 · Fix `TImage` leak in `savePng`

**Source:** PaintReview.md § P0.6  
**Priority:** P0  
**Scope:** XS

Replace the raw `TImage*` with a scope guard:

```cpp
std::unique_ptr<TImage, void(*)(TObject*)> image(
    TImage::Create(), [](TObject* p){ delete p; });
image->FromPad(&canvas);
image->WriteImage(path.c_str());
```

Or wrap in a try/catch that deletes on the throw path.

**Files:**
- `utils/Paint/Save.hh`

---

## Group 8 — Paint P1 (UX)

### Phase 29 · PR-P1.1 · Throw on unknown colour token

**Source:** PaintReview.md § P1.1  
**Priority:** P1  
**Scope:** XS

In `Paint/Style.hh::parseColor`, replace the silent `kBlack` fallbacks with
`throw std::runtime_error("unknown color: " + token)`. The driver will report
and exit cleanly.

**Files:**
- `utils/Paint/Style.hh`
- `tests/test_paint.cc` — add test: unknown colour throws

---

### Phase 30 · PR-P1.2 · Throw on type mismatch in `readValue`

**Source:** PaintReview.md § P1.2  
**Priority:** P1  
**Scope:** XS

In `Paint/Book.hh::detail::readValue` (or wherever the template lives):

```cpp
if (!node) return;
auto value = node.value<T>();
if (!value)
    throw std::runtime_error("type mismatch for key '" + key + "'");
out = *value;
```

**Files:**
- `utils/Paint/Book.hh` (or `Style.hh` if that's where `readValue` lives)
- `tests/test_paint.cc` — add test: string value for int key throws

---

### Phase 34 · PR-P1.5 · Add `TProfile` kind; throw for unsupported types

**Source:** PaintReview.md § P1.5  
**Priority:** P1  
**Scope:** S  
**Depends on:** Phase 33 (registry-based dispatch)

1. Add `ObjectKind::Profile` to `Paint/Types.hh`.
2. Add the `TProfile` dynamic_cast to `inferKind`.
3. Add draw callbacks in `Apply.hh` / `Render.hh` for Profile kind (draw as TH1
   with `"HIST"` or `"E"` option by default).
4. Add `assertExpectedKind` case for `"TProfile"`.
5. For `TF1`, `THStack`, `TMultiGraph`: throw explicitly with a message listing
   unsupported types.

**Files:**
- `utils/Paint/Types.hh`
- `utils/Paint/Render.hh`
- `utils/Paint/Apply.hh`

---

### Phase 35 · PR-P1.3 · Per-source colour palette in `source_search`

**Source:** PaintReview.md § P1.3  
**Priority:** P1  
**Scope:** S  
**Depends on:** Phase 32 (preset duplication unified)

Add a `source_palette = ["kRed", "kBlue", "kGreen"]` TOML key under
`[[paint.<name>]]`. When `source_search` returns N results, cycle the palette
across them in order. For explicit (non-search) sources, existing per-source
`style` blocks still apply.

**Files:**
- `utils/Paint/Types.hh` — add `sourcePalette` field to result type
- `utils/Paint/Book.hh` — parse `source_palette`
- `utils/Paint/Resolve.hh` — apply palette colours when building `ResolvedSource` list

---

### Phase 36 · PR-P1.4 · Glob/regex matching in `source_search`

**Source:** PaintReview.md § P1.4  
**Priority:** P1  
**Scope:** S

In `Paint/Resolve.hh::searchDirectory`, replace the exact `name == needle` check
with a glob match (`fnmatch`) or, if a `source_search_regex = true` key is set,
a `std::regex` match. Make the matching style explicit in the TOML doc.

**Files:**
- `utils/Paint/Resolve.hh`
- `utils/Paint/Types.hh` — add `searchRegex` flag if needed
- `utils/Paint/Book.hh` — parse the new key

---

### Phase 37 · PR-P1.6 · Canonicalise `assertExpectedKind` type tokens

**Source:** PaintReview.md § P1.6  
**Priority:** P1  
**Scope:** XS

Accept only the ROOT class name form (`TH1`, `TH2`, `TGraph`, `TProfile`).
Remove the short aliases (`H1`, `H2`, `Graph`). Update error message to list
accepted tokens.

**Files:**
- `utils/Paint/Render.hh` (or wherever `assertExpectedKind` is defined)

---

### Phase 38 · PR-P1.7 · Support `default_style = ""` opt-out

**Source:** PaintReview.md § P1.7  
**Priority:** P1  
**Scope:** XS

In `Paint/Book.hh::readDefaultStylePath` (or equivalent): if the key is present
and the value is an empty string or `false`, skip loading the defaults file.

**Files:**
- `utils/Paint/Book.hh`
- `tests/test_paint.cc` — add test: `default_style = ""` runs without a defaults file

---

### Phase 39 · PR-P1.8 · Allow `output_name` in visual presets

**Source:** PaintReview.md § P1.8  
**Priority:** P1  
**Scope:** XS

In `Paint/Book.hh::applyVisualPreset`, change the `inheritOutputName` argument
to `true` (same as `mergeResultVisual`), or document the asymmetry in the TOML
reference with a clear rationale.

**Files:**
- `utils/Paint/Book.hh`

---

### Phase 40 · PR-P1.9 · Configurable stats-box fill colour / style

**Source:** PaintReview.md § P1.9  
**Priority:** P1  
**Scope:** S

Add `stats.fill_color` and `stats.fill_style` fields to `StatsSpec` (currently
unused). Read them in `Paint/Book.hh`. Apply them in `applyStatsBox` instead of
the hardcoded `(0, 1001)` values.

**Files:**
- `utils/Paint/Types.hh` — extend `StatsSpec`
- `utils/Paint/Book.hh` — parse new fields
- `utils/Paint/Render.hh` (or `Apply.hh`) — apply in `applyStatsBox`

---

### Phase 41 · PR-P1.10 · Derive legend marker type from draw option

**Source:** PaintReview.md § P1.10  
**Priority:** P1  
**Scope:** S

Replace the hardcoded `"lpf"` in `legend->AddEntry(...)` with a function
`legendOption(ObjectKind, drawOption)`:

- `Hist1D` with `"HIST"` → `"l"` (line only)
- `Graph` with `"AP"` → `"p"` (point)
- 2D hists → `"f"` (fill box)
- Default: `"lpf"`

Allow per-source `legend_option = "l"` override in the TOML.

**Files:**
- `utils/Paint/Render.hh`
- `utils/Paint/Types.hh` — `legend_option` field on `SourceSpec` or `Style`

---

### Phase 42 · PR-P1.11 · Route all formats through `TCanvas::Print`

**Source:** PaintReview.md § P1.11  
**Priority:** P1  
**Scope:** XS

In `Paint/Save.hh::saveCanvas`, replace the hardcoded format whitelist with a
pass-through to `canvas.Print(path)` for all non-PNG formats. ROOT itself will
report unknown formats. Keep the PNG branch (uses `TImage` with scaling).

**Files:**
- `utils/Paint/Save.hh`

---

### Phase 43 · PR-P1.12 · Remove or harden `mutate_input` flag

**Source:** PaintReview.md § P1.12  
**Priority:** P1  
**Scope:** S

Preferred: remove `mutate_input`. The clone cost is negligible for offline
plotting. Alternatively, if keeping it:

1. Document loudly in TOML that in-memory objects are styled and reuse of the
   same path in one plan gives wrong results.
2. Add a guard in `resolveSources`: if the same path appears twice and
   `mutate_input = true`, throw.

**Files:**
- `utils/Paint/Types.hh` — remove or flag the field
- `utils/Paint/Resolve.hh` — remove skip-clone path (or add guard)
- `utils/Paint/Book.hh` — remove parsing (or add loud warning)
- `configs/defaults/Paint.toml` — remove key

---

## Group 9 — Paint P2 (Code Quality)

### Phase 31 · PR-P2.1 · Lift `detail::` merge helpers to public namespace

**Source:** PaintReview.md § P2.1  
**Priority:** P2  
**Scope:** S

`detail::mergeAxis`, `detail::mergeCanvas`, etc. defined in `Style.hh` are
called from `Resolve.hh`. Move them to `namespace Paint` (or a named `Paint::merge`
sub-namespace) so the cross-file usage is explicit rather than accidentally
importing a `detail::` symbol.

**Files:**
- `utils/Paint/Style.hh` — move helpers out of `detail::`
- `utils/Paint/Resolve.hh` — update call sites

---

### Phase 32 · PR-P2.2 · Unify duplicate preset-resolution walk

**Source:** PaintReview.md § P2.2  
**Priority:** P2  
**Scope:** S  
**Note:** Should precede Phase 35 (per-source palette) to avoid compounding duplication.

`applyVisualPreset` and `applySourcePreset` perform the same recursive `use`
walk with cycle detection, differing only in the type they pass
(`RenderResult` vs `Style`). Extract a shared:

```cpp
template <typename T>
void resolvePresetChain(const PresetMap& presets, const std::string& name,
                        std::unordered_set<std::string>& seen,
                        std::function<void(const toml::table&, T&)> merge,
                        T& out);
```

**Files:**
- `utils/Paint/Book.hh`

---

### Phase 33 · PR-P2.3 · Registry-based `ObjectKind` dispatch

**Source:** PaintReview.md § P2.3  
**Priority:** P2  
**Scope:** M  
**Note:** Should precede Phase 34 (TProfile) to avoid adding a 7th site.

Currently adding one `ObjectKind` requires editing ~6 sites. Introduce a
`KindEntry` struct:

```cpp
struct KindEntry {
    std::function<bool(TObject*)> detect;  // dynamic_cast test
    std::string rootClassName;
    std::function<void(TObject*, const Style&)> apply;
    std::function<void(TObject*, const std::string&)> draw;
    std::string defaultDrawOption;
};
```

Register all kinds at startup; `inferKind`, `assertExpectedKind`, `applyToSource`,
`drawSource`, and `defaultDrawOption` become table lookups.

**Files:**
- `utils/Paint/Types.hh` — `KindEntry`, `KindRegistry`
- `utils/Paint/Render.hh` — replace switch/chain with registry lookup
- `utils/Paint/Apply.hh` — idem

---

### Phase 44 · PR-P2.4 · Move `Paint.hh` doc block to Architecture.md

**Source:** PaintReview.md § P2.4  
**Priority:** P2  
**Scope:** XS

Remove the 18-line ASCII-bordered comment from `utils/Paint.hh`. Add a "Paint"
subsection to `docs/Architecture.md` with the same content (already partially
present). Trim the header to a one-line `// Offline ROOT histogram renderer.`.

**Files:**
- `utils/Paint.hh`
- `docs/Architecture.md`

---

### Phase 45 · PR-P2.5 · Make `modeName`/`objectKindName` unreachable-safe

**Source:** PaintReview.md § P2.5  
**Priority:** P2  
**Scope:** XS

Replace the silent fallback `return "single"` / `return "hist1d"` at the end of
each switch with:

```cpp
default:
    throw std::runtime_error("corrupted enum value: " + std::to_string(int(mode)));
```

Or use `__builtin_unreachable()` if the enum is provably exhaustive.

**Files:**
- `utils/Paint/Types.hh` (or wherever these functions live)

---

### Phase 46 · PR-P2.6 · Cap recursion depth in `searchDirectory`

**Source:** PaintReview.md § P2.6  
**Priority:** P2  
**Scope:** XS

Add a `maxDepth` parameter (default 16) to `searchDirectory`. Decrement on each
recursive call; when it reaches 0, stop recursing and optionally warn.

**Files:**
- `utils/Paint/Resolve.hh`

---

### Phase 47 · PR-P2.7 · Rename `detachFromDirectory`

**Source:** PaintReview.md § P2.7  
**Priority:** P2  
**Scope:** XS

Rename `detachFromDirectory` → `detachHistFromDirectory` everywhere it is
defined and called to make clear it only handles TH1/TH2/TGraph.

**Files:**
- `utils/Paint/Resolve.hh`

---

### Phase 48 · PR-P2.8 · Add resolved-style output to `printPlan`

**Source:** PaintReview.md § P2.8  
**Priority:** P2  
**Scope:** S

Extend `printPlan` (dry-run output) to include per-source resolved line colour,
draw option, and preset chain. Gate behind a `--verbose` flag (or a `verbose`
field on `DryRunOptions`).

**Files:**
- `utils/Paint/Render.hh` (or `Illustrator.hh`)
- `_Paint.cc` — add `--verbose` CLI flag

---

### Phase 49 · PR-P2.9 · Fix `dryRun` const-correctness

**Source:** PaintReview.md § P2.9  
**Priority:** P2  
**Scope:** XS

`Illustrator::dryRun(...) const` calls `printPlan(plan_, os)` on mutable state.
Either:
- Drop `const` from `dryRun`, or
- Make `printPlan` take `const RenderPlan&`.

**Files:**
- `utils/Paint/Illustrator.hh`
- `utils/Paint/Render.hh` (if `printPlan` is defined here)

---

### Phase 50 · PR-P2.10 · Replace magic strings with named constants

**Source:** PaintReview.md § P2.10  
**Priority:** P2  
**Scope:** S

Move the following literals into named `constexpr` strings in `Paint/Types.hh`
or at the top of the file that uses them:

| Literal | Candidate name |
|---|---|
| `"configs/defaults/Paint.toml"` | `kDefaultStylePath` |
| `"results"` | `kDefaultResultsKey` |
| `"png"` | `kDefaultFormat` |
| `"HIST"` | `kDrawHist` |
| `"COLZ"` | `kDrawColz` |
| `"APL"` | `kDrawAPL` |
| `"lpf"` | `kLegendDefault` |
| `"__paint"` | `kPaintSuffix` |

Leave ROOT internal names (`"stats"`, `"title"`) in place — those are ROOT
conventions, not free constants.

**Files:**
- `utils/Paint/Types.hh` — add constants
- `utils/Paint/Book.hh`, `Resolve.hh`, `Render.hh`, `Save.hh` — replace literals

---

## Group 10 — Paint Tests

### Phase 51 · PR-TG · Paint test gaps

**Source:** PaintReview.md § Test Gaps  
**Priority:** P1 (after P0/P1 fixes)  
**Scope:** M  
**Depends on:** Phases 23–43 (fixes they exercise)

Add the following cases to `tests/test_paint.cc`:

| Test | What to assert |
|---|---|
| Preset cycle detection | `use = "A" → use = "B" → use = "A"` throws |
| `mutate_input = true` (if kept) | Second render of same path has wrong style |
| PDF / SVG / ROOT save | Files exist after `savePlot`; no exception |
| `image_scale > 1` | Output PNG pixel dimensions are `scale × canvas` |
| `default_style = ""` | Run with no defaults file present; no exception |
| Unknown colour | `parseColor("kRedd")` throws |
| Type mismatch | `line_width = "thick"` throws |
| Overlay stats boxes | All N sources have a visible `TPaveStats` |
| TProfile rendering | TProfile drawn without exception, stats filled |
| Source-style cycle | `applySourcePreset` cycle throws |
| `output_name` override | Output file uses the overridden name |

**Files:**
- `tests/test_paint.cc`

---

## Dependency Summary

```
Phase 2 (TimerRegistry)
    └─► Phase 3 (Instrument)
            └─► Phase 1 (Run timing matrix)
                └─► Phase 12 (Writer stats, if timer-backed)
                └─► Phase 13 (Monitor locking, only if timing confirms)

Phase 10 (Writer stress tests)
Phase 11 (Watchdog barrier)
    └─► Phase 14 (test_writer)

Phase 32 (Unify preset walk)
    └─► Phase 35 (Per-source palette)

Phase 33 (Kind registry)
    └─► Phase 34 (TProfile kind)

Phases 23–43 (Paint P0 + P1 fixes)
    └─► Phase 51 (Paint test gaps)
```

All other phases are independent and can be done in any order within their group.
