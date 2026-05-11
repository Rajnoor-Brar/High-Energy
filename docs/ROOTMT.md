# ROOT MT — breaking the 150% CPU floor

Updated: 2026-05-11. Phase 1 implemented + measured + made opt-in.
Phase 2 spike measured (5.3× at 8 threads), and **Option 2 (full-buffer
two-pass `ProbeIMT`) is now implemented and passing tests**.
Production cut-over is a one-line driver change pending the user's
A/B run on the 10M-event input.

## Phase 1 result (2026-05-11)

**Implemented.**  `Probe::Splitter` (fast-clone basket-level split) and
the per-worker shard plumbing in `ProbeParallel` are live.  Tests pass.

**Measured.**  CPU usage stays at ~150% regardless of `nThreads` with
sharding on; only wall time increases because of the split step.  Per-TFile
basket contention was **not** the bottleneck.

**Diagnosis revised.**  The real limiter is `ROOT::EnableThreadSafety()`'s
global recursive mutex.  ROOT 6 wraps essentially every `TBranch::GetEntry`,
`TFile` op, and `TClass` lookup in that one lock — workers serialize on it
no matter how many independent `TFile` handles they open.  Phase A's
correctness verdict (the lock is required) still holds; we just learned
that the lock is also the throughput limiter, not a separate contention
point on top of it.

**Decision.**  Phase 1 is now **opt-in** via `[probe].split_input = true`
(default false).  Code stays in place because:

1. It is useful for A/B experiments on different ROOT versions / access
   patterns (some setups may genuinely benefit, e.g. NFS-backed inputs).
2. Phase 2 (TTreeProcessorMT) composes naturally on top of per-worker
   shards — they become a `TChain` for the IMT executor.

For production use today, leave `split_input` off.  Reconstruction runs
should be tuned by setting `nThreads` to ~2 (no point spending more).

---

## Context

`_Lambda_Reconstruction` saturates at ~150% CPU regardless of
`nThreads` or `CallbackMode`. Phase A of the prior plan
([../.claude/plans/...](../.claude/plans/read-bots-bot-md-for-behavioural-noble-tome.md))
confirmed empirically that `ROOT::EnableThreadSafety()` is required
for correctness on our access pattern — removing it produces sporadic
crashes inside `Probe::FlatReader` and silent counter corruption. The
serialised core is `TBranch::GetEntry` going through ROOT's global
mutex when many workers pound on baskets in the same `TFile`.

There are two ways to break that floor without disabling thread safety:

1. **Phase 1 — physically split the input file** so each worker reads
   from its own `TFile`. The global mutex is still on, but workers no
   longer queue behind each other on the same file's basket cache,
   `TClass` lookups warm independently, and the per-`TFile` state is
   genuinely per-thread.
2. **Phase 2 — switch reads to `ROOT::EnableImplicitMT` /
   `TTreeProcessorMT`**. ROOT's official multi-threaded reader uses a
   tbb-based pool with finer-grained locks specifically designed to
   parallelise basket decompression. This builds on top of Phase 1's
   shard infrastructure (each shard becomes a TTreeProcessor input)
   and gets us the rest of the way.

Phase 1 first because it is much smaller in scope and will tell us
whether the per-file contention alone is the bottleneck. If Phase 1
gets us to N×, Phase 2 may not be needed. If Phase 1 helps but
plateaus, Phase 2 is the next step. If Phase 1 doesn't help, the
diagnosis was wrong and we re-investigate.

Companion docs:
[CGPTsummary.md](CGPTsummary.md) (overhaul context),
[MAP.md](MAP.md), [Issues.md](Issues.md), [REVIEW.md](REVIEW.md),
[DataFlow.md](DataFlow.md).

---

## Time-cost reality for splitting

Realistic numbers for splitting a single ROOT file into N shards using
ROOT's APIs, keeping entries grouped by event-index so each shard is
self-consistent:

| Method | Mechanism | Throughput | 500 MB | 10 GB | 100 GB |
| --- | --- | --- | --- | --- | --- |
| `TFile::Cp` / TKey copy | bulk byte copy (cannot split mid-tree) | disk-bound | 2–5 s | ~1 min | ~10 min |
| Fast clone (basket-level via `TFileMerger -fk` or `TTree::CloneTree(0)` + `CopyEntries`) | per-basket copy, no decompress/recompress | 200–600 MB/s | 1–3 s | 30–60 s | 5–15 min |
| Recompress copy (read + `Fill`) | full decompress + recompress | 50–150 MB/s | 5–15 s | 1–3 min | 15–30 min |
| Recompress copy, parallel N writers | as above, N×, ROOT mutex contention factored in | ~2× of serial in practice | 3–8 s | 30–90 s | 8–15 min |

