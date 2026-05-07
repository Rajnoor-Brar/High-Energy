# Review — open backlog

The post-W7 streamline (Batch01–07) closed the bulk of the previous backlog.
What remains is one investigation, one deferred unification, plus a handful
of orthogonal quality items previously listed as "deferred observations" in
ROADMAP §B.5.

> **Build status (post-Batch07).** All five targets — `_Lambda_Data.exe`,
> `_Lambda_Parallel.exe`, `_Lambda_Reconstruction.exe`, `_Lambda_Test.exe`,
> `tests/test_rootAnalysis_smoke.exe` — build clean. `make test` passes
> T1–T5 and S1–S5.

Companion docs: [MAP.md](MAP.md) (file map),
[ROADMAP.md](ROADMAP.md) (post-batch status + deferred observations),
[Architecture.md](Architecture.md) (strategic plan-of-plans — items
W1–W10 marked complete), [DataFlow.md](DataFlow.md) (TOML key
inventory), [plans/COMPLETED.md](plans/COMPLETED.md) (per-batch
summary).

---

## Items resolved in Batch01–07

For the historical record (the long postmortem bodies are gone; consult
git history if a specific decision needs re-litigating):

| Old #  | Title                                                          | Closed in |
| -----: | -------------------------------------------------------------- | --------- |
|     1  | Dead `Record::TreeRecord` plumbing (wire-up via TOML)          | Batch07   |
|     2  | `Probe::ScalarSpec` plumbing dead                              | Batch03   |
|     3  | `kTreeEnabledSets` empty array                                 | Batch07   |
|     4  | `bool userEvents` sentinel for `event_count`                   | Batch04   |
|     5  | Reproducibility metadata in `Meta::Record`                     | Batch07   |
|     6  | Doc-comment headers on every umbrella                          | Batch07   |
|     7  | Cross-link the docs                                            | Batch07   |
|     8  | Pythia `cmnd` path from TOML                                   | Batch07   |
|     9  | Limits load optional + struct-init defaults (defaults file part done; struct-init still pending — see §3 below) | Batch07 (partial) |
|    10  | `declareObjects` / `declareDataObjects` narrow handle          | Batch07 (via `Lambda::configure` consolidation) |
|    11  | External `histMutex` lives in driver, not in `Writer`          | Batch02   |
| P1, W2, W5, W6, W7, W8, W9, W10 | (full ROADMAP execution slice)                | Batch01–06 |

Earlier closures (Log/Root alias retirement, Schema.hh → BranchControl.hh
rename, ThetaTolerance camelCase rename, Lambda::ParamAid deletion,
Pipeline B → A schema migration, Parameters.hh 3-way split,
`_Lambda_Data.exe` build break, `Probe::detail` → `BranchControl` rename,
`Config::Register` → `HistConfig`/`Paths` partial split,
`Lambda::propertyName` overload removal, `dataLogString` move into
`modules/Lambda.hh`, `using Lorentz` aliases unified, `namespace
Extract`/`Meta` nesting under `Record`) live only in git history.

---

## 1. `AnalysisContext` and `GenerationContext` are duplicative

`modules/Lambda/Context.hh` defines both; both hold `Watch& logging`,
`AsyncLogger& asyncLogger`, `Record::Writer& writer`. The structural
difference is `RootArray& histograms` vs `DataObjects& data` +
`std::mutex& treeMutex`.

Recommendation in the original Batch07 plan was **keep distinct**: the
two communicate intent (analysis vs data-generation), and unification
behind a templated `Context<HistOrData>` would obscure more than it
saves. Re-evaluate only if a third context appears.

---

## 2. Limits — struct-init defaults fallback (REVIEW #9 partial)

`utils/Config/Defaults.hh::limitExtractor` now skips the global defaults
file silently when absent. Remaining: when `configs/defaults/Limits.toml`
is missing AND the project limits TOML doesn't cover every property,
seed `root.particleLimits` / `root.eventLimits` from struct-init defaults
defined alongside `Physics::ParticleTraits` (extend the trait with a
`defaultBounds` field). Today, `extractPhysics` will throw on a missing
property limit instead.

Low priority; the project limits TOML provides full coverage in tree.

---

## 3. Investigation A — Sub-namespacing under `Probe`

`utils/Probe/BranchControl.hh` already uses `Probe::BranchControl`.
Investigate whether other Probe internals would benefit from explicit
sub-namespacing — e.g. `Probe::TreeControl`, `Probe::LeafControl`,
`Probe::EventControl`. Outcome should be a design note before any code
change.

---

## Deferred observations (orthogonal — open but off the active path)

These are real but architecturally orthogonal; previously listed under
ROADMAP §B.5 "deferred observations." They survive REVIEW because the
underlying issue is real and worth a future fix.

- **Silent `hist_limits` resolution.**
  [utils/Config/LimitAid.hh:7–15](../utils/Config/LimitAid.hh) silently
  expands a bare name into `configs/<name>.toml`. If the user typoed or
  moved the file, the only signal is a downstream `Histogram limits file
  does not exist` exception in
  [Lambda/Loaders.hh](../modules/Lambda/Loaders.hh). Print the resolved
  path on first read.
- **`AsyncLogger::runLoop` shuttles five `std::optional<…>` across one
  lock boundary** ([utils/Monitor/Logger.hh:212–280](../utils/Monitor/Logger.hh)).
  Works, hard to extend. A small `std::queue<Action>` drained outside
  the lock would make adding a new heartbeat tick a one-line change
  instead of editing six places.
- **`Probe::runParallel` swallows then rethrows the *first* worker
  exception** ([utils/Probe/Parallel.hh](../utils/Probe/Parallel.hh)).
  Aggregate or chain so a second fault's diagnostic isn't lost.
- **`tests/run_all.sh:30` `break`s on first failure.** A regression in
  `test_reconstructCandidates` masks any later regression in
  `test_rootAnalysis_smoke`. Drop the `break`; report total pass/fail
  at the end.
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
  document why three passes is the right choice.
- **`Histogram::write` and `writeToDir` are near-twins**
  ([utils/Record/Histogram.hh](../utils/Record/Histogram.hh)) —
  identical except for `dir->cd()` placement. Parameterize or drop one.

---

## Unconcerns (deferred indefinitely)

- **Per-event `WorkerStats` RAII helper.** Three handlers
  (`pythiaAnalysis`, `rootAnalysis`, `dataGenerator`) share six-step
  boilerplate. Readable as-is; abstraction would obscure.
- **Per-event `EventScope` RAII** (Gemini ROADMAP 8). Same rationale.
- **TeX / human-readable axis labels.** Cosmetic; bare property names
  on plots are tolerable.
- **`Lambda::Parameters::thetaTolerance` is write-only** after the
  `cosThetaTolerance = std::cos(thetaTolerance)` derivation. Kept for
  log readability.
- **README.md.** `bots/CLAUDE.md` covers the build/run path for human
  and bot consumers.
- **Reproducibility metadata extras beyond §5** — git SHA / dirty bit /
  file shas are done; broader environment capture (full toolchain
  pinning) is out of scope.
- **Snake_case → camelCase sweep on `Watch` / TOML keys.** Mixed case
  is the current state; not a priority.

---

## Out of scope

- C++20 / 23 migration (concepts, modules, `std::span`).
- Replacing `toml++` with another TOML library.
- Switching ROOT TFile → TBufferFile / RNTuple.
- Splitting the long `*Limits.toml` files in `configs/defaults/` and
  `configs/`.
- Async I/O on writes.
- Pre-compiled headers (PCH).
