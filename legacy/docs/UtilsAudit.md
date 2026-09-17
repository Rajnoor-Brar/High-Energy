# Tech-Debt Audit: `utils/` — High-Energy

**Date:** 2026-06-12 · **Scope:** all 58 headers (~9,800 lines) under `utils/`
**Toolchain:** C++17, header-only, per-file compilation via Makefile (`-I./utils`), deps: ROOT, Pythia8, toml++

## Context

This audit was requested ahead of a future project phase: HEP workflows with ML and visualization on real data (CERN/LHC), preferring C++ with likely Python interop later. The goal is a `utils/` layer that is human-navigable, maintainable, and cohesive. Findings below were produced by full reads of every file; every load-bearing claim was re-verified against source (several initial findings were *disproven* and are listed in §7 so you don't chase ghosts).

## 1. Inventory & how it hangs together

| Namespace | Files | ~Lines | Role |
|-----------|-------|-------|------|
| Record | 13 | 2,640 | ROOT TTree/hist writing, parallel clone-merge |
| Probe | 11 | 2,690 | Reading recorded data, parallel streaming |
| Paint | 9 | 1,610 | Plot rendering pipeline (Book→Resolve→Render→Save) |
| Monitor | 10 | 1,180 | Async logger, progress, stall detection, timers |
| Config | 7 | 810 | TOML parsing/merging, limits, thread resolution |
| Physics | 4 | 280 | Property enums + trait tables, kinematics |
| Utility | 4 | 250 | Time/number formatting, ROOT type aliases |

**Runtime flow:** TOML → `Config::parseConfig` (recursive table merge, directory-of-files support) → `Config::configure*` populates `Watch`/`Register`/`Events` → constructs `Probe::ProbeParallel`, `Record::Writer`, `Monitor::AsyncLogger` → main loop streams events → fill requests → checkpoint/finalize → `Paint::Illustrator` renders from output files.

**Dependency rules** are declared in `Config.hh:4-15` and mostly honored. Include graph is acyclic except the deliberate Writer↔Logger lifecycle coupling. All files use `#pragma once` consistently. Internal helpers correctly live in `detail::` namespaces.

**Docs state:** `docs/Architecture.md` and `docs/UtilsDependencyMap.md` are current and match code. `Plan.md`, `REVIEW.md`, `Issues.md`, `PaintReview.md` are older process docs — treat as historical.

**Tests:** `test_config`, `test_paint`, `test_probe_parallel`, `test_record_writer`, `test_rootAnalysis_smoke`, `test_reconstructCandidates`. **No tests at all for Physics, Utility, Monitor.**

---

## 2. Verified failure points & gotchas

### 2.1 Undefined behavior: `Physics::traitsOf(ParticleProperty::EventIndex)` — HIGH
`Physics/Types.hh:91-96`. The enum has 13 values (`EventIndex` = index 12) but `kParticleTraits` has 12 entries; the `static_assert` (line 78) deliberately stops at `Azimuthal_Angle`. `traitsOf()` does `kParticleTraits[toIndex(p)]` with **no bounds check before the array access**, so `traitsOf(EventIndex)` is an out-of-bounds read on a `constexpr std::array` — UB, and the `trait.id != p` guard runs *after* the OOB read.
**Fix (30 min):** `if (toIndex(p) >= kParticleTraits.size()) throw std::logic_error(...)` before indexing, plus a comment on `EventIndex` saying it is branch-only and has no extractor.

### 2.2 Silent I/O failures — HIGH
- `Monitor/Report.hh:24-27` `writeTextFile()` never checks the `ofstream` state. Used by `outputLog`, **`writeEmergencyLog`** (the fatal-stall record!), `flushRunStat`, `writeThreadStats`. Disk-full or bad path = silently lost logs at exactly the moment you need them.
- `Paint/Save.hh` `canvas.Print()` return is unchecked; ROOT prints to stderr but the program reports success.
- `Record/Meta.hh:196-207` `mergeFromToml()` wraps everything in `catch (...) {}` — a TOML syntax error in the metadata section silently yields empty provenance. `mergeFromProbe()` (line 214-217) silently returns on unopenable file. Provenance/metadata quietly missing is the kind of thing you discover months later.
**Fix:** check stream state and throw/log; route Meta failures through a warning channel (Monitor exists for exactly this).

### 2.3 Unchecked ROOT returns — HIGH (pattern, ~10 sites)
- `Record/Meta.hh:323-327`: `mkdir("About")` fallback `GetDirectory("About")` can still be null → deref on next line.
- `Probe/Methods.hh:32` (FlatReader ctor): `file->Get(...)` result is `dynamic_cast` and used; null Get → null deref. Several reader ctors share this pattern. (Contrast: `Probe/BranchControl.hh::requireBranch` does this *right* — throw with file/tree context.)
- `Probe/Methods.hh:475`: `kinArrays_[0]->GetSize()` → `size_t` with no check that all 4 coordinate arrays agree in size; mismatch reads garbage kinematics rather than throwing.
**Fix:** one checked helper (see §5.1 `rootGet<T>`) replaces the whole class of bug.

### 2.4 Config accepts physically invalid values — MEDIUM
`Config/Reader.hh`:
- Line 144: `event_count` is read as `int64_t` then cast to `size_t` — a negative value wraps to ~1.8e19 events.
- Lines 171-172: `bin_count` / `hist_scaling` accepted with no `> 0` validation; 0 bins crashes ROOT far from the config that caused it.
- Lines 178-179, 290-291: queue capacities cast from unvalidated int64 → huge unsigned on negatives.
- `Config/Defaults.hh:69`: unknown limit keys silently skipped "for forward-compatibility" — a typo like `Masss_Invariant` silently leaves default limits. At minimum log the skipped key.
**Fix (≈1 hr):** small `requirePositive(value, key)` helper used at each read site.

### 2.5 Header hygiene: global-namespace pollution — MEDIUM
`Config/Reader.hh:18` declares `namespace fs = std::filesystem;` at **global scope**. Every TU that includes `Config.hh` gets a global `fs` alias — a collision time bomb and inconsistent with `Defaults.hh:16` which correctly scopes it inside `namespace Config`. One-line fix.

### 2.6 CWD-relative hardcoded paths — MEDIUM
- `Paint/Book.hh:16` `kDefaultStylePath = "configs/defaults/Paint.toml"`
- `Config/Defaults.hh:81` `"configs/defaults/Limits.toml"`
Both silently depend on the process being launched from the repo root. Running an exe from anywhere else silently skips the defaults file (Limits "Pass 1" is `if (fs::exists(...))` — no warning). See §5.2 for the proposed fix.

### 2.7 Smaller verified items — LOW
- `Monitor/Directive.hh:245` uses ROOT `Form()` (fixed internal buffer) to build paths; very long directories truncate. Use `std::string` concatenation/`std::format`-style instead.
- Paint `applyGlobalStyle()` (`Apply.hh:17-28`) mutates `gStyle` per result; the `BatchRestore` RAII guard wraps the whole plan but not per-result style state — results later in a plan inherit earlier results' style residue unless every key is explicitly set.
- `Physics/Types.hh:67` `Energy_Transverse` computes `√(pT²+m²)`, which (on-shell) is numerically identical to `Mass_Transverse` (`Mt()`, line 65). Either it's intentionally mT (then it's a duplicate) or you wanted `ET = E·sinθ = E·pT/p`. Document or fix — for real-data ML features this distinction matters.
- `Monitor` stall behavior: fatal threshold is hardcoded `programStallThreshold × 5`; the multiplier isn't configurable.
- Logger `publish()` before `initialise()` silently no-ops — no warning.
- Mixed unit styles in Monitor config: `print_interval` (events) vs `heartbeat_interval` (ms).
- `ROOT::EnableThreadSafety()` once-flags exist independently in `Record/Administration.hh` and `Probe/BranchControl.hh` — safe but redundant; should be one shared call site (§5.1).

