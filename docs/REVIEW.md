# Review — open backlog

Action backlog of additions, removals, and restructures. Everything in this
file is **open**. Resolved items are not listed; for completed work see git
history. Companion to [MAP.md](MAP.md). Active phase plan: [ROADMAP.md](ROADMAP.md).

Numbering restarts from 1; previous numbers no longer apply. Each item carries
the exact `file:line` of the issue in the current tree.

---

## 1. Complete the `Watch`/`Register` rename, retire `Log`/`Root` aliases

`utils/Config/Types.hh:137-138`

```cpp
using Log  = Watch;
using Root = Register;
```

The structs were renamed (`Watch`, `Register`). The aliases stayed in place to
let consumers migrate gradually; nothing has migrated. Every translation unit
that touches per-run state still types `Config::Log` / `Config::Root`:

| File:line                                                        | Symbol used                   |
| ---------------------------------------------------------------- | ----------------------------- |
| `_Lambda_Parallel.cc:20-22`                                      | `Config::Root`, `Config::Log` |
| `_Lambda_Reconstruction.cc:20-21`                                | both                          |
| `_Lambda_Data.cc:21-23`                                          | both                          |
| `_Lambda_Test.cc:19-20`                                          | both                          |
| `_Monitor_FatalStall_Harness.cc:12, 20`                          | both                          |
| `tests/test_rootAnalysis_smoke.cc:56-57`                         | both                          |
| `utils/Monitor/Render.hh:59, 60, 100-101, 111-112, 144-145, 153` | both (in 6 free functions)    |
| `utils/Monitor/Snapshot.hh:41`                                   | `Config::Log`                 |
| `utils/Monitor/Logger.hh:27, 57, 103`                            | both                          |
| `utils/Record/Finalizer.hh:44, 81, 108-109`                      | both                          |
| `utils/Record/Meta.hh:115-116`                                   | both                          |
| `modules/Lambda.hh:33`                                           | `Config::Root`                |
| `modules/Lambda/Context.hh:6, 25, 33`                            | `Config::Log`                 |
| `modules/Lambda/Parameters.hh:55, 68, 82, 89, 159, 195, 266`     | `Config::Root`                |

**Why this matters now.** Phase 2's `Watch::recordEvent` and `Watch::freeze`
already use the canonical name; consumers calling `logging.recordEvent(...)`
on a `Config::Log&` parameter quietly resolve through the alias. The alias is
no longer load-bearing — it's pure churn. Until it's removed, every new file
arrives confused about which name to use, and grep-by-name returns half
results.

**Fix direction.** Either commit to `Watch`/`Register` everywhere and delete
the aliases, **or** finish the audit-recommended rename to more informative
names (`RunStats` / `OutputContext`) and then delete both pairs of aliases.
**Ordering caveat:** the audit recommended bundling this with the
`Register`-split (item 12 below). If both happen, `Register → OutputContext`
is a stepping stone before the split lands; pure name churn that gets
reverted on the next pass. Pick the destination first, then move once.

---

## 2. `Lambda::propertyName` overloads are pure passthroughs

`modules/Lambda/TypeAid.hh:13-15`

```cpp
inline string propertyName(Physics::ParticleProperty p) { return Physics::particlePropertyName(p); }
inline string propertyName(Physics::EventProperty p)    { return Physics::eventPropertyName(p); }
```

Two-lookup wrappers with no added value. Drop them; have
`Lambda/Parameters.hh` and `Lambda/TypeAid.hh::propertyAlias` call
`Physics::*PropertyName` directly. Five callers under `modules/Lambda/`.

---

## 3. `Lambda::levelName` duplicates `Config::levelToString`

`modules/Lambda/TypeAid.hh:27-36`

The body is a literal copy of `Config::levelToString`
(`utils/Config/TypeAid.hh:10-19`), modulo the throw-vs-return-`"Unknown"`
fallback. Drop the `Lambda::` version; replace each call (currently only
inside `Lambda/Parameters.hh::levelBounds` error messages) with
`Config::levelToString`.

---

## 4. `dataLogString` is in the wrong file

