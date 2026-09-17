# Audit (Round 2) — vulnerabilities, design, performance, dead code

Updated: 2026-06-12. Status: complete. Every load-bearing claim was verified
against source (file:line cited); dead-code items were confirmed by
whole-repo reference search, not assumed.

Second-pass audit of `utils/` on the post-remediation codebase (after the
Phase 1–3 fixes recorded in `docs/UtilsAudit.md` §11). Focus areas this round:

1. Overlooked vulnerabilities & robustness gaps
2. Design issues
3. Performance
4. Futureproofing & expansion suggestions
5. **Separate section:** dead code, clutter, parameter/state reduction

## 1. Vulnerabilities & robustness

### 1.1 Shell injection via `popen` in `sha256File` — HIGH (the one real security bug)
`Record/Meta.hh:121-147` builds a shell command by string concatenation:
`"shasum -a 256 \"" + path + "\""` → `popen`. `path` comes from config values
and CLI args (`integrityAddFileSha(writer.meta(), configPath)` in every driver,
plus cmnd/limits paths). A path containing `"`, `$(…)`, or a backtick breaks
out of the quoting and executes arbitrary shell. Today you only attack
yourself, but the moment a config from a collaborator or a *file inside a
downloaded dataset directory* gets hashed, a maliciously named file is code
execution. It is also a correctness hole: legit paths with quotes fail, and
machines without `shasum`/`sha256sum` silently record `"unavailable"`.
**Fix:** drop the shell entirely — embed a ~120-line public-domain SHA-256 in
`Utility/` (header-only, works on all platforms, no tool dependency).

### 1.2 Checkpoint write is not crash-safe — MEDIUM
`Record/Recording.hh:194-210` (`writeCheckpointFile`) opens the checkpoint
path with `"RECREATE"`, which truncates the *previous* checkpoint before the
new one is written. A crash/power-loss mid-checkpoint destroys both the old
and new checkpoint — exactly the moment checkpoints exist for.
**Fix:** write to `<path>.tmp` and `std::filesystem::rename` over the old file
on success (atomic on POSIX).

### 1.3 Unsynchronized `writerException_` read in watchdog — LOW (TSan-visible race)
`writerException_` is written under `fillMutex_` (`setWriterException`,
`Record/Threading.hh:255-258`) but read without any lock in the watchdog at
`Threading.hh:178` and `:201`. `std::exception_ptr` is not atomic; this is a
formal data race (benign on current platforms, flagged by TSan, easy to fix:
read it under `fillMutex_` or make it a `std::atomic<bool> hasError` +
locked fetch).

### 1.4 No signal handling anywhere — MEDIUM (robustness)
Ctrl-C / SIGTERM / batch-system kill leaves a truncated un-closed ROOT file
and no final log; the carefully built Fatal/checkpoint machinery never runs.
A small `std::signal` handler that sets a global `std::atomic<bool>` polled by
the event loop (drivers check it and call `writer.fatalWrite(...)`) would make
the existing fatal path actually reachable from the outside world. Batch
systems (HTCondor/SLURM — relevant for the real-data phase) send SIGTERM with
a grace period; right now that grace period is wasted.

### 1.5 Smaller items
- `Config/Reader.hh` `sr_padding` is validated non-negative but not bounded
  above: `sr_padding = 1000000000` → `setw(1e9)` → a ~1 GB string allocation.
  Clamp to a sane max (e.g. 10).
- Output directories come straight from TOML (`[record.paths].directory`) with
  no normalization — `directory = "../../../etc/x"` happily writes outside
  the project tree. Fine for a personal tool; worth a `lexically_normal` +
  is-under-root check before the Ingest/real-data phase.
- `std::regex` from config (`source_search`) can be made to backtrack
  pathologically (hang, not crash). Local tool ⇒ acceptable; just don't ever
  feed it untrusted configs.
- `Meta::fillDerived` still has one `catch (...) {}` (around `std::stod`,
  `Meta.hh:285-287`) — harmless here (guarded by `== 0.0` check) but the
  pattern the Phase 1 pass eliminated elsewhere.

## 2. Design issues (Record deep-dive)