---

## 3. Duplication

1. **Checked-lookup boilerplate (~20 sites):** `auto it = map.find(k); if (it == map.end()) throw ...` repeated across `Record/Recording.hh` (6×), `Record/Declaration.hh` (9×), `Probe/Methods.hh` (3+×). One `getOrThrow(map, key, context)` helper kills all of it.
2. **TFile-open / tree-get / validate ctor preamble:** near-identical in `EventParticleReaderArray`, `EventNodeReaderArray`, `FeedParticleReader` ctors (`Probe/Methods.hh:435, 519, 697`) and again in `prepareEntryBounds` (`Probe/Administration.hh:142-169`).
3. **CoordSpec visitors:** the same `std::visit` over coordinate-spec variants appears 4× in `Probe/Methods.hh` (lines ~87, ~93, ~721, ~830). Consolidate into named functions next to the spec types in `BranchControl.hh`.
4. **Input file double-scan:** `FlatReader` scans entry bounds in its ctor, and `ProbeParallel::prepareEntryBounds()` rescans the same tree with `GetEntry()` over every row. For large real-data files this is a real cost (full sequential pass per spec). Cache bounds, or compute once and share.
5. **TOML table merge implemented twice:** `Config::detail::mergeTables` (`Reader.hh:29`) and `Paint::detail::mergeTomlTables` (`Book.hh:20`) are character-for-character the same algorithm; `parseBookConfig` (`Book.hh:41`) re-implements `Config::parseConfig`'s directory-merge logic. Paint avoids depending on Config — fine — but then the shared helper belongs in a `Utility/Toml.hh`.
6. **Paint `mergeSubsectionUse` call blocks** duplicated at `Resolve.hh:149-153` and `170-174`; loop over a static array of (useKey, subtableKey) pairs instead.
7. **Overlay stats-box positioning** (`Render.hh:268-284`) duplicates `applyStatsBox` (`Render.hh:167-187`) with drift between them — a stats-box fix must be made twice.
8. **ETA formatting** computed independently in `Monitor/Methods.hh:17-26` and inline at `:84-106`.