`modules/Lambda/Reconstruction.hh:6-12`

```cpp
inline std::string dataLogString() {
    std::ostringstream stream;
    stream << "Proton PDG ID                 : 2212\n";
    ...
}
```

Pure logging blurb, no reconstruction logic. Only consumer is
`_Lambda_Data.cc:58` (which is itself slated for migration — see
ROADMAP item 2). Move next to `logString` in `modules/Lambda.hh`, or to a new
`modules/Lambda/Logging.hh` if Lambda gains more such blurbs.

---

## 5. `using Lorentz` aliases scattered across modules

The same alias is defined five times:
- `utils/Probe/Types.hh:15`        — `using Lorentz = Physics::Lorentz;`
- `utils/Record/Types.hh:19`       — `using Lorentz = Physics::Lorentz;`
- `modules/Lambda/Types.hh:18`     — `using Lorentz = Record::Lorentz;`
- `utils/Record/Extract.hh:23`     — `using Lorentz = Physics::Lorentz;` (inside `namespace Extract`)
- `modules/Lambda/Reconstruction.hh:22-26` (uses `Lorentz` resolved through `Lambda::Types.hh`)

Pick one of:
- **Option A (verbose, explicit):** delete every alias; type `Physics::Lorentz`
  at every use site (~60 occurrences). Catches the dependency at the call
  site.