### 2.1 Eight parallel "master + clones" structs — collapse to one template
`Record/Types.hh` defines `ParticleTH1/TH2/Graph/Profile` *and*
`Hist1DRecord/Hist2DRecord/GraphRecord/ProfileRecord` — the same
`{master*, vector<unique_ptr> clones, meta}` shape eight times, which then
forces four `cloneXxxImpl` + four `mergeXxxImpl` template pairs
(`Cloning.hh`). One `template <class TObj, class Meta> struct CloneSet`
collapses 8 structs → 1 and 8 clone/merge functions → 2 (TH1-like with
`SetDirectory`, TGraph-like without). Mechanical, no behavior change.

### 2.2 `fillDerived` takes a whole `Config::Register` to read one field
`Meta.hh:259-263` — only `root.beamEnergy` is used, and `Writer::finish()`
(`Lifecycle.hh:277`) already has to pass a dummy `Config::Register{}` to
satisfy it. Change the parameter to `const std::string& beamEnergy`. This is
also a step toward deleting `Register` (see §5.3).

### 2.3 `applyTreeRowRequest` validates with a per-row heap map
`Recording.hh:164-192` builds an `unordered_map<RecordKey,bool>` for *every
tree row* to check all branches were supplied exactly once. The Protons/Pions
trees go through this for every candidate (≈28k rows/1k events). The shape of
a row is fixed at declaration time — validate the caller's list against
`branchOrder` positionally (or sort-once-compare), zero allocations.

### 2.4 Watchdog Heartbeat kind is a no-op
`WatchRequest::Kind::Heartbeat` is queued by the logger and dropped on the
floor by the watchdog (`Threading.hh:168-172`, "reserved for future"). Each
heartbeat is a mutex lock + queue churn for nothing. Either implement the
"future artifact" or stop emitting them until needed.

### 2.5 Minor
- `drainAndStopWorkers` spin-polls queue emptiness at 200 µs
  (`Threading.hh:235-248`); a condition-variable wait would be cleaner
  (finalize-only path, so cosmetic).
- Anonymous-namespace `kFatalGracePeriod` in a header (`Lifecycle.hh:245-247`)
  — per-TU copy; make it `inline constexpr` in `Record`.
- `scaleAndWrite` (`Recording.hh:10-28`) silently returns on null object and
  on failed `Clone` — acceptable, but a one-line warn would match the Phase 1
  no-silent-failure policy.

## 3. Design & robustness — Monitor, Probe, Paint

### 3.1 Stall detection runs on wall-clock — MEDIUM (Monitor)
`snapshot.lastUpdateTime` is `system_clock` (`Monitor/Threading.hh:91,144`),
and `isFatalStalled` compares wall-clock differences (`Threading.hh:99-118`).
An NTP step / DST adjustment / VM clock jump forward of ≥ `5×stall_threshold`
**fires `fatalShutdown` on a healthy run**; a backwards step masks a real
stall. The run loop itself already uses `steady_clock` for its deadlines —
use `steady_clock` for `lastUpdateTime`/idle math too, keep `system_clock`
only for display strings.

### 3.2 `ScopeTimer` is a global contention point — MEDIUM (perf)
Every `MONITOR_SCOPE_TIMER` destruction does: construct a `std::string` from
the literal, lock a **single global mutex**, hash the string
(`Monitor/Timer.hh:31-36`). The two hottest Writer paths are timed
(`pushFill`, `applyParticleRequest` — 284k each in a 1k-event run, ×2 with
Probe timers), so all workers serialize on this mutex and the profiler
perturbs what it measures. Fixes in increasing order of effort: key the map
by `const char*` (string literals have stable addresses — kills the string
allocation), per-thread registries merged at `dump()` (kills the contention),
or both. ~20 lines.

### 3.3 WorkerThread mode cannot abort early — MEDIUM (Probe)
In `runCollectorThread`, a failing worker/collector calls `requestStop()` and
everything winds down. In `runWorkerThread` (`Probe/Threading.hh:97-143`)
there is no stop flag in the loop: if partition 0 throws in the first second
of a 2-hour run, the other N−1 partitions run to completion before the error
is rethrown. Add a shared `abort` flag checked per iteration (same pattern
collector mode already uses).