**Non-duplication (checked):** `Config/TypeAid.hh` vs `Physics/TypeAid.hh` are different domains (limit levels vs property names) — keep both; the parallel naming is good convention, not debt.

---

## 4. Convolutions, naming, navigability

### 4.1 The file-name taxonomy is the biggest navigability tax
The per-namespace pattern (`Types` / `Methods` / `Administration` / `Directives` / `Configure`) is *consistent*, which is worth a lot — but several names don't say what's inside:

| Current | Actually contains | Better name |
|---|---|---|
| `*/Administration.hh` | lifecycle: open/start/stop/close + queues | `Lifecycle.hh` |
| `*/Directives.hh` | async worker/watchdog loops, publish paths | `Threading.hh` or `AsyncLoop.hh` |
| `Record/Declaration.hh` | declare-phase API (declareHist1D, …) | `Declare.hh` (fine, minor) |
| `Config/Defaults.hh` | **limits-file parsing**, not defaults | `Limits.hh` |
| `Monitor/Methods.hh` | snapshot builders + string formatting | split or `Format.hh` |
| `Paint/Resolve.hh` | source lookup **+ plan init + TFile open** | split: `Sources.hh` + keep thin `Resolve` |

A new reader cannot guess where `checkpoint()` lives vs `declareHist1D()`. Renaming is cheap now (single-repo, no external users) and gets more expensive every month. Alternative if you don't want renames: a 20-line "what lives where" table at the top of each umbrella header.

### 4.2 Runtime-only lifecycle enforcement
`Record::Writer` requires open→declare→start→fill→finish; `Paint::Illustrator` requires load→resolve→render; `Monitor::AsyncLogger` requires initialise→publish. All enforced (or not — Logger silently no-ops) at runtime. A full type-state redesign is over-engineering here, but two cheap improvements: (a) make `Illustrator::render()` auto-run load/resolve if pending; (b) make Logger `publish()`-before-`initialise()` throw or warn once.

### 4.3 Justified complexity (leave alone)
- The Record quiesce/barrier protocol and clone-per-worker merge model — genuinely good parallel design.
- `resolvePresetChain` cycle detection in Paint — fine.
- Variant-based fill-request dispatch (`std::visit` + `if constexpr`) — idiomatic, keep.
- The Writer's 5-fragment implementation split looks unusual but each fragment is a coherent responsibility; with better names (§4.1) it's a strength, not debt.

---

## 5. Proposed additions (new namespaces / restructuring)

### 5.1 `Utility/RootAid.hh` — checked ROOT access + global-state RAII ★ highest leverage
One new ~100-line header eliminates the largest bug class (§2.3) and the scattered global-state handling:
```cpp
namespace Utility::RootAid {
    void enableThreadSafetyOnce();              // replaces 2 private once-flags
    template <class T> T* get(TDirectory&, const char* name);        // Get + dynamic_cast + throw-with-context
    template <class T> T* require(T* p, std::string_view context);   // null → throw
    struct StyleGuard   { /* save/restore gStyle */ };
    struct BatchGuard   { /* gROOT batch save/restore (move from Paint) */ };
    struct DirectoryGuard { TDirectory::TContext ctx; };              // gDirectory save/restore
    std::unique_ptr<TFile> openRead(const std::string& path);         // open + zombie check + throw
}
```
Record, Probe, and Paint all consume it. This is also where a future Python-facing C API would anchor.

### 5.2 `Utility/Paths.hh` — project-root anchored resolution
Resolve the repo root once (env var `HIGH_ENERGY_ROOT`, else walk up from the exe/cwd looking for an anchor like `configs/`), and route the two hardcoded default paths (§2.6) plus `Config`'s output-directory creation through it. Kills the "must run from repo root" trap before it bites a batch system or a Python wrapper, both of which launch from elsewhere.

### 5.3 `Utility/Toml.hh` — shared TOML helpers
Move `mergeTables` + directory-merge `parseConfig` core here; Config and Paint both call it (§3.5). Add `requirePositive`, `requireInRange` validators (§2.4).

### 5.4 `Physics/Particles.hh` — PDG data table (new, small, high value for next phase)
You currently have no central particle-data table (PDG IDs, masses, charges, names). Lambda reconstruction code presumably hardcodes 3122/2212/-211 somewhere in `modules/`. Before real-data work, add:
```cpp
namespace Physics {
    struct ParticleInfo { int pdgId; const char* name; double massGeV; int charge3; };
    constexpr std::array kParticles = {...};   // Λ, p, π±, K, etc.
    const ParticleInfo& particle(int pdgId);   // checked lookup
}
```
Same self-keyed trait-table pattern you already use — fits the house style. Also: adopt and document **GeV everywhere** as the unit convention (one comment block in `Physics.hh`), since `delta_mass_gev` config keys already imply it.