- **Option B (single re-export):** keep the alias only in `Physics/Types.hh`
  (it's already there as the canonical) and let consumers `using
  Physics::Lorentz` once at the top of each TU that needs it.

Currently it's neither — the alias is redefined in five places, and
`Lambda::Lorentz` indirects through `Record::Lorentz` instead of going to the
source.

---

## 6. `Probe::ScalarSpec` plumbing is dead

- Declaration: `utils/Probe/Types.hh:40-45` (struct), `:77` (`Event::scalars` map)
- Threaded through: `utils/Probe/Event.hh:19` (`EventStream` ctor),
  `utils/Probe/Parallel.hh:19, 56, 101, 116, 119, 132` (six occurrences in
  `runParallel` and `readAllParallel` signatures)
- Consumers: **none** in `modules/Lambda/` or any driver.

Either:
- **(a) Wire it up** to a real consumer. Natural fit: per-event weights in
  `_Lambda_Reconstruction.cc:75-81`, where `Probe::Event` already has
  `ev.scalar<T>(...)` available.
- **(b) Drop it.** Remove the parameter, `Event::scalars`, and the convenience
  overload. The single overload of `runParallel` becomes 30 lines simpler.

If kept, document the intended use in `utils/Probe/Types.hh` near the
`ScalarSpec` declaration so the next reader knows it's an extension point and
not orphan code.

---

## 7. `_Monitor_FatalStall_Harness.cc` is an orphan

`_Monitor_FatalStall_Harness.cc:1-102`

Fixed : Deleted the

---

## 8. Rename `Probe/Schema.hh` → `Probe/Detail.hh`

`utils/Probe/Schema.hh:1-215`

The entire file is `namespace Probe::detail { … }`; nothing public lives in
it. The filename should reflect that. Three callers:
`utils/Probe/FlatReader.hh:8`, `utils/Probe/VecReader.hh:9`,
`utils/Probe/Event.hh:9` — plus the umbrella `utils/Probe.hh:4`.

---

## 9. Move `namespace Extract` and `namespace Meta` under `namespace Record`

- `utils/Record/Extract.hh:21` — `namespace Extract { … }` (top-level)
- `utils/Record/Meta.hh:21`    — `namespace Meta { … }` (top-level)

Inconsistent with everything else under `Record/` (which is in
`namespace Record`). Two options:

- **Recommended:** nest as `Record::Extract` and `Record::Meta`. Updates
  `_Lambda_Reconstruction.cc:84` (`Meta::Record` → `Record::Meta::Record`)
  and any downstream consumer.
- Alternative: split out into top-level umbrellas (`utils/Extract.hh`,
  `utils/Meta.hh`) — but those names were already retired as compat shims
  in an earlier pass per `docs/refactor-direction.md` §4. Re-introducing
  them would re-create the conflict that section just fixed.

---

## 10. Split `Lambda/Parameters.hh` (310 lines, three concerns)

`modules/Lambda/Parameters.hh:1-310` (the largest file in the project)

Three concerns mixed in one header:

- **Bounds resolution helpers** (~60 lines): `explicitBounds`, `levelBounds`
  (×2), `boundsFromNode<P>`, `resolveBounds<P>`, `Recorded_ParticleProperties`,
  `kTreeEnabledSets`.
- **TOML loaders** (~75 lines): `loadInputSection`, `loadCandidatesSection`,
  `extractPhysics` (which is by far the longest function in the file at ~45
  lines).
- **ROOT object declaration** (~120 lines): `inputSchema`, `declareDataObjects`,
  `shouldWriteTree`, `declareObjects`.

Suggested split:
- `modules/Lambda/Parameters.hh` — `Parameters` struct (already in Types.hh,
  this just keeps the bounds-resolution helpers + `Recorded_ParticleProperties`).
- `modules/Lambda/Loaders.hh` — `loadInputSection`, `loadCandidatesSection`,
  `extractPhysics`.
- `modules/Lambda/Declare.hh` — `declareDataObjects`, `declareObjects`,
  `inputSchema`, `shouldWriteTree`.

**Why this matters now:** every later refactor that touches Register's
internals (item 12) has to grep this file first. Splitting first reduces the
search radius. **Hard prerequisite for ROADMAP Phase 4 item 1.**

---

## 11. Per-event `WorkerStats` RAII helper (partial — finish it)

`modules/Lambda.hh:36-54, 70-86, 94-122` — three handlers (`pythiaAnalysis`,
`rootAnalysis`, `dataGenerator`) repeat the same six-step boilerplate:

1. `++ctx.logging.iEvent`
2. `publishThreadStats(workerIndex, ThreadPhase::Analysis, eventIndex, NoCallbackCompleted)`
3. user work (the only differing step)
4. `ctx.logging.recordEvent(now)` *(was `static std::mutex stateMutex` block;
   extracted to `Watch::recordEvent` in Phase 2)*
5. `publish(logging, RunPhase::Analysis, DontWriteRunStat)`
6. `publishThreadStats(workerIndex, ThreadPhase::Simulation, eventIndex, CallbackCompleted)`

Step 4 is done. Steps 1, 2, 5, 6 are still copy-pasted. A scoped RAII helper
(`Lambda::EventScope scope{ctx, workerIndex};`) constructed before user work
and destroyed after would collapse the three handlers' bookkeeping into one
declaration. Scope reduced now that step 4 is already extracted.

---

## 12. Split `Register` (Config::Root)

`utils/Config/Types.hh:112-131`

`Register` mixes four concerns:

| Field group                                                                                                                                                                             | Concern              | Used by                                                |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- | ------------------------------------------------------ |
| `outFile`, `binCount`, `histScale`                                                                                                                                                      | output ROOT artifact | `Histogram::write`, `FinalizerController`              |
| `rootDirectory`, `logDirectory`, `checkpointDirectory`, `outName`, `logName`, `runStatName`, `threadStatDirectory`, `checkpointOutName`, `checkpointLogName`, `fileTitle`, `beamEnergy` | path templates       | `AsyncLogger.start`, `Monitor::outputLog`, `_Lambda_*` |
| `histLimitsFile`, `particleLimits`, `eventLimits`                                                                                                                                       | resolved limits      | `Lambda::extractPhysics`, `Lambda::declareObjects`     |
| `inputPath`                                                                                                                                                                             | input ROOT artifact  | `_Lambda_Reconstruction.cc:25`                         |

**Why this matters now (and didn't before).** Phase 2 added `inputPath`,
which is the fourth concern. Section 7's `readInputSection` populates it, but
nothing else looks at it — proof that the bundling is incidental. After the
Phase 3 §5 callback redesign, `Monitor::AsyncLogger::start` still takes the
whole `Register&` to read three fields (`runStatName`, `threadStatDirectory`,
`fileTitle`); a `OutputPaths` struct would let it depend on what it actually
uses.

Suggested split (names from architecture audit):
- `OutputFile` — `outFile`, `histScale`, `binCount`, `beamEnergy`
- `OutputPaths` — every `*Name` / `*Directory` / `fileTitle` field
- `LimitsConfig` — `histLimitsFile`, `particleLimits`, `eventLimits`
- `inputPath` moves to `Events` (or a new `InputConfig` struct).

**Hard prerequisite:** item 10 (Parameters split) — `Lambda/Parameters.hh`
takes `Config::Root&` in seven places, all of which would need to be
re-pointed at the new structs. Splitting that file first is the safer order.

---

## 13. Add a `Driver` / `App` skeleton

The four `_Lambda_*` drivers share ~80% of their lifecycle (see MAP.md
§Drivers). A `Driver::run<DriverFn>` template (in a new `utils/Driver.hh` or
`App.hh`) would shrink each driver to just the unique payload — the
`pythia.run(...)` call, the `runParallel(...)` call, or the test-mode loop.

**Scope changed in Phase 2.** The `AnalysisContext`/`GenerationContext` work
already removed the per-handler argument bloat that motivated this item. The
remaining duplication is the lifecycle scaffold itself, not the call payload.
Smaller win than originally estimated, but still worth doing once item 12
lands (the new structs are ergonomic to pass to such a skeleton).

---

## 14. Fold `Monitor/Format.hh` into `Monitor/Snapshot.hh`

`utils/Monitor/Format.hh:1-23`

The file contains exactly one function (`updatedETA`). `Snapshot.hh` is its
only consumer (`utils/Monitor/Snapshot.hh:11, 47`). The split made sense when
Format.hh also held `numberFormat`/`timeString`/`durationString` — those moved
to `Utility/`, leaving Format underweight. Merge.

---

## 15. Rename `Lambda::Parameters::ThetaTolerance` → `thetaTolerance`

`modules/Lambda/Types.hh:49` (declaration), `modules/Lambda/Parameters.hh:270-271`
(read from TOML), `modules/Lambda/Reconstruction.hh` (currently no consumer
because `cosThetaTolerance` is what's used downstream — the field is
write-only and feeds `cosThetaTolerance = std::cos(ThetaTolerance)` once).

Other fields in the same struct are camelCase: `massTolerance`,
`cosThetaTolerance`, `reservedProtons`. The capitalization on `ThetaTolerance`
is the odd one out. Audit also confirms the field is **write-only after
extractPhysics** — consider whether the field belongs at all, vs. just storing
the cosine.

---

## 16. Add a "specified vs defaulted" sentinel for `event_count`

`utils/Config/Reader.hh:41-53` (`readEventsSection`),
`_Lambda_Reconstruction.cc:55-62` (the IIFE that re-parses TOML to disambiguate)

`readEventsSection` writes `1000` as the default for `[events].event_count`,
making it impossible for downstream code to tell "user set 1000" apart from
"user said nothing." `_Lambda_Reconstruction.cc` works around this by
re-parsing the TOML to check whether the key is actually present, which is
why one `toml::parse_file` call survives in the driver after Phase 2's
single-read consolidation.

Fix: add `std::optional<std::size_t> eventCountExplicit` (or a
`bool eventCountSet`) to either `Config::Events` or `Config::Register`.
Populate it in `readEventsSection`. The driver's IIFE collapses to a single
check and the second `toml::parse_file` call goes away.

---

## 17. Reproducibility metadata in `Meta::Record`

`utils/Record/Meta.hh:73-81` (`struct Record` — currently has no integrity
fields beyond `creation_timestamp` and `processed_by`)

Capture into `About/processing/` and `About/integrity/`:
- `git_sha` (from `git rev-parse HEAD` at build time, baked in via `-DGIT_SHA=...`)
- `git_dirty` (whether the working tree was clean at build time)
- `host_uname` (already partially via `osArch()` at `Meta.hh:100` — extend with
  kernel release and host)
- `cmnd_file_sha` (sha of the loaded `.cmnd` file —
  `_Lambda_Parallel.cc:19`, `_Lambda_Test.cc:18`, `_Lambda_Data.cc:20`)
- `limits_file_sha` (sha of `root.histLimitsFile`,
  resolved by `Config/LimitAid.hh:7`)

Lets future analysts answer "which exact code produced this ROOT file?"
without spelunking the working tree.

---

## 18. TeX / human-readable axis labels

`modules/Lambda/Parameters.hh:235-245` (histogram declaration loop)

Histograms get bare snake_case names (`Mass_Invariant`,
`Momentum_Transverse`) for both branch name and axis title. Branches are fine
that way; plot titles are ugly.

Add `Physics::particlePropertyTeX(ParticleProperty)` returning `"M_{inv}
[GeV]"`, `"p_{T} [GeV]"`, etc. Extend `ParticleTraits`
(`utils/Physics/Types.hh:51-55`) with a `tex` field; feed it into
`SetTitle("...; <tex>; ...")` inside `declareObjects`.

---

## 19. README.md is missing

There is no top-level README. `bots/CLAUDE.md` covers the same ground for the
agent path, but a human-facing entry point is missing. Add a brief page:

- What this project is (one paragraph: Lambda baryon reconstruction in C++17 + ROOT + Pythia8).
- Build prerequisites (ROOT, Pythia8, toml++, compiler version).
- How to build (`make _Lambda_Parallel.exe`, etc.) and how to run
  (`./_Lambda_Parallel.exe configs/Lambda_Generation.toml`).
- The project's testing mandate (`event_count = 1000`, `serial = 99`,
  outputs redirected to `outputs/test/`) — see `bots/BOT.md`.