For an 88 GB Pythia output (the current
`output/Lambda_Data/_08/Lambda_Recons_7000GeV_10M.root`):

- **Best case** (fast clone, 8 shards, parallel): ~3–5 min wall.
- **Worst case** (recompress, serial): ~30 min wall.

The fast-clone path should be used wherever possible. ROOT's
`TFileMerger` with `kFastIncremental` flags or
`TTree::CloneTree(nentries, "fast")` plus `CopyEntries` over an entry
range gives basket-level copy without recompression. This is the
fastest correct primitive for our format, and it is what `hadd -fk`
uses internally.

The above are wall-time numbers; CPU usage during a fast-clone copy
is ~30–80% of one core (mostly disk-bound on NVMe, more
CPU-saturated on rotational disks). On the user's hardware with NVMe,
expect closer to the optimistic end.

**Implication for "split per run":** an 88 GB-class file is too big
to split on every reconstruction. Even at the optimistic 3 min wall,
that's a 3-min penalty before any reads start, on every run. If the
user runs reconstruction twice with the same input, doing the work
twice is waste. Phase 1 therefore provides:

- **Default behaviour:** cleanup on shutdown (per user's instruction).
- **`[probe].keep_shards = true`:** persistent shards keyed by
  source-file hash + mtime; reused if input is unchanged. Escape
  hatch for repeated runs over a stable input.

---

## Phase 1 — split the input file

### Goal

Each Probe worker reads from a private input shard. The Probe
public API still takes a single `[probe].input_file`. Internal to
`Probe::ProbeParallel::configureProbe`, the input is split into
`threadCount_` shards, written to a temp directory, and each worker
opens its own shard. After the reconstruction finishes (or fatals),
the shards are deleted unless `[probe].keep_shards = true`.

### TOML surface

```toml
[probe]
input_file  = "output/Lambda_Data/_08/Lambda_Recons_7000GeV_10M.root"
nThreads    = 8
split_input = false               # MASTER SWITCH; default false (see result above)
temp_space  = "temp/"             # default: "temp/<record.file.prefix>/"
keep_shards = false               # default false; set true for cached reuse

[record.file]
prefix = "Lambda_Recons"
```

Resolution rules:

- If `[probe].temp_space` is set: use that directory directly.
- Otherwise: derive from `[record.file].prefix` →
  `temp/<prefix>/`. Fall back to `temp/probe_shards/` if `prefix` is
  empty.
- Each invocation creates a unique sub-directory under `temp_space`
  named with the source-file basename + a hash of
  `(input_file, mtime, threadCount)`:
  `temp/<prefix>/<input_basename>_<hash>_<N>shards/`.
- If that directory already contains a complete and current shard
  set (manifest matches), reuse it directly.
- If it exists but is incomplete or stale, replace it.

### Splitting mechanism

Use ROOT's basket-level fast clone. For each tree referenced by
`[probe].event_particles` (e.g. `Protons`, `Pions`):

1. Open input `TFile` once on the main thread.
2. Determine the index-key range per shard. Reuse
   `Probe::ProbeParallel::scanFlatEventKeys` /
   `BranchControl::partitionEvents` (already in tree) to compute the
   `[firstKey, lastKey]` per shard.
3. For each shard `s` in `[0, N)`:
   - Open `temp/.../shard_<s>.root` for `RECREATE`.
   - For each tree:
     - Find the entry range `[firstEntry, lastEntry]` in the input
       tree corresponding to the shard's key range. Reuse
       `prepareEntryBounds` (Parallel.hh:250–318) — exactly the
       per-worker `Bounds` it already computes.
     - Call `inputTree->LoadTree(firstEntry)` then
       `inputTree->CloneTree(0, "fast")` to clone the schema, then
       `CopyAddresses` + `CopyEntries(firstEntry, lastEntry - firstEntry + 1, "fast")`.
       This is basket-level copy; no decompression.
   - Close the shard file.
4. Write a manifest file in the temp dir:
   `manifest.toml` containing source path, source mtime,
   source size, shard count, per-shard entry counts, ROOT version.
   Used to validate cache reuse.

The split runs serially today. Multi-threaded splitting is possible
but introduces the same mutex-contention story we're trying to escape.
Serial fast-clone at ~500 MB/s is acceptable for the one-time cost
and avoids self-contention.

### Probe API change

`Probe::ProbeParallel` gains:

```cpp
class ProbeParallel {
    std::string              inputFile_;            // existing — original source
    std::vector<std::string> inputShards_;          // new — physical shards
    bool                     ownsShards_ = false;   // cleanup on dtor if true
    std::string              shardTempDir_;
    bool                     keepShards_ = false;
    // ...
};
```

`configureProbe` becomes:

```cpp
void configureProbe(std::string inputFile,
                    std::vector<ParticleSpec> specs,
                    std::size_t threadCount,
                    std::size_t requestedEvents,
                    bool userRequestedEvents,
                    std::string tempSpace,            // new
                    bool        keepShards,           // new
                    std::string shardKeyPrefix)       // new (from record.file.prefix)
{
    // existing: resolve threadCount_, eventCount_, partitions...
    // new: ensureShards() to populate inputShards_; sets ownsShards_.
}
```

`runWorkerThread` and `runCollectorThread` already loop over
`eventPartitions_` and construct one `EventStream` per worker. The
only change there is: worker `t` constructs its `EventStream` from
`inputShards_[t]` instead of `inputFile_`. The partition bounds the
worker iterates remain the same — the shard contains exactly that
key range, so the worker streams from entry 0 to the shard's last
entry.

`~ProbeParallel` (or an explicit `cleanupShards()`) removes
`shardTempDir_` if `ownsShards_ && !keepShards_`.

### Driver lifecycle

`Config::configure(...)` is the single configuration point per the
user's instruction. The probe overload reads `[probe].temp_space` and
`[probe].keep_shards` from the TOML and forwards them into
`probe.configureProbe`. After `Config::configure` returns, the probe
already has its shards on disk and `inputShards_` populated. The
event loop (`probe.run(callback)`) does no further setup — only
streaming reads.

```cpp
int main(int argc, char** argv) {
    Probe::ProbeParallel probe;
    Record::Writer       writer;
    Monitor::AsyncLogger logger;

    Config::configure(configPath, project, probe, writer, logger);  // splits, opens, partitions

    Lambda::Parameters phys;
    Lambda::configure(phys, writer, configPath);

    writer.bind(...);
    logger.initialise(writer);
    writer.start();

    probe.run([&](const Probe::Event& ev, int t){           // pure stream
        Lambda::rootAnalysis(ev, t, ctx);
    });

    writer.finish(logger.watch().nEvents);
    // ~ProbeParallel deletes the shard tempdir here
}
```

### Cleanup discipline

- Default: shards are deleted when `~ProbeParallel` runs at end of
  scope. This includes normal completion and stack-unwound exception
  paths.
- If `keep_shards = true`: `~ProbeParallel` skips deletion. The
  directory persists with its manifest; the next run with the same
  input + threadCount + ROOT version skips the split entirely.
- If the process is killed (`kill -9`, hardware fault): shards leak.
  Mitigation: on the next `configureProbe`, scan
  `temp_space/<prefix>/` for orphan directories whose source-file
  hash no longer matches any input. Delete them. Print one warning
  line. Don't crash on unrecognised contents — just leave them.
- `Writer::fatalShutdown` is on a different code path and shouldn't
  call cleanup — Probe's destructor is fine because it runs as the
  driver scope unwinds, before the process exits.

### Critical files

| File | Phase 1 change |
| --- | --- |
| [utils/Probe/Parallel.hh](../utils/Probe/Parallel.hh) | `ProbeParallel` gains shard members + `ensureShards()` + `cleanupShards()`; `configureProbe` signature gains tempSpace/keepShards/prefix args; workers consume `inputShards_[t]` |
| [utils/Probe/ConfigAid.hh](../utils/Probe/ConfigAid.hh) | extend `parseCollectionsFromToml` (or add a sibling parser) to read `[probe].temp_space` and `[probe].keep_shards` |
| [utils/Config/Configure.hh](../utils/Config/Configure.hh) | `Config::configure` forwards new args to `probe.configureProbe`; pulls `prefix` from the resolved `Record::Paths` |
| [utils/Probe/Splitter.hh](../utils/Probe/Splitter.hh) | **new** — owns the fast-clone split, manifest read/write, stale-cache scan |
| [docs/DataFlow.md](DataFlow.md) | document `[probe].temp_space` and `[probe].keep_shards` |
| [docs/MAP.md](MAP.md) | mention `Probe/Splitter.hh` under utils/Probe |
| [tests/test_probe_parallel.cc](../tests/test_probe_parallel.cc) | add a small split-cache test (split into 2, reuse, check manifest) |

### Verification

1. `make test` passes (unchanged tests + new split-cache test).
2. `_Lambda_Reconstruction.exe` over the 88 GB input completes once
   (warm cache) and once again (reuse cache). Wall times:
   - First run: split cost (3–10 min) + reconstruction.
   - Second run with `keep_shards = true`: only reconstruction.
3. Output equivalence: run the same config with `nThreads=1` (no
   split) vs `nThreads=8` (split). Histogram entries and integrals
   match across all `HistogramSet` directories. Diff via a small
   ROOT macro.
4. CPU usage: at `nThreads=8`, observe `>150%` (target: 4–8×). If
   wall time scales near-linearly with thread count up to 4×, Phase 1
   has done its job. If it plateaus around 2–3×, ROOT mutex
   contention on `TClass` and other shared state is still the
   limiter; proceed to Phase 2.
5. Cleanup: after a clean run with `keep_shards = false`, the temp
   directory is gone. After a `kill -9`, a stale directory remains;
   the next run logs one warning and removes it.

### Risks

- **Split cost on every run for ephemeral input.** If the user runs
  reconstruction once per input, every run pays the split cost. The
  optimistic 3 min for 88 GB is a real wall-time hit. Mitigation:
  the manifest-cache reuse path makes repeated runs effectively
  free.
- **Tempfs / disk pressure.** Shards are ~the same total size as the
  input (no recompression). 88 GB doubles to 176 GB on disk during
  the split. Document the requirement; default temp dir should be
  on the same volume as the input to allow rename-based atomicity.
- **Cache invalidation correctness.** The manifest must include
  source-file mtime AND size AND a content hash (or at least the
  first-key + last-key of the source's index). Mtime alone is
  unreliable across filesystems. SHA256 of the source is too
  expensive at 88 GB; first-and-last-key + size + mtime is a
  reasonable approximation.
- **Multi-tree consistency.** Both `Protons` and `Pions` must be
  split using the same key partitions. Reuse the existing
  `prepareEntryBounds` machinery so the splitter and runtime use
  identical boundaries.
- **Empty shards.** If a partition contains no events, the shard
  must still exist (empty trees) so the worker has something to
  open. `EventStream` already handles zero-event input gracefully.

---

## Phase 2 — `EnableImplicitMT` + `TTreeProcessorMT`

### Updated motivation (post-Phase-1)

Phase 1 measurement (above) ruled out per-TFile basket contention as
the limiter. The remaining suspect is `ROOT::EnableThreadSafety()`'s
global recursive mutex, which serialises essentially every
`TBranch::GetEntry`, `TFile` op, and `TClass` lookup across the
process — independent of which `TFile` instance is being read.

`EnableImplicitMT` is ROOT's intended escape hatch from that
serialisation. The IMT path uses a tbb-backed executor and
finer-grained locks specifically designed around basket decompression
and cluster reads. Whether those finer locks are enough to break our
floor is an empirical question. This phase is the only known
in-ROOT path to the answer.

If Phase 2 also yields no improvement, the conclusion is "no
practical way to parallelise ROOT reads further inside one process",
and the live options become multi-process (Fallback A below) or
"accept the floor" (Fallback B). Phase 2 must therefore be
gated behind a small spike experiment before any production refactor.

### What `EnableImplicitMT` actually does

Worth being explicit because the documentation is thin:

- `ROOT::EnableImplicitMT(N)` initialises a tbb thread pool of size
  `N` and flips a process-global flag (`ROOT::IsImplicitMTEnabled()`).
- After that flag is set, certain ROOT primitives — most notably
  `TTreeProcessorMT`, `RDataFrame`, and `TTree::Process` — dispatch
  work to that pool. Plain `TBranch::GetEntry` from your own thread
  does **not** automatically parallelise; you have to use one of the
  IMT-aware entry points.
- `EnableThreadSafety` is implied by `EnableImplicitMT`. Both flags
  end up set. The locks introduced by ThreadSafety remain in place;
  IMT just adds *additional* finer-grained locks for the cluster
  decompression path so that the global lock is not always taken.
- The win is concentrated in **basket decompression**. If your
  workload is dominated by decompression CPU, IMT typically scales
  to 4–8 cores before saturating. If it's dominated by `TClass`
  lookup, `gROOT` access, or callback-side work, IMT helps much less.

Our workload profile (small per-event payload, simple
`std::vector<Lorentz>` build, then `TH1::Fill` via the Writer queue)
is read-heavy. The decompression component should be a meaningful
fraction of the per-event cost. That's the optimistic story; the
spike has to confirm it.

### Spike experiment (do this BEFORE the refactor)

**Status: implemented and measured (2026-05-11). Result: GREEN — proceed
with Phase 2 proper.**

Measured on `output/Lambda_Data/_08/Lambda_Recons_7000GeV_10M.root`
(10 M events, ~304 M proton entries):

| Mode | Threads | Wall (s) | CPU% | Speed-up |
| --- | --- | --- | --- | --- |
| Baseline (ThreadSafety only) | 1 | 9.71 | 92% | 1.0× |
| IMT | 4 | 2.63 | 380% | 3.7× |
| IMT | 8 | 1.83 | 757% | 5.3× |

Branch sums identical across all three runs (-53573.9) → output
equivalence confirmed.  The 150% CPU floor is broken: at N=8 we
reach 757% with 5.3× wall-time speed-up.  Sub-linear past 4 threads
is expected (disk I/O + residual `TClass`/`gROOT` serialisation).

Conclusion: `TTreeProcessorMT`'s cluster-aware locking actually
parallelises basket decompression on our access pattern.  The Phase 1
diagnosis was correct that the global mutex was the limiter, and
Phase 2's premise (IMT escapes it) holds.


Binary at [tests/spike_imt_read.cc](../tests/spike_imt_read.cc).  Builds
via `make tests/spike_imt_read.exe`; not run by `make test`.

Goal: prove or disprove that IMT breaks the floor on **our** access
pattern, before committing to the multi-day refactor that Phase 2
proper requires.

**Run protocol:**

```bash
# 1. Build once
make tests/spike_imt_read.exe

# 2. Baseline — single-threaded with ThreadSafety on
/usr/bin/time -v tests/spike_imt_read.exe \
    output/Lambda_Data/_08/Lambda_Recons_7000GeV_10M.root \
    Protons pX D 1

# 3. IMT runs — repeat at N = 4 and N = 8
/usr/bin/time -v tests/spike_imt_read.exe \
    output/Lambda_Data/_08/Lambda_Recons_7000GeV_10M.root \
    Protons pX D 8

# 4. (Optional) confirm not disk-bound during baseline
iostat -d -w 1     # macOS — watch the read rate during step 2
```

Capture wall time and `%CPU` from `/usr/bin/time -v`'s "Elapsed
wall clock time" and "Percent of CPU this job got" fields.

**Decision matrix (from the binary's header):**

- `nThreads=8` CPU ≈ 800% and wall ≈ baseline/N → land Phase 2 proper.
- `nThreads=8` CPU 200–400% and wall 2–3× speed-up → judgment call;
  weigh the ~3-day refactor cost.
- `nThreads=8` CPU stays ~150% and wall unchanged → IMT doesn't help
  us; skip to Fallback A (multi-process) or B (accept floor).
- `iostat` shows disk-saturated during baseline → Fallback B
  regardless; more CPU can't help.

The spike intentionally ignores the multi-tree problem (it only
chains `Protons`). The point is to measure raw IMT throughput on
our basket layout. If single-tree IMT doesn't move the needle,
multi-tree IMT will not save it.

**Fixture sanity check (already verified):**
```
tests/spike_imt_read.exe tests/fixtures/lambda_fixture.root Protons pX D 1
tests/spike_imt_read.exe tests/fixtures/lambda_fixture.root Protons pX D 4
```
Both runs read all 200 entries with the same branch sum (1753.5) →
TTreeProcessorMT integrates correctly with our ROOT install.  The
fixture is too small (sub-ms scale) to draw throughput conclusions;
real measurement requires the 10M-event input.

### Option 2 (implemented) — full-buffer two-pass

**Status: shipped.**  Files:
[utils/Probe/ParallelIMT.hh](../utils/Probe/ParallelIMT.hh) and
[utils/Probe/EventReaderMT.hh](../utils/Probe/EventReaderMT.hh).
Test coverage in
[tests/test_probe_parallel.cc](../tests/test_probe_parallel.cc) —
three new cases including output-equivalence vs `ProbeParallel`
(per-event momentum sums match to 1e-9).

Algorithm:
1. Allocate a per-event buffer indexed by `event_index - firstKey`,
   one inner `vector<Lorentz>` per `ParticleSpec` ordinal.
2. For each spec, run `TTreeProcessorMT` in parallel.  Each task
   builds a thread-local `unordered_map<event_index, vector<Lorentz>>`
   then hands it off to the orchestrator under a single lock at
   task end.  After `Process()` joins, the orchestrator merges all
   task buffers into the per-event buffer single-threaded — the
   costly part (basket decompression) already ran in parallel.
3. Serial flush: walk the per-event buffer, construct an `Event`,
   call the user callback with `workerIndex = 0`.

Memory profile (10M events, 4 protons + 5 pions per event):
- Per-event skeleton buffer: ~500 MB
- Particle data (peak after both passes): ~3 GB
- Transient task-local buffers during read: ~500 MB
- **Peak ~4 GB.**  Acceptable on the target 16 GB+ machines.

Driver substitution (one-line change):
```cpp
Probe::ProbeIMT probe;            // was: Probe::ProbeParallel
Config::configure(configPath, project, probe, writer, logger);  // unchanged
probe.run([&](const Probe::Event& ev, int t){
    Lambda::rootAnalysis(ev, t, ctx);
});
```

`Config::configure` is templated and accepts either `ProbeParallel`
or `ProbeIMT` (SFINAE-gated). Same configureProbe signature on both
classes; shard-related args are silently ignored by `ProbeIMT`
(IMT doesn't need per-worker files).

Known limitations (documented in `ParallelIMT.hh` header):
- **Vector-stream specs not supported.**  Spec without an
  `event_index` branch errors at `configureProbe` time with a clear
  message.  Phase-2-proper assumption: every spec is keyed by event.
- **Particle order across cluster boundaries not preserved.**
  Reconstruction code that does all-vs-all pairing (our case) is
  unaffected.  If a "leading particle" convention is added later,
  tag entries with their tree-row index and sort after merge.
- **Flush is serial.**  Each event's callback runs single-threaded
  during the flush phase.  If reconstruction work (mass cut +
  `TH1::Fill` via Writer queue) becomes the bottleneck, parallelise
  the flush via `TThreadExecutor` — straightforward extension.

### Other options (deferred)

Two structural choices for the production path:

**Option A — `TTreeProcessorMT` directly.** Smallest delta from the
current code; replaces the `std::thread` worker pool with ROOT's
pool. Multi-tree complication addressed by friend trees (below).

**Option B — `RDataFrame`.** Modern idiom, declarative, handles
event-grouping natively via `Define`/`Aggregate`. Bigger delta
because the read loop becomes a graph of nodes, but composes well
with future analysis. Treat as Phase 2.5; out of scope unless
Option A proves too painful.

Recommend starting with Option A unless the spike already gave us a
reason to want RDataFrame's grouping features.

### Refactor sketch (Option A)

```cpp
// Probe/ParallelIMT.hh — sibling to Parallel.hh, new file.
namespace Probe {

  class ProbeIMT {
    public:
      void configureProbe(std::string inputFile,
                          std::vector<ParticleSpec> specs,
                          std::size_t threadCount,
                          ...);

      template<typename Callback>
      void run(Callback&& cb) {
          ROOT::EnableImplicitMT(threadCount_);

          // Multi-tree: build a primary TChain (Protons), friend
          // each other spec's chain on event_index.  See "Multi-tree
          // problem" below for alternatives.
          TChain primary(specs_[0].tree.c_str());
          primary.Add(inputFile_.c_str());
          for (std::size_t p = 1; p < specs_.size(); ++p) {
              auto* friendChain = new TChain(specs_[p].tree.c_str());
              friendChain->Add(inputFile_.c_str());
              friendChain->BuildIndex("event_index");
              primary.AddFriend(friendChain);
          }
          primary.BuildIndex("event_index");

          ROOT::TTreeProcessorMT processor(primary);
          processor.Process([&](TTreeReader& reader) {
              EventReaderMT er(reader, specs_);  // per-task adapter
              while (er.next()) {
                  cb(er.event(), 0 /* worker index — no longer meaningful */);
              }
          });
      }
  };

} // namespace Probe
```

Driver code becomes a one-line switch:
`Probe::ProbeIMT` instead of `Probe::ProbeParallel`, selected by
`[probe].mode = "imt"` (default `"manual"` until measurement
justifies the flip).

### The multi-tree problem in detail

Our format stores `Protons` and `Pions` as **separate trees** keyed by
`event_index`. `TTreeProcessorMT` processes one logical tree per
task. Three options:

| Option | Mechanism | Refactor cost | ROOT-version risk | Performance |
| --- | --- | --- | --- | --- |
| 1. Friend trees | `primary.AddFriend(friendChain)` + `BuildIndex` | ~1 day | Friend-tree IMT bugs exist in ROOT < 6.24; verify on our version | Best if it works; one TTreeReader sees all branches |
| 2. RDataFrame | `RDataFrame` with `Define` joining trees | ~3 days | Most modern path; well-supported in 6.26+ | Comparable to (1); more idiomatic |
| 3. Schema redesign | Single tree with struct-of-vectors per event | ~1 week + touches Pythia data driver | None (we control it) | Likely best; single-tree IMT is the well-trodden path |
| 4. Manual join | Two `TTreeProcessorMT` passes + post-merge | ~2 days | Low | Throws away IMT's task locality; probably no faster than Phase 1 |

(1) is the smallest delta but pays in version-fragility. Validate by
running the spike a second time with friended chains before committing.
(3) is the most invasive but the most maintainable long-term — the
schema is ours to change, and the data already logically groups by
event. If we're already touching the Pythia driver for other reasons,
fold it in.

### EventStream adapter

The current `Probe::EventStream` owns its `TFile` and drives entry
iteration. The IMT path needs a different shape: ROOT owns the
`TTreeReader`, hands us one per task, and we drain it.

Plan:
- Keep `EventStream` (file-owning, used by `ProbeParallel`).
- Add `EventReaderMT` — wraps a `TTreeReader&` passed in by ROOT;
  binds `TTreeReaderValue<>` for each branch in `ParticleSpec`;
  exposes the same `next() / event()` surface as `EventStream` so
  user callbacks don't change.
- Branch-type detection in `Probe::BranchControl::detectType`
  already handles the type mapping we need; reuse it for the
  `TTreeReaderValue<T>` instantiations.

### Critical files

| File | Phase 2 change |
| --- | --- |
| [tests/spike_imt_read.cc](../tests/spike_imt_read.cc) | **new** — the spike binary; built only when needed |
| [utils/Probe/ParallelIMT.hh](../utils/Probe/ParallelIMT.hh) | **new** — `ProbeIMT` class; mirror of `ProbeParallel` using `TTreeProcessorMT` |
| [utils/Probe/EventReaderMT.hh](../utils/Probe/EventReaderMT.hh) | **new** — per-task `TTreeReader` adapter, exposes `EventStream`-like API |
| [utils/Probe/Parallel.hh](../utils/Probe/Parallel.hh) | unchanged; `ProbeParallel` remains the manual default |
| [utils/Probe/ConfigAid.hh](../utils/Probe/ConfigAid.hh) | parse `[probe].mode` ("manual" \| "imt") |
| [utils/Config/Configure.hh](../utils/Config/Configure.hh) | dispatch to `ProbeIMT` when `mode == "imt"` (templated probe arg, or `std::variant`) |
| [utils/Probe/Splitter.hh](../utils/Probe/Splitter.hh) | optional: flush larger clusters when writing shards, to improve IMT task granularity |
| [docs/ROOTMT.md](ROOTMT.md) | post-decision: record Phase 2 measurement and which mode is the new default |

### Verification

1. **Spike before refactor.** Decision gate per "Spike experiment" above.
2. **Output equivalence.** Reconstruction histograms entry counts and
   integrals match between `mode = "manual" / nThreads = 1` and
   `mode = "imt" / nThreads = 8`. Diff via a small ROOT macro.
3. **TSan run.** Build `_Lambda_Reconstruction.exe` with
   `-fsanitize=thread` against the smoke fixture; no warnings under
   IMT mode. Especially important because we have both ROOT's IMT
   pool and our Writer's scribe thread in flight simultaneously.
4. **Repeat-run stability.** Stress run: 50× reconstruction with
   IMT mode; zero crashes, zero diffs. ROOT-internals races
   surface sporadically; one clean run is not enough evidence.
5. **Manual path remains the default** until measurement justifies
   flipping it. Phase 2's value is opt-in until proven, just like
   Phase 1 became opt-in after measurement.

### Risks

- **IMT may not break the floor on our pattern.** Worst case: same
  150% wall, same wall time. The spike is the cheap way to find
  out before committing.
- **`EnableImplicitMT` is process-global and sticky.** Once on,
  every ROOT call routes through the IMT pool. Co-existing
  threads — our Writer scribe in particular — share that pool's
  lock topology. Verify under TSan.
- **Pythia drivers must not initialise IMT.** `PythiaParallel`
  manages its own thread pool. If `Probe.hh` is included
  transitively into a Pythia driver and IMT initialises by
  accident, we get N × M threads. Mitigation: `ProbeIMT::run` is
  the only call site for `EnableImplicitMT`; Pythia drivers do not
  instantiate `ProbeIMT`.
- **Friend-tree bugs in older ROOT.** If we land on a system with
  ROOT < 6.24, friended chains under IMT are known-flaky. Mitigation:
  feature-detect the ROOT version at `configureProbe` time and
  refuse to run in IMT mode if too old. Fall back to manual.
- **`TClass` first-load races.** ROOT's class registry can race
  on first access. IMT does not fix this; it can make it more
  likely by spreading first reads across threads. Mitigation:
  pre-warm all `TClass::GetClass(...)` for every payload type on
  the main thread before calling `TTreeProcessorMT::Process`.
- **Cluster granularity.** Default Pythia output has small basket
  clusters → tiny IMT tasks → scheduling overhead dominates.
  Mitigation: extend the Splitter (Phase 1 code) with a "flush
  large clusters" mode and run IMT against the resharded files.
  Caveat: if Phase 1 stays opt-in, this is two opt-ins to compose.
- **Disk I/O ceiling shadows the question.** On NVMe at 3+ GB/s
  with 88 GB compressed input, wall time of a perfect-CPU read is
  ~30 s (just disk-bound). Anything below that floor doesn't
  benefit from more CPU. Worth measuring `iostat` during the spike
  to see if we're actually disk-saturated, in which case
  "accept the floor" is the right answer.

### Fallback A — multi-process

If Phase 2 fails the spike: drop the in-process MT requirement
entirely. Fork N processes from the driver, each with its own
ROOT runtime (and therefore its own copy of every global lock).
IPC the histogram fills back to a coordinator that aggregates
into the final TFile.

Rough shape:
- Main process partitions input by event-index range (reuse
  Probe's `partitionEvents`).
- Forks N children. Each child runs the existing single-threaded
  reconstruction over its partition, writing to a per-child
  temporary `.root` file.
- Main process `wait()`s on all children, then `hadd`s the
  per-child files into the final output.
- `hadd` is fast for our histogram-only output (no event-level data
  written) — minutes for 88 GB-sized inputs is unlikely; expect tens
  of seconds.

Cost: ~2 days. Rules:
- No `std::thread` inside any child; each child is single-threaded.
  This sidesteps all ROOT-MT issues by construction.
- Crash-tolerant: if a child segfaults, the main process logs
  which partition failed and re-launches that child. Easier
  fault isolation than threaded code.
- Memory cost: N × peak-RSS of the single-threaded path. For our
  workload that's manageable.

This is the heaviest-weight option but the most certain to work.
It is also the path that other ROOT users on HPC clusters
typically end up on when in-process MT doesn't pay off.

### Fallback B — accept the floor

If Phase 2 spike fails and multi-process is not worth the
complexity:

- Set `[events].nThreads = 2` as the production default. Past 2
  threads the global mutex wins and adds only overhead.
- Document the ceiling in `Issues.md` with the measurements that
  led to it.
- Revisit when ROOT relaxes the lock (track `ROOT::Internal`
  changelogs) or when the input file is regenerated in a
  more IMT-friendly layout.

This is the cheapest option and the right one if the workload's
real ceiling is disk I/O rather than CPU.

---

## Updated phase ordering and stop conditions

```
Phase 0 (done): ThreadSafety experiment confirmed lock is required.
Phase 1 (done, opt-in): per-worker shard files.
   └─ measurement showed no CPU-floor improvement.
      Default OFF.  Code retained for A/B and Phase 2 composition.

Phase 2 spike (next): TTreeProcessorMT on a single tree, 100 LOC.
   ├─ near-linear scaling to ≥4 threads → land Phase 2 proper.
   ├─ marginal (2-3×)                    → judgment call; cost vs benefit.
   ├─ flat (~150%)                       → skip to Fallback A or B.
   └─ disk-bound from iostat             → Fallback B (accept the floor).

Phase 2 proper (if spike succeeds): ProbeIMT + EventReaderMT.
   ├─ multi-tree via friend chains (option 1) by default.
   ├─ falls back to schema redesign (option 3) if friend trees flake.
   └─ ships behind [probe].mode = "imt"; manual remains default
      until output-equivalence + stress run pass.

Fallback A (if spike fails, throughput still needed): multi-process.
Fallback B (if spike fails, throughput not worth the cost): accept floor.
```

Each transition ends with a measurement, not a guess. Don't refactor
to Phase 2 without the spike result in hand — Phase 1 was the lesson.