### 5.5 Future namespace: `Ingest::` (designed in §10, built in Phase 5)
Probe is tuned to reading *your own* Record output. The real samples already in `datasets/` have four different shapes (surveyed in §10.1). Rather than stretching Probe, plan a sibling `Ingest::` namespace that adapts external files into the same `Probe::Event`/feed structures, so everything downstream (Record, Paint, ML export) is unchanged. Keep `Probe::Event` and the spec types free of assumptions that the input was written by Record (they currently are mostly clean; the variant `AuxValue` types are in-memory only, which is good). Full implementation blueprint: §10.

### 5.6 ML/Python interop: a data contract, not a binding layer
Recommendation for the multi-language future: **don't plan on PyROOT bindings to these classes.** Instead:
- Keep everything *persisted* as flat ROOT trees/histograms of POD branches (already true — verified: no variants or maps are written to file).
- Write a short `docs/DataContract.md` stating the output schema (tree names, branch names/types, `About/` metadata layout) and the rule "anything in the output file must be uproot-readable."
- Python side then uses `uproot` + `awkward`/`numpy` for ML feature extraction with zero C++ coupling. This is the lowest-friction multi-language architecture for HEP and removes any pressure to make the C++ utils "bindable."
- Optionally later: a tiny `Export::` helper that writes ML-ready flat ntuples (one row per candidate, plain doubles) — but Record's explicit-tree support already gets you most of this.

### 5.7 Dependency-direction fix (required for the above)
`Utility/Time.hh:10` includes `Config/Types.hh` for `Config::TimePoint`/`Config::uSeconds` — the bottom layer depends on the framework layer, which inverts the documented hierarchy and means Utility can't be extracted/tested alone. **Move the clock aliases into `Utility/Time.hh`** (`Utility::TimePoint`, `Utility::uSeconds`), have `Config/Types.hh` alias them for back-compat (`using TimePoint = Utility::TimePoint;`). Mechanical, ~1-2 hrs.

---

## 6. Test & docs debt

- **No tests:** Physics (trait tables, §2.1 UB path, kinematics edge cases like m²<0), Utility (durationString boundaries), Monitor (stall detection, emergency log write).
- **Gaps in existing tests:** config rejection of invalid numerics (§2.4); Feed-only and mixed Probe streams; Record limits enforcement; concurrent writer contention.
- **Docs:** Architecture.md + UtilsDependencyMap.md are good and current — keep maintaining them. Add the unit convention note (§5.4) and DataContract.md (§5.6). Mark `Plan.md`/`REVIEW.md`/`Issues.md`/`PaintReview.md` as archived (move to `docs/archive/` or add a header line) so future readers (and future AI sessions) don't treat them as current.

---

## 7. Claims investigated and dismissed (don't chase these)

- **"Probe queue has an ABA race"** — false. `pushQueuedFrame` (`Probe/Administration.hh:229-246`) holds the lock continuously from predicate through `push_back`; `markWorkerFinished` increments under the mutex and notifies after. The queue protocol is correct.
- **"Config/Defaults.hh is dead code duplicated in Reader.hh"** — false. Reader includes it; `limitExtractor` is called from `Config.hh:37`. The real issue is only the misleading *name* (§4.1).
- **"Reader.hh uses Utility::numberString without including it"** — false; `Utility.hh` is included at `Reader.hh:14`.
- **Writer/Logger lifecycle coupling** — intentional, documented in UtilsDependencyMap.md; not debt.

---

## 8. Prioritized remediation plan

Score = (Impact + Risk) × (6 − Effort), each 1-5.

| # | Item | I | R | E | Score | Phase |
|---|------|---|---|---|-------|-------|
| 1 | Silent I/O failures (§2.2) | 4 | 4 | 1 | 40 | 1 |
| 2 | `traitsOf(EventIndex)` UB + bounds check (§2.1) | 2 | 4 | 1 | 30 | 1 |
| 3 | Config numeric validation (§2.4) | 3 | 3 | 1 | 30 | 1 |
| 4 | Unchecked ROOT Get/mkdir → `RootAid` (§2.3, §5.1) | 3 | 4 | 2 | 28 | 2 |
| 5 | Global `namespace fs` in Reader.hh (§2.5) | 2 | 2 | 1 | 20 | 1 |
| 6 | Utility→Config dependency inversion (§5.7) | 3 | 2 | 2 | 20 | 2 |
| 7 | CWD-relative paths → `Utility/Paths.hh` (§2.6, §5.2) | 3 | 2 | 2 | 20 | 2 |
| 8 | Checked-lookup + TOML helpers, de-dup (§3, §5.3) | 3 | 2 | 2 | 20 | 2 |
| 9 | Tests for Physics/Monitor/config-rejection (§6) | 3 | 3 | 3 | 18 | 3 |
| 10 | gStyle leakage between Paint results (§2.7) | 2 | 2 | 2 | 16 | 2 |
| 11 | `Form()` fixed-buffer path building (§2.7) | 1 | 2 | 1 | 15 | 1 |
| 12 | DataContract.md + GeV convention doc (§5.6) | 3 | 2 | 3 | 15 | 3 |
| 13 | File-name taxonomy renames (§4.1) | 3 | 1 | 3 | 12 | 3 |
| 14 | `Physics/Particles.hh` PDG table (§5.4) | 3 | 1 | 2 | — (feature) | 3 |
| 15 | Probe double-scan / bounds caching (§3.4) | 2 | 1 | 3 | 9 | 4 |
| 16 | Stall multiplier configurable, Logger init guard (§2.7) | 2 | 1 | 2 | 12 | 4 |
| 17 | `Ingest::` / `Export::` namespaces (§10) | — | — | — | feature | 5 |

