# Issues — active investigation

Updated: 2026-05-10.

Probe and Writer have both been overhauled. The active path is:

1. Probe reads input events with `Probe::ProbeParallel`.
2. Lambda reconstructs candidates.
3. Lambda submits queued fill requests to `Record::Writer`.
4. Writer's scribe thread is the only normal path that mutates / writes /
   closes ROOT output objects.

Companion docs: [CGPTsummary.md](CGPTsummary.md) (overhaul context),
[REVIEW.md](REVIEW.md) (expansions / improvements backlog),
[MAP.md](MAP.md) (file map), [DataFlow.md](DataFlow.md) (TOML/runtime
flow).

This file is the active open-issue list, not the long-term backlog. The
single open issue today is **scaling does not follow `nThreads`**. The
fix is most likely a sequence of small changes rather than one big
restructure.

---

## P0 — Scaling still does not follow `nThreads`

Observed:

- Raising `nThreads` does not produce expected throughput scaling.
- At 8 configured threads the process shows roughly 1–3 cores busy
  rather than 8 saturated workers.

This is not yet narrowed to a single cause. There are several
contributors that compound, and instrumentation is the prerequisite.

### Suspect ranking (by current evidence)

| Rank | Suspect | Why it is plausible | What would confirm it |
| ---- | ------- | -------------------- | --------------------- |
| 0 | Probe `CallbackMode::CollectorThread` default | Workers read events, but the collector calls `Lambda::rootAnalysis` serially. Now that Writer queues ROOT mutation safely, `WorkerThread` mode should be retested. | `probe.stats()` reports `callbackMode=CollectorThread`; switching to `WorkerThread` raises core load and throughput. |
| 1 | `BlockTimer` per-event file I/O in `rootAnalysis` | `modules/Lambda.hh:83` constructs `BlockTimer timer("Whole Analysis");` once per event. `BlockTimer` opens `output/timer.log` in append mode in its constructor. Per-event file open is a serialised I/O dependency under multi-threaded callbacks. | Removing the line restores throughput scaling, even before any other change. |
| 2 | `AsyncLogger::publish` + `publishThreadStats` mutex | Both lock `AsyncLogger::mutex_`. Each `rootAnalysis` event calls them twice. Under WorkerThread mode, `nThreads × 2` lock acquisitions per event hit a single mutex. | Per-call `Monitor::ScopeTimer` (REVIEW §3.2) shows publish wall time growing with `nThreads` while CPU stays low. |
| 3 | Lambda reconstruction loop | `reconstructCandidates` is `O(nProtons × nPions)`, materializes every unvalidated pair, computes boost-based `cosTheta` *before* the cheaper invariant-mass cut, and reads `lambda.M()` twice per pair. | Wall time per `reconstructCandidates` dominates per-event budget; reordering the cuts reduces it. |
| 4 | Writer single-scribe ceiling | One thread applies all fills. Each event submits one `ParticleRequest` plus optional checkpoint. | `writer.stats().backlog` grows monotonically; producers block on `queueNotFull_`; scribe CPU is hot. |
| 5 | `ParticleRequest` particle-vector copies | `fillParticleEvent` copies each candidate vector into `ParticleGroupFillRequest::particles`. For large events these copies bloat queue memory and CPU. | Move-aware fill API (REVIEW §2.2) cuts copy time noticeably. |
| 6 | ROOT global mutex inside `EventStream::next` | `ROOT::EnableThreadSafety()` wraps `TBranch::GetEntry`. With many workers reading at high frequency, ROOT serializes I/O. | `EventStream::next` wall time scales linearly with `nThreads` while CPU stays roughly constant. |
| 7 | `writer.finish` post-loop cost | `TFile::Write` + `TFile::Close` runs single-thread after the event loop. Currently considered unlikely to dominate. | Total runtime dominated by `writer.finish`, not by the event loop. |

Do not assume Writer parallelisation (REVIEW §2.1) is the next correct
implementation until instrumentation has separated Lambda reconstruction
cost from Writer scribe cost from queue-wait cost.

### Recommended sequence

Each step ends with a measurement; the data drives the next step.

1. **Replace `BlockTimer`.** Land the standardised `Monitor::Timer`
   family from REVIEW §3.2. Remove the `BlockTimer` line in
   `rootAnalysis` and the commented one in `reconstructCandidates`. The
   replacement timer writes to thread-local buffers and never opens a
   file on the hot path. Re-run the `nThreads ∈ {1,2,4,8}` sweep.

2. **Switch to `WorkerThread` callback mode.** Either via the new
   `[probe].callback_mode` TOML key (REVIEW §1.1) or, until that lands,
   a one-line `probe.setCallbackMode(Probe::CallbackMode::WorkerThread)`
   in `_Lambda_Reconstruction.cc`. Run the same sweep.

3. **Inspect `probe.stats()` and `writer.stats()`.** Print at end of
   run (or at periodic checkpoint). Look for:
   - Probe `produced` vs `consumed` (in CollectorThread mode);
   - Probe `progress[]` per-worker variance;
   - Writer `backlog`, `maxBacklog`, and whether it reached
     `queueCapacity`.

4. **Read the timer registry.** Wall + CPU time per labelled region.
   The CPU/wall ratio identifies serialisation. Initial labels per
   REVIEW §3.3.

5. **Reorder reconstruction cuts.** Move the invariant-mass cut before
   `cosTheta` in `reconstructCandidates`. Cache `lambda.M()`. Stop
   copying `ev[label]` into local `std::vector<Lorentz>`. Re-measure.