### 3.4 Mixed-mode silently truncates Feed data — LOW (Probe)
Both loops break when the Event stream ends (`!contE && hasEventData`,
`Threading.hh:128,204`) even if the Feed stream still has rows. If
intentional ("events drive the run"), document it in `ProbeConfig`; if not,
it's silent data loss in Mixed mode.

### 3.5 Per-event allocation churn in the streaming hot path — design+perf (Probe)
`Probe::Event` is `unordered_map<string, vector<Lorentz>>` plus a
two-level `map<string, map<string, AuxColumn>>` (`Probe/Types.hh:142-169`).
Every event: map node allocations, string hashing on every callback access,
then `frame = QueuedFrame{}` discards all that memory per frame. Fine at 1k
events; at NanoAOD scale (1.5M events × several collections) the maps will
dominate the read cost. The fix direction (when ML throughput matters, not
before): labels are fixed at configure time — intern them to small indices,
make `Event` hold `vector<vector<Lorentz>>` + a shared label→index table,
and recycle frames through a pool instead of reallocating. API can stay
string-keyed via the existing `operator[]`/`column<T>` helpers.

### 3.6 Three overlapping "mode" states on ProbeParallel — design (Probe)
`requestedMode` (StreamMode), `activeMode_` (ActiveMode), and `streamType_`
(StreamType, comment says "legacy" yet `determineStreamType()` is still
called from `Configuration.hh:61`). Three enums describe one question —
"what are we streaming?" Either finish the migration (fold StreamType's
flat-vs-vector answer into per-spec data, where it actually belongs) or
remove the "legacy" label. Right now a reader cannot tell which one is
authoritative.

### 3.7 Paint kind detection is order-fragile — design (Paint)
`kindRegistry()` (`Paint/Apply.hh:103-147`) matches with overlapping
dynamic_cast predicates (Hist1D = TH1 ∧ ¬TH2 ∧ ¬TProfile) iterated in
**map-key order** — correctness depends on every matcher being mutually
exclusive rather than on priority. Adding TEfficiency/THStack/TF1 for the
real-data phase will force the issue. Switch to an ordered
`vector<KindEntry>` (most-derived first) and a `registerKind()` hook; that
also gives Paint its missing extension point.

### 3.8 `Illustrator` still has the load→resolve→render trap — LOW (Paint)
`resolve()` before `load()` operates on an empty book;
`render()` requires manual `resolve()` (`Illustrator.hh`). Make `render()`/
`dryRun()` lazily run whatever is pending — deletes both runtime traps and
shrinks driver code to two lines.

## 4. Futureproofing & expansion

1. **RNTuple is coming.** ROOT is replacing TTree with RNTuple as the default
   columnar format (already production in ROOT 6.34+; ALICE AO2D and CMS are
   migrating). Everything persisted goes through ~6 call sites in
   Record (`declareBranch`/`Fill`/`Write`) — keep it that way, and note in
   DataContract.md that the contract is "columns of PODs", not "TTree".
   When Ingest lands (audit §10 in UtilsAudit.md), `Detect.hh` should sniff
   RNTuple vs TTree from day one; uproot already reads both.
2. **Monitor sinks.** Terminal rendering is hard-wired ANSI. For batch-farm
   runs you'll want a "plain log line every N min" mode (no escape codes in
   SLURM logs). A `Sink` interface (terminal / plain-file / silent) on
   AsyncLogger is a small refactor now, painful later.
3. **Paint**: a `registerKind()` hook (§3.7) + per-result output formats
   already cover most plotting growth; the missing visualization feature for
   the analysis phase is **ratio/pull panels** (data/MC comparison) — worth
   designing as a `mode = "ratio"` rather than ad-hoc canvas division.
4. **Reproducibility**: `Meta` records git SHA + config SHA, but not the
   **input dataset checksums** for Probe runs (only metadata merge). When
   real data arrives, add the input file's SHA (cheap once §1.1's in-process
   SHA-256 exists) so every output is traceable to exact input bytes.
5. **C++ standard**: the codebase is clean C++17; `std::format` (C++20)
   would delete most ostringstream plumbing in Monitor/Utility, and
   `std::span` fits the Column APIs. ROOT ≥ 6.30 supports C++20 — flip
   `-std=c++20` in one place when convenient, no urgency.