### Phase 1 — Correctness hardening (~half a day, no API changes)
Items 1, 2, 3, 5, 11. Pure hardening: stream-state checks, bounds check in `traitsOf`, `requirePositive` at config read sites, scope the `fs` alias, replace `Form()` path building. Verify: rebuild all exes + `tests/run_all.sh`; add one failing-config test per validation.

### Phase 2 — Structural cleanup (~1-2 days, mechanical API touch-ups)
Items 4, 6, 7, 8, 10. Introduce `Utility/RootAid.hh`, `Utility/Paths.hh`, `Utility/Toml.hh`; move clock aliases to Utility with back-compat aliases in Config; sweep Record/Probe/Paint call sites onto the helpers; rename `Config/Defaults.hh` → `Config/Limits.hh`. Verify: full rebuild, all tests, plus one end-to-end run (`_Lambda_Data` with test config: event_count=1000, serial=99) diffing output ROOT file structure before/after.

### Phase 3 — Navigability & future-proofing (~1 day, opt-in scope)
Items 9, 12, 13, 14. Taxonomy renames (or per-umbrella "what lives where" tables if renames feel disruptive), archive stale docs, write DataContract.md + unit convention, add Physics/Monitor tests, add `Physics/Particles.hh`.

### Phase 4 — Performance & polish (deferred)
Items 15, 16. Revisit Probe double-scan performance with real file sizes (the NanoAOD sample is 1.56M events — a wasted full scan is now measurable); make the stall multiplier configurable; add the Logger init guard.

### Phase 5 — `Ingest::` / `Export::` (real-data + ML phase)
Item 17. Full blueprint in §10 below, grounded in the actual files in `datasets/`.

## 9. Verification (applies to every phase)
1. `make` all driver exes + `make tests/<each>.exe`; run `tests/run_all.sh`.
2. End-to-end: run `_Lambda_Data.exe` with the standard test config (event_count=1000, serial=99), confirm output `.root` opens cleanly and `About/` metadata is intact.
3. For Phase 2 path changes: run one exe from a *different* CWD and confirm defaults still resolve (this currently fails silently — it becomes the regression test for §5.2).
4. For Phase 5: each milestone in §10.5 names its own verification dataset from `datasets/`.

---

## 10. Phase 5 blueprint — `Ingest::` and `Export::`

### 10.1 Ground truth: what is actually in `datasets/` (inspected 2026-06-12)

| Sample | Format | Structure (verified by opening the files) | Difficulty |
|---|---|---|---|
| `MasterclassData.root` | LHCb masterclass ntuple | Single flat `DecayTree`: 91,583 entries × 152 **scalar POD** branches, one row per D⁰ candidate (`D0_*`, `OWNPV_*`) | **Tier 1** — trivial |
| `ATLAS_2J2LMET30/ODEO_*.root` | ATLAS Open Data (educational) | Single flat `analysis` tree: 1,015,729 entries × 119 branches — but includes **`ROOT::VecOps::RVec<bool>` and `std::string` branches** (non-POD) | **Tier 1.5** |
| `BTagMu-NANOAOD/*.root`, `MuOnia-NANOAOD/*.root` | CMS NanoAOD | `Events` tree: 1,560,283 entries × **1,347 branches**; pattern = scalar `run/luminosityBlock/event` + per-collection counter `nX` + jagged arrays `X_pt[nX]`, `X_eta[nX]`, … Plus `LuminosityBlocks`/`Runs` trees (POD) and `MetaData`/`ParameterSets` (EDM objects — skip) | **Tier 2** |
| `AO2D.root` (261 MB) | ALICE Run 3 O2 | Many `DF_<id>` TDirectoryFiles per file; each holds **normalized tables**: `O2collision_001` (425 rows), `O2track` (1.47M rows), `O2trackcov`, `O2trackextra_002`, … Tracks reference collisions via index columns. **Tree names carry schema-version suffixes** (`_001`, `_002`) | **Tier 3** |
| `BJetPlusX-AOD /*.root` | CMS Run 1 AOD (EDM) | Full EDM object format; requires CMSSW class dictionaries | **Out of scope** — document the workaround (use NanoAOD-format open data, or convert externally) |