- Pointers to [docs/MAP.md](MAP.md), [REVIEW.md], [ROADMAP.md](ROADMAP.md).

---

## 20. `kHistogramSetCount` / `kTreeEnabledSets` / `shouldWriteTree` — wire up or delete

- `modules/Lambda/Types.hh:16` — `constexpr std::size_t kHistogramSetCount = 3;`
- `modules/Lambda/Parameters.hh:36-38` — `constexpr std::array<HistogramSet, 0> kTreeEnabledSets = {};` (empty)
- `modules/Lambda/Parameters.hh:178-191` — `shouldWriteTree(set, parameters)` returns the AND of
  "set is in the empty `kTreeEnabledSets`" and "any candidate has `writeTree=true`",
  which always evaluates to false. The TreeRecord branch in `RootObjects` is
  declared (`Record/Types.hh:32-36`) but never populated.

Either:
- **Remove** the unused machinery: `kTreeEnabledSets`, `shouldWriteTree`, and
  the `trees` field on `RootObjects`. Saves a `unique_ptr` allocation on
  every histogram set.
- **Or wire it up:** add `[record].write_trees = ["Selected"]` to the TOML
  schema, populate `kTreeEnabledSets` from it (via a `std::vector<HistogramSet>`
  rather than `std::array` so it's runtime-sized), and verify the trees
  actually appear in the output ROOT file.

---

## 21. Doc-comment header on every umbrella

Each `X.hh` umbrella file currently has varying inline docs (some have none —
`utils/Monitor.hh`, `utils/Record.hh`, `utils/Paint.hh`, `utils/Physics.hh`,
`utils/Probe.hh`, `utils/Utility.hh` are all bare include lists). Standardize:
one block at the top describing the module's role + listing its submodules
with one-line purposes. Same pattern as MAP.md but inline.

---

## 22. Cross-link the docs

- [MAP.md] now points here and at ROADMAP.md.
- This file points back to MAP.md and ROADMAP.md.
- Once README.md exists (item 19), link from there to all three.
- `bots/CLAUDE.md` already links to MAP.md and REVIEW.md but should add
  ROADMAP.md once it lands.

---

## Out of scope

- C++20 / 23 migration (concepts, modules, `std::span`).
- Replacing `toml++` with another TOML library.
- Switching ROOT TFile → TBufferFile / RNTuple.
- Splitting the long `*Limits.toml` files in `configs/defaults/` and `configs/`.
- Async I/O on writes.