## 5. Dead code, clutter, parameter & state reduction

### 5.1 Dead code (verified by reference search)
| Item | Evidence | Action |
|---|---|---|
| `Physics/Kinematics.hh` Column-batch helpers: `invariantMassColumn`, `transverseMomentum`, `momentum`, `pseudorapidity`, `rapidity`, `azimuthalAngle` (Columns), plus `fromComponents`, `cosOpening`, `deltaR` | zero callers outside the file (only `invariantMass`/`deltaPhi` are used, and only by tests) | Delete the Column family (pre-trait-table era leftovers); keep `invariantMass`/`deltaPhi`/`deltaR` as the documented kinematics API |
| `Config::configuration()` (`Config.hh:59-69`) | zero callers — drivers use `Config::configure<T>` or `readConfigValues` | Delete |
| `index_sorted` / `index_ascending` / `index_monotonic` TOML keys → `indexSorted/indexAscending/indexMonotonic` fields ×2 specs (`Probe/Types.hh:42-44,53-55`, parsed at `ConfigAid.hh:173-175`) | parsed, **never read anywhere** — config keys that promise behavior they don't deliver | Delete fields + parsing, or implement (the CollectorThread monotonic check at `Probe/Lifecycle.hh:180` is unconditional and ignores the flag) |
| `ProbeIMT` + `ParallelIMT.hh` + IMT sections of `Methods.hh`/`Threading.hh` (~250 lines) | only callers: `tests/spike_imt_read.cc` (a spike) and one test section; no driver uses it; its design buffers the entire file in memory (`Threading.hh:248`) | Decide: promote to a supported path with a driver, or move to `archive/` with the spike. Keeping "experimental but compiled+tested forever" is the worst option |
| `WatchRequest::Kind::Heartbeat` handling | queued by Logger, dropped by watchdog (§2.4) | Stop emitting or implement |
| `Record::ParticleFillView` (`Requests.hh:72-76`) | grep: declared, never used | Delete |

### 5.2 Repo clutter (outside utils/, quick wins)
- **Instruments `.trace` bundles are tracked in git** (hundreds of files,
  `Launch__Lambda_Reconstruction.exe_*.trace/...`) — deleted from the working
  tree but still in the index (the `D` wall in `git status`). Also tracked:
  `.DS_Store`. `git rm -r --cached` them; `.gitignore` already covers both.
- `.gitignore` gaps: `*.exe.d` (new dependency files are not matched by
  `*.exe`), `logs/`, `checkpoints/`.
- Top-level scratch dirs (`_vs/`, `dump/`, `aux/`, `bots/`, `results/`,
  `archive/`) have no README; a one-liner in `docs/MAP.md` saying which are
  disposable would save future-you from archaeology. `examples` and `legacy/`
  appear in `.gitignore` but don't exist — stale entries.
- `Time_Collect.cc` reads `output/Lambda/timer.log` — **nothing writes that path**
  (verified: all `TimerRegistry::dump` calls go to stdout). Orphaned; archive
  it or repoint it at the stdout CSV.

### 5.3 State reduction
- **`Config::Register` is self-declared transitional** (`Config/Types.hh:113-117`:
  "Full Register deletion is the W9 endpoint") — 19 fields straddling Config
  and Record, mirrored into `Record::Paths`/`HistConfig` by `configureWriter`,
  and `fillDerived` callers already pass empty dummies (§2.2). Finishing W9
  (move path-building into `Record::Paths` factory, limits into `HistConfig`)
  deletes the largest redundant state block in the codebase.