(Housekeeping: the directory `BJetPlusX-AOD ` has a **trailing space** in its name — rename it before any config references it.)

Key insight from the survey: **Probe already owns most of the needed machinery.** NanoAOD's pt/eta/phi/mass quadruplet maps directly onto the existing `PtEtaPhiMSpec` coordinate spec; the `nX`+jagged-array pattern matches `EventParticleReaderArray`; AO2D's index-column joins match `EventNodeReaderRowJoin`. The gaps are: format *detection*, multi-directory (DF) iteration, schema-version suffix resolution, non-POD branch types (RVec/string), and branch-subset ergonomics when a tree has 1,347 branches.

### 10.2 `Ingest::` structure

```
utils/Ingest.hh                    — umbrella, mirrors house style
utils/Ingest/
    Types.hh        — SourceKind {FlatNtuple, NanoAOD, AO2D}; SourceSpec
                      (file, kind, tree/collection selectors, branch maps)
    Detect.hh       — sniffFormat(TFile&) → SourceKind:
                        has "Events" tree + nX counters        → NanoAOD
                        has DF_* TDirectoryFile children       → AO2D
                        single TTree of scalars                → FlatNtuple
    ConfigAid.hh    — [ingest] TOML section → SourceSpec
                      (mirrors Probe/ConfigAid.hh conventions)
    Readers/
        Flat.hh     — Tier 1/1.5: flat-tree adapter
        NanoAOD.hh  — Tier 2: counter+jagged-array adapter
        AO2D.hh     — Tier 3: DF iteration + table joins
    Administration.hh — lifecycle + (later) parallel streaming
```