6. **Decide based on data.** If the Probe-side timers and Writer
   backlog are healthy and Lambda timers dominate, the rest of the
   work is in `modules/Lambda/Reconstruction.hh`. If Writer backlog
   saturates, design multi-lane Writer per REVIEW §2.1. If
   `EventStream::next` dominates with low CPU, the ROOT global mutex
   is the floor and no Probe-side restructure helps — at that point,
   pre-sharded input or RDataFrame+IMT is the path.

The first three steps are the cheapest available signal. They should
land before any architectural change.

---

## Required instrumentation before changing architecture

Implement once via the `Monitor::Timer` family proposed in
[REVIEW §3.2](REVIEW.md). Initial labels:

- Probe:
  - per-worker `EventStream::next`,
  - per-worker queue-push wait (CollectorThread mode),
  - collector pop wait,
  - collector callback-dispatch wall.
- Lambda callback:
  - `rootAnalysis` total,
  - `reconstructCandidates`,
  - `fillCandidates` enqueue cost,
  - `AsyncLogger::publish` and `publishThreadStats` wall time,
  - `ev[label]` lookup cost (sanity).
- Writer:
  - `applyParticleRequest` (scribe-side) split into count / hist /
    graph/profile / tree fill,
  - `pushNormal` queue-wait,
  - `writeCheckpointFile`,
  - `writeAllToCurrentFile`.
- End to end:
  - event-loop wall vs `writer.finish` wall.

Print `probe.stats()` and `writer.stats()` once at end of run, plus
optionally on each `writer.checkpoint`. Run the same config with
`nThreads ∈ {1, 2, 4, 8}`.

Decision question: are producers blocked **before** enqueue (Probe-side
or analysis-side cost) or **after** enqueue (Writer scribe ceiling)?

---

## Lambda analysis-loop candidates

Verified hotspots in `modules/Lambda/Reconstruction.hh` and
`modules/Lambda.hh` (also in [REVIEW §4](REVIEW.md)):

- `rootAnalysis` copies Probe vectors via `const std::vector<Lorentz>
  protonList = ev[...]`. Use `const auto&`; the event is alive for the
  callback.
- `reconstructCandidates` pushes every proton×pion pair into
  `result.unvalidated` before any filtering. With sizes 50p × 50pi this
  is 2500 entries before any cut. It also computes `cosTheta` before the
  mass cut.
- Reorder: mass cut first, then `cosTheta` only on survivors. Cache
  `lambda.M()`.
- `fillParticleEvent` copies candidate vectors into queued requests.
  Today's `Recording::fillCandidates` builds the `Candidates` struct
  locally and could move from it; see REVIEW §2.2.

These changes are independent of architecture. They land in any order
relative to the Probe / Writer instrumentation.

---

## Writer-throughput hypothesis (only if measurement points here)

Writer is intentionally single-scribe. That trades parallelism for
output-mutation correctness. It can become the throughput ceiling.

Before parallelising:

- Confirm `writer.stats().maxBacklog == queueCapacity` (saturated).
- Confirm producers spend wall time blocked on `queueNotFull_`.
- Confirm scribe CPU is hot during the event loop, not during
  `writer.finish`.
- Confirm `applyParticleRequest` time per event is comparable to the
  combined Lambda enqueue rate × nThreads.

If those align, the safe parallel-Writer shape is REVIEW §2.1
(per-record-key lanes, per-lane scribe, barrier on checkpoint and
finish). Do not write the same `TFile` from multiple threads under
ROOT thread-safety; per-object ownership by lane is the invariant.

---

## Current config / data-flow mismatches

(Cross-referenced from [DataFlow.md](DataFlow.md).)

- `[probe.index]` keys (`sorted`, `ascending`, `monotonic`) appear in
  `configs/Lambda_Reconstruction.toml` but `Probe::buildIndexSpecs`
  hardcodes the `IndexSpec` as ascending/dense/grouped. Either parse
  them or remove from sample configs (REVIEW §1.1).
- Writer-owned data generation and the smoke-test fixture use
  `event_index`, while `configs/Lambda_Reconstruction.toml` currently
  lists `Index` in `[probe].event_particles`. This must match the
  actual input ROOT file: a Probe-driven reconstruction over a file
  produced by `_Lambda_Data.cc` should use `event_index`.
- `[record].save_checkpoints`, `save_log_threads`, `save_heartbeat`,
  `save_final_log` appear in configs but are not currently read by code.
- `Monitor::configureMonitor` runs before `[events]` is parsed in the
  Probe-pipeline `Config::configure`. Progress-bar `barInterval`
  derivation may use the default event count rather than the resolved
  one. Verify whether this affects current terminal output.
- `_Lambda_Parallel.cc` does not explicitly apply the parsed thread
  count to `Pythia8::PythiaParallel`. `_Lambda_Data.cc` does. Cleanup
  alongside the per-section thread-config split (REVIEW §5).

---

## Done since prior Issues snapshot

For history; nothing in this list is open work.

- Probe overhaul: `Probe::ProbeParallel`, callback modes, partition
  precompute, queue plumbing.
- Writer overhaul: declaration APIs, queue lanes, scribe loop, barriers,
  checkpoint/finish/fatal write, `Meta` integration.
- Lambda migration to Writer-owned output: `Lambda::configure`,
  `fillParticleEvent`, removal of `RootArray` from active drivers,
  Writer-owned `Protons`/`Pions` trees in data generation.
- Doc/Plan baseline: this Issues file replaces the prior backlog list.

If anything below the line above looks open, double-check the live code
before acting on it.