- **`Record::Writer`**: ~35 members. Cheap consolidations: the 6 per-kind
  atomic counters → `std::array<std::atomic<size_t>, 6>` indexed by variant
  index; the 4 injected `std::function` hooks → one `WriterHooks` struct
  (also collapses `bind()`'s 5 params to 2); `produced_/consumed_/maxBacklog_`
  → a small `QueueStats` struct.
- **`Monitor::AsyncLogger`**: 6 emission bools + interval scattered across
  two configure calls (`configureWatchEmission` + `configureArtifactEmission`)
  → one `EmissionPolicy` struct, one setter.
- **`ProbeParallel`**: `streamType_` + `requestedMode` + `activeMode_` (§3.6);
  `workersFinished_/produced_/consumed_` could fold into a `QueueStats`
  mirroring the Writer's.

### 5.4 Parameter reduction
- `Writer::declareParticleHist2D` takes **11 parameters**, `declareHist2D` 10
  (`Writer.hh:102-113,147-158`) — introduce `AxisSpec{bins, low, high}` (and
  reuse it in `validateHistogramShape`): signatures drop to 5-6 args and the
  x/y groups become impossible to misorder.
- `Meta::fillDerived(…, const Config::Register&)` → `const std::string&
  beamEnergy` (§2.2).
- `Monitor::buildLogText(writer, logging, programLog, printStats,
  listChangedSettings, pacing)` — 6 params, 3 of them callbacks that came
  from `Writer::bind` — would collapse with the `WriterHooks` struct above.
- `detail::buildStreams(…6 params…)` (`Probe/Threading.hh:30`) — pass
  the partition context as one struct; it's already constructed from one.

## 6. Priority table

Score = (Impact + Risk) × (6 − Effort), 1-5 each.

| # | Item | §  | I | R | E | Score |
|---|------|----|---|---|---|-------|
| 1 | In-process SHA-256, kill `popen` | 1.1 | 4 | 5 | 2 | 36 |
| 2 | Atomic checkpoint rename | 1.2 | 3 | 4 | 1 | 35 |
| 3 | Dead config keys `index_*` (lying API) | 5.1 | 3 | 3 | 1 | 30 |
| 4 | Steady-clock stall detection | 3.1 | 3 | 3 | 1 | 30 |
| 5 | Delete dead Kinematics/`configuration`/`ParticleFillView` | 5.1 | 3 | 2 | 1 | 25 |
| 6 | Untrack `.trace`/`.DS_Store`, fix `.gitignore` | 5.2 | 2 | 2 | 1 | 20 |
| 7 | SIGTERM/SIGINT handler → fatal path | 1.4 | 3 | 3 | 2 | 24 |
| 8 | `ScopeTimer` contention fix | 3.2 | 3 | 2 | 1 | 25 |
| 9 | WorkerThread early-abort flag | 3.3 | 2 | 3 | 1 | 25 |
| 10 | `writerException_` locked read | 1.3 | 1 | 3 | 1 | 20 |
| 11 | `AxisSpec` + `WriterHooks` + `EmissionPolicy` param/state cleanup | 5.3/5.4 | 3 | 1 | 2 | 16 |
| 12 | `CloneSet` template collapse (8 structs → 1) | 2.1 | 2 | 1 | 2 | 12 |
| 13 | ProbeIMT fate decision | 5.1 | 2 | 1 | 2 | 12 |
| 14 | Finish W9: delete `Config::Register` | 5.3 | 3 | 1 | 4 | 8 |
| 15 | Event layout interning / frame pool | 3.5 | 4 | 1 | 4 | 10 — defer to ML phase |
| 16 | Paint ordered kind registry + ratio mode | 3.7/4.3 | 2 | 1 | 3 | 9 — defer to analysis phase |

Suggested batches: **items 1-6** are a half-day correctness/hygiene pass with
no API changes; **7-10** a second half-day; **11-13** one API-touching cleanup
PR; **14-16** live with their respective future phases.

## 7. Implementation log (2026-06-12) — items 1-13 DONE

All scored items except the explicitly deferred ones (#14 Register/W9,
#15 Event interning, #16 Paint registry/ratio) were implemented and verified:
7/7 test suites green, 1k-event e2e produces a correct file, live SIGINT test
finalizes a partial output cleanly.

**Security & robustness (Batch A)**
- `Utility/Sha256.hh`: in-process FIPS 180-4 SHA-256 (verified against 4 test
  vectors incl. 1M-char streaming); `Meta::sha256File` no longer shells out —
  the popen injection vector is gone.
- Checkpoints write to `.tmp` + atomic rename (`Recording.hh`).
- Stall detection runs on `steady_clock` via a new `RunSnapshot.lastUpdateMono`
  (wall-clock `lastUpdateTime` kept for display only).
- `writerException_` reads in the watchdog now go through a locked
  `peekWriterException()`.
- `runWorkerThread` checks `stopRequested_` per iteration and failing
  partitions call `requestStop()` — both Probe modes abort early now.
- `ScopeTimer` records into lock-free `thread_local` buckets keyed by literal
  address; merge to the string-keyed global registry happens at thread exit /
  dump. The global-mutex-per-scope hot-path contention is gone.
- `Utility/Signals.hh` + all three drivers: SIGINT/SIGTERM → graceful stop
  (Probe driver unwinds via sentinel exception through the worker error path;
  Pythia drivers use cooperative skip since PythiaParallel invokes callbacks
  on its own threads and has no abort API — first signal finishes + finalizes
  partial output, second signal kills). Verified live: `kill -INT` mid-run →
  exit 0, complete ROOT file with About/ intact.
- Smaller: `sr_padding` clamped ≤ 10; `stod` failure warns; `kFatalGracePeriod`
  is `inline constexpr`; no-op Heartbeat WatchRequests no longer emitted;
  `Illustrator` lazily load/resolves; `applyTreeRowRequest` validates rows
  with zero allocations; `scaleAndWrite` warns on failed Clone; Mixed-mode
  "events drive" semantics documented at both loops + `ProbeConfig`.

**Dead code (Batch C)**
- Deleted: Kinematics Column-batch family + `Physics::Column` alias
  (`invariantMass`/`deltaPhi`/`deltaR` kept), `Config::configuration()`,
  `ParticleFillView`, the `index_*` keys/fields (now *rejected* with a clear
  error if present in configs — fixture/configs/templates scrubbed; the
  intended clustering-algorithm design is preserved as a comment on
  `EventParticleSpec`). `Time_Collect.cc` archived.
- **ProbeIMT was promoted, not deleted** (user decision, supported by the
  recovered `ROOTMT.md`: the spike measured 5.3× at 8 threads — IMT escapes
  the ROOT global lock that caps ProbeParallel at ~150% CPU; adoption had
  simply stalled). The whole-file buffering disqualifier is fixed with
  windowed reads (`setChunkEvents`, default 200k, 0 = legacy whole-file);
  identity and trade-offs documented in `ParallelIMT.hh`; new chunked-window
  test passes alongside the existing equivalence tests.

**API cleanup (Batch D)**
- `Record::AxisSpec{bins, low, high}`: `declareParticleHist2D` 11 → 7 params,
  all declare* converted; `modules/Lambda/Declare.hh` + tests updated.
- `Record::WriterHooks`: `bind(logger, hooks)` replaces 5 positional
  `std::function` params; 5 call sites updated.
- `Monitor::EmissionPolicy` + `configureEmission()` replace the
  configureWatchEmission/configureArtifactEmission pair, and `save_heartbeat`
  now genuinely gates the periodic runstat write (it previously gated
  requests the watchdog discarded).
- `CloneSet<TObj>`/`GraphCloneSet<TObj>` collapse the 8 master+clones structs;
  `Cloning.hh` is 8 impls → 4 (`cloneHistImpl`/`cloneGraphImpl`/
  `mergeHistImpl`/`mergeGraphImpl`); members renamed `.hist/.graph/.profile`
  → `.master`.
- `Meta::fillDerived` takes `beamEnergy` string instead of a whole
  `Config::Register` (the finish-time dummy-Register hack is gone).

**Hygiene (Batch B)**
- Untracked the two Instruments `.trace` bundles and all `.DS_Store` files;
  `.gitignore` rewritten (adds `*.exe.d`, `logs/`, `checkpoints/`; stale
  entries dropped); `docs/MAP.md` updated with scratch-dir annotations and
  the archived `Time_Collect.cc`.

## 8. What this round deliberately did not re-litigate
Round 1 (docs/UtilsAudit.md) already covers: include-cycle hygiene, naming
taxonomy, TOML/path/ROOT-access helpers, Probe double-scan, the
Ingest/Export blueprint, and the test/docs debt — all tracked there with
their own phases. This document is additive, not a replacement.