Design decisions:
1. **Adapters emit `Probe::Event`** (and feed structures), so Record, Paint, Monitor, and Export are untouched downstream. `Ingest → Probe` is the dependency direction (allowed: Ingest is a peer of the drivers' read path); Ingest reuses `Probe::BranchControl` (`requireBranch`, coordinate specs, `detectBranchType`) rather than duplicating it. If reuse pressure grows, promote `BranchControl` to `Utility/` later — don't pre-move it.
2. **Branch mapping lives in TOML, not code** — e.g. `[ingest.particles.muon] pt="Muon_pt" eta="Muon_eta" phi="Muon_phi" mass="Muon_mass" count="nMuon"`. Same declarative style as `[probe.events.particles.*]`, so the config mental model stays uniform.
3. **Extend `BranchType`** (in `Probe/Types.hh` or `Utility/RootTypes.hh`) with `Float32` (NanoAOD is mostly floats, not doubles), `Bool`, `RVecBool`, `StdString` — detected via `TBranch`/`TLeaf` type names. This is the only Probe-side change Tier 1.5/2 need.
4. **AO2D specifics (Tier 3):** iterate `DF_*` dirs as an outer loop (each DF is an independent batch — natural parallelism unit, one worker per DF); resolve version suffixes by scanning keys for `^O2<name>(_\d+)?$` and taking the highest suffix; join tracks→collisions via the index column using the RowJoin pattern.
5. **Schema survey tool first:** before any adapter, build `_IngestSurvey.cc` — a driver that opens any ROOT file and dumps tree/branch/type inventory (the C++ version of what this audit did by hand). It doubles as your learning instrument for each new dataset and as the debugging tool when a mapping fails.

### 10.3 `Export::` structure (ML hand-off)

```
utils/Export.hh
utils/Export/
    Types.hh     — TableSpec {name, columns: {label, source property/aux}}
    Table.hh     — TableWriter: flat TTree of PODs, one row per
                   candidate/event; column order = declaration order
    Configure.hh — [export] TOML section
    CSV.hh       — (optional, later) small-file CSV for quick pandas checks
```

Design decisions:
1. **The interchange format is a flat ROOT TTree of scalar PODs** (float/double/int32/int64), one row per training example. That is the one format every Python HEP-ML stack ingests in one line (`uproot.open(f)["table"].arrays(library="np"/"pd")`). No Parquet/HDF5 writer in C++ — if ever needed, convert on the Python side.
2. **Schema self-description:** reuse `Record::Meta`'s `About/` pattern — write column descriptions, source dataset, selection config, and git SHA into the export file. The `docs/DataContract.md` from §5.6 governs both Record and Export output.
3. **Reproducible splits:** add a deterministic `split_hash` column (e.g. hash of run/event/candidate index) so train/val/test splits are stable across re-exports — decided in Python, but the hash must come from C++ so it survives re-processing.
4. **Export is a consumer of `Probe::Event`** — same position in the pipeline as Record. A driver streams events (from Probe *or* Ingest) and fills both Record histograms and Export tables in the same pass.
5. **Python validation stub:** add `py/check_contract.py` (uproot + numpy only) that opens any Record/Export output and asserts the contract (expected trees, POD-only branches, About/ present). Run it in `tests/run_all.sh` if Python is available; it is the round-trip test that keeps the multi-language door open.

### 10.4 What to do *now* (during Phases 1–3) to keep Phase 5 cheap
- §5.1 `RootAid` checked-get helpers — every adapter needs them (highest-leverage prerequisite).
- §5.7 dependency fix — Ingest must be able to sit beside Probe without inheriting the Utility→Config tangle.
- Keep `AuxValue`/variant types out of anything persisted (already true — preserve it).
- When touching `Probe/BranchControl.hh` in Phase 2, keep it free of `ProbeConfig` coupling so Ingest can include it standalone.
- Rename the `BJetPlusX-AOD ` directory (trailing space).

### 10.5 Milestones (each ends with a working artifact)

| # | Milestone | Verify against | Est. |
|---|---|---|---|
| 5.0 | `_IngestSurvey.cc` schema-dump driver | all five samples | 0.5 day |
| 5.1 | `Ingest::Detect` + `Ingest::Readers::Flat` (POD only) | `MasterclassData.root` → D⁰ mass histogram through Record + Paint, end-to-end | 1–2 days |
| 5.2 | Non-POD branch types (Float32/Bool/RVec/string) | ATLAS `analysis` tree → lepton kinematics plot | 1 day |
| 5.3 | `Ingest::Readers::NanoAOD` (counter+jagged) | `MuOnia-NANOAOD` → dimuon invariant mass (J/ψ peak — a genuinely satisfying first real-data result) | 2 days |
| 5.4 | `Export::TableWriter` + `py/check_contract.py` | export 5.3's dimuon candidates; load in pandas | 1 day |
| 5.5 | `Ingest::Readers::AO2D` (DF iteration + joins) | `AO2D.root` → track multiplicity / kinematics per collision | 2–3 days |
| 5.6 | Parallel ingest (reuse ProbeParallel patterns; DF-per-worker for AO2D) | AO2D + NanoAOD timing vs serial | 1–2 days |

Milestones 5.1–5.4 are deliberately sequenced as a learning path: flat tree → typed branches → jagged event structure → ML hand-off, each one validated by a physics result you can see in Paint.

---

## 11. Progress log

### Phase 1 — DONE (2026-06-12), all 6 test suites green, e2e verified

Planned items, all landed:
- §2.1 `traitsOf` bounds checks (both overloads) — `Physics/Types.hh`
- §2.2 silent I/O: `writeTextFile` stream check (warn-not-throw: emergency-log path), `saveCanvas` post-`Print` file-existence check, `Meta` merge failures now warn with context
- §2.4 `requirePositive`/`requireNonNegative` validators applied to `event_count` (0 stays legal = "all events"), `bin_count`, `hist_scaling`, both queue capacities, `sr_padding`
- §2.5 `fs` alias scoped into `namespace Config`
- §2.7 both `Form()` path builders replaced with `ostringstream`

New findings during verification (not in the original audit):
1. **The branch didn't compile.** All committed `.exe`s were stale; `utils/` at HEAD fails to build (clang/toml++ drift). Two pre-existing fixes required:
   - `Probe/Methods.hh:361` — `namespace detail` opened and never closed before member definitions; ~450 lines (BranchHandle + all reader ctors) were silently inside `Probe::detail`. Closed after the handle factories; re-opened around the Phase-5 helpers and IMT binders that *are* referenced as `detail::`.
   - `Config/Defaults.hh:52` — const-correctness: `TomlTable&` bound to const node.
2. **Makefile didn't track header dependencies** — the root cause of the stale exes. Added `-MMD -MP` + `-include *.exe.d` and extended `clean`. Header edits now trigger rebuilds.
3. **`source_search` glob support was spec'd but unimplemented** — `test_paint` "Phase 36" expects `*_Hist` to work; docs disagree (all.toml says glob, Paint.toml says regex). Implemented: regex first, glob→regex fallback (`globToRegex` in `Paint/Resolve.hh`). All 27 paint tests pass, including the previously-aborting glob + `?`-wildcard tests.
4. **Output filename ordering bug**: `configurePythia` set `reg.beamEnergy` *after* `readPathsAndFile` baked the file title → `Lambda_Gen_GeV_1k.root` (no energy; compare old `_01/Lambda_Recons_7000GeV_10k.root`). Fixed: energy (TOML or cmnd-file `Beams:eCM`) resolves before paths; redundant late fallback removed from `Configure.hh`. Verified: `Lambda_Gen_7000GeV_1k.root`.

One audit finding corrected: §2.4's "unknown limit keys silently skipped" is partially intentional — `[record.limits.*]` is shared with `Lambda::extractPhysics` (object-keyed sections `Unvalidated`/`Validated`/`Selected`), so a per-key warning is wrong (fires on every run). Reverted to a documented silent skip naming the second consumer. **Note for Probe pipeline:** reconstruction outputs (`_15`, `_23`, `_25`) also lack the energy in filenames — that path never sets `beamEnergy` before paths; needs a design decision (read `About/physics/center_of_mass_energy_gev` from the probe input before `readPathsAndFile`?) — deferred to Phase 2/4.

Verification artifact kept: `dump/phase1_e2e.toml` (event_count=1000, serial=99) for re-use in later phases.

### Phase 2 — DONE (2026-06-12), all 6 suites green, e2e + from-/tmp verified

- **New headers:** `Utility/RootAid.hh` (enableThreadSafetyOnce, `require<T>`, `get<T>`, `openRead`, `BatchGuard`, `StyleGuard`), `Utility/Toml.hh` (shared `mergeTables`/`parseConfigTable` + validators), `Utility/Paths.hh` (`HIGH_ENERGY_ROOT` env var, else walk-up-to-`configs/` anchor).
- **Dependency inversion fixed:** clock aliases (`TimePoint`/`uSeconds`/`Seconds`) now defined in `Utility/Time.hh`; `Config/Types.hh` re-exports them. Utility no longer includes Config.
- **De-dup:** Config and Paint both delegate TOML merge + directory-parse to `Utility::Toml` (two identical implementations deleted); both ROOT thread-safety once-flags delegate to RootAid.
- **Paths anchored:** `resolveLimitsPath`, the default Limits.toml pass, and Paint's `default_style` all resolve through `Utility::Paths::resolveProjectPath`. Verified: running from `/tmp` with `HIGH_ENERGY_ROOT` set resolves `configs/Lambda_Limits.toml` absolutely (previously a silent skip/throw).
- **gStyle leakage fixed:** `renderPlan` wraps each result in a `StyleGuard` (full `TStyle::Copy` restore); ad-hoc `BatchRestore` replaced by `RootAid::BatchGuard`.
- **Rename:** `Config/Defaults.hh` → `Config/Limits.hh` (it parses limits, not defaults).
- **Kinematic safety:** `EventParticleReaderArray::readForEvent` now throws on coordinate-array size disagreement instead of reading garbage.
- **Audit correction:** §2.3's Probe claims were overstated — all six `file->Get` reader sites already check-and-throw; only the kinArrays size check was real. Meta's `writeAbout` is null-safe by contract (`writeStr`/`writePar` guard).

### Phase 3 — DONE (2026-06-12), 7/7 suites green (new test added), e2e verified

- **Taxonomy renames landed:** `{Record,Probe,Monitor}/Administration.hh` → `Lifecycle.hh`; `{Record,Probe}/Directives.hh` + `Monitor/Directive.hh` → `Threading.hh`. All includes, umbrella-header maps (Probe.hh gained a full submodule map), Writer.hh section comments, and docs updated.
- **Docs:** archived `Plan.md`, `REVIEW.md`, `Issues.md`, `PaintReview.md`, `ProbeStream.md` (implemented plan), and `Dependencies.md` (stale duplicate of UtilsDependencyMap.md) into `docs/archive/`. `Architecture.md`/`UtilsDependencyMap.md`/`MAP.md` updated to new filenames. New `docs/DataContract.md` (uproot-readable output contract + layout + Python example).
- **Physics:** new `Physics/Particles.hh` (PDG table, checked lookup, antiparticle resolution); GeV unit-convention block in `Physics.hh`; `Energy_Transverse`≡`Mt` subtlety documented at the trait.
- **New test binary `tests/test_utils_hardening.exe`** (registered in Makefile + auto-discovered by run_all.sh): traitsOf bounds/extractors, PDG lookups, kinematics edges (spacelike mass, Δφ wrap), Toml validators, path anchoring, config numeric rejection (incl. event_count=0 stays legal), writeTextFile failure path.
- **New finding (real landmine):** include cycle `Monitor/Report.hh → Record/Writer.hh → Record/Lifecycle.hh → Monitor/Threading.hh → Report.hh` — compiles only if Record enters the include graph first; every existing TU did so by luck. Fixed cheaply: `Monitor.hh` now includes `Record/Writer.hh` first with an explanatory comment, making umbrella include order irrelevant. The *proper* decoupling (declare/define split of Report.hh) is a Phase 4 candidate.

**Consciously deferred from Phase 3:** `Monitor/Methods.hh` split (snapshot builders vs formatters) and `Paint/Resolve.hh` split (`Sources.hh`) — both are pure-churn refactors; do them opportunistically when those files next change.

**Remaining for Phase 4/5:** see §8 items 15-17 and §10. Plus: Probe-pipeline output filenames still lack beam energy (needs design decision per Phase 1 note); Report.hh declare/define split.
