# 03 — Integration Options (ADR-style)

Date: 2026-09-16 · Status: **Proposed** (analysis only; nothing implemented)

**Question.** Can Rivet, YODA, HepMC3, LHAPDF and FastJet be brought into
the module-style `utils/` stack so that PhotoProduction-type runs get the
same configuration, monitoring, failure handling and provenance as the
Lambda pipeline — without giving up the community tooling (Rivet
analyses, YODA, `rivet-mkhtml`, HEPData references)?

**Short answer.** Yes. The recommended path is incremental: fix the seams
first, unify configuration, decouple Monitor from Record, then add an
**in-process Rivet stage** behind a small **event-sink** abstraction, with
HepMC files kept as an optional sink. Plotting stays in Python.

---

## 1. Requirements

### Functional
- F1 Generate Pythia events from existing `.cmnd` files (asymmetric beams, photoproduction, LHAPDF sets).
- F2 Run one or more Rivet analyses (project plugins + standard analyses) with options.
- F3 Produce YODA outputs normalised with the **merged** generator cross-section.
- F4 Sweep run matrices (PDF sets now; pT0Ref, MPI on/off, beam energies next) with deterministic names and seeds.
- F5 Plot/compare/merge YODA outputs, optionally with reference data.
- F6 Optionally write HepMC3 for reuse (Delphes, other analyses) and optionally analyse existing HepMC3 files.
- F7 Keep the Lambda pipeline (Probe/Record/Paint) working.

### Non-functional
- N1 Progress, ETA, stall detection and graceful stop for multi-hour runs.
- N2 Provenance: git SHA, config snapshot, cmnd/plugin SHA-256, seed, PDF, σ in every output.
- N3 Throughput not capped by a text round-trip.
- N4 Builds must not require every optional package.
- N5 Everything a run depends on is in the repo.

### Constraints
- Single developer; Linux Lab_PC now, Mac later (different stack) → optional deps must degrade gracefully.
- C++17 header-only house style; `Rivet`, `YODA`, `HepMC3`, `fastjet`, `LHAPDF` namespaces are taken → new project namespaces must not collide.
- `PythiaParallel` runs callbacks **serially by default** (`Parallelism:processAsync = off`, `Parallelism.xml:161`) and has **no abort API**; it exposes merged `sigmaGen()` / `weightSum()` but no merged σ error (`PythiaParallel.h:65-68`).
- `Rivet::AnalysisHandler` is not thread-safe (construction must be locked; one handler per thread; `merge()` to combine — `RivetHooks.h:87-115,147-187`).

---

## 2. Options

### Option 0 — Harden the toolchain, keep it separate

Move `~/HEP/{rivpyth,ydplt,ydmrg,rivpyth_common.py}` into the repo
(`tools/`), fix the FIFO hang (B1), pass merged σ and provenance to Rivet
(via `rivet -x` / YODA annotations sidecar), fix the Makefile (M1–M3),
repair stale configs (A1, B2).

- **Config/Monitor integration:** none (by design).
- **Pros:** cheapest; zero C++ architecture change; immediately safer.
- **Cons:** three config languages remain; no progress/stall; ASCII bottleneck; two philosophies coexist indefinitely.
- **Effort:** S (½–1 day). **Risk:** very low.

### Option A — Unified configuration, process pipeline kept

One TOML grammar for both stacks. The generator becomes a real driver
(`sources/PhotoProduction/_Generate.cc`) that uses `Config::` (new
`[rivet]`, `[hepmc]`, `[sweep]`, `[plot]` sections) and `Monitor::` for
progress; Python tools read the **same** file and only launch/plot.

- **Config integration:** full — same parser, same section ownership, same path/naming rules, migration errors for old `[analysis]/[yoda]/[rivpyth]` keys.
- **Monitor integration:** generator gets progress/ETA/stall — **requires** Monitor to run without a `Record::Writer` (A3).
- **Pros:** one mental model; provenance can be written by C++; Python becomes thin.
- **Cons:** FIFO + ASCII remain (B3, B6); failure semantics still cross processes.
- **Effort:** M (2–3 days incl. Monitor decoupling). **Risk:** low.

### Option B — In-process Rivet stage (recommended core)

A C++ driver runs `PythiaParallel` and feeds each event to project-owned
Rivet handlers; no FIFO, no HepMC text.

```
PythiaParallel.run(cb) ── cb(Pythia* w) ──► Generate::Dispatcher
                                              │ countEvent / publish (Monitor)
                                              │ stopRequested (Signals)
                                              ▼
                                   Observe::RivetSink[w.index]
                                   (Pythia8ToHepMC per thread → AnalysisHandler)
 end of run: merge handlers → setCrossSection(pythia.sigmaGen()…) → finalize
             → annotate provenance → writeData(<name>.yoda)
```

Design points:
- **Project-owned sink, not `libpythia8rivet.so`** — avoids the double-merge question (R1), lets us set the merged σ, add provenance annotations, and report progress.
- **Concurrency mode from config:** `processAsync = off` → one handler, no locks (simplest; correct; Rivet then costs wall time serially); `processAsync = on` → one handler per worker, merged at the end. Measure before choosing the default (FastJet ×3 incl. SISCone may dominate).
- **Cross-section:** after `run()`, `handler.setCrossSection(pythia.sigmaGen() [mb→pb], err, true)` before `finalize()`. `sigmaErr` is not exposed by `PythiaParallel`; combine from `pythia.stat()` or per-instance `info.sigmaErr()` via a hook — open question Q3.
- **Graceful stop:** cooperative skip (same pattern as Lambda drivers); on stop, finalize and write a **partial** YODA with `n_events_processed` annotation.
- **Periodic dumps:** `AnalysisHandler::setFinalizePeriod` ↔ `[monitor.intervals].checkpoint_interval` (Rivet's own checkpointing, fits the Monitor vocabulary).
- **Namespace:** `Observe::` (observables vs data) — avoids clashing with `Rivet::`.
- **Config integration:** `[rivet]` section owned by `Observe::configure`; plugin search path, analyses (+options), check_beams, preloads, dump period.
- **Monitor integration:** identical call pattern to `Lambda::pythiaAnalysis` (`countEvent`, `publish`, `publishThreadStats`), plus a report hook (`programLog` = analyses list + σ).
- **Pros:** removes B1/B3/B6 by construction; progress/stall/provenance for free; one process to debug.
- **Cons:** Rivet+ROOT+Pythia in one binary (link weight, symbol hygiene); non-Pythia generators need Option D.
- **Effort:** M (3–4 days after A). **Risk:** medium (merge semantics, σ error, thread safety) — mitigated by an equivalence test against the current FIFO pipeline.

### Option C — Event-sink abstraction (dual output)

Generalise B's dispatcher so one event loop can feed any set of sinks:

| Sink | Backed by | Output |
|---|---|---|
| `Observe::RivetSink` | `Rivet::AnalysisHandler` | `.yoda` |
| `Generate::HepMCSink` | `Pythia8ToHepMC` (per-thread files, or merged with a lock) | `.hepmc` / `.hepmc.gz` / HepMC3-ROOT |
| `Generate::ModuleSink` | a `modules/*` callback → `Record::Writer` | `.root` (+`About/`) |

- Enables "Rivet validation + custom C++ reconstruction + ML export" from the **same events**, and HepMC for Delphes.
- Collapses the duplicated driver boilerplate of `_Lambda_Data/_Lambda_Parallel` into `Generate::run(config, sinks)`.
- **Config:** `[sinks] enabled = ["rivet", "record", "hepmc"]` (or presence of sections).
- **Monitor:** one logger for the whole run; each sink contributes a report fragment and a finalize step.
- **Effort:** M (2–3 days on top of B). **Risk:** low–medium (lifecycle ordering across sinks).

### Option D — HepMC3 as an input (Probe/Ingest)

Read existing HepMC3 files (any generator) as a Probe-style source, then
fan out to the same sinks. Matches the planned `Ingest::` phase
(`docs/UtilsAudit.md` §10).

- **Pros:** generate once, analyse many; Herwig/Sherpa/MadGraph outputs join the same pipeline.
- **Cons:** HepMC3 ASCII readers are serial; partitioned parallel reading needs HepMC3-ROOT format or chunking.
- **Effort:** L (4–6 days). **Risk:** medium. **Defer** until a second generator is actually used.

### Option E — YODA ⇄ ROOT bridge for Paint / DataContract

Add a YODA source type to `Paint::Resolve` (via YODA C++ reader) or convert
with `yoda2root`, so Rivet outputs can be styled by Paint and read by
uproot-based ML tooling.

- **Pros:** one plotting style across projects; ROOT/uproot access.
- **Cons:** duplicates what `rivet-mkhtml` already does well (ratio panels, reference data, `.plot` files).
- **Effort:** S–M. **Recommendation:** optional, low priority; keep `rivet-mkhtml` as the primary YODA plotter.

### Option F — Generic DAG/pipeline framework (rejected)

Stages as plugins with a scheduler (Snakemake-like, or home-grown).
Over-engineered for one developer and 2–3 stage runs; campaign
orchestration is better served by a small `[sweep]` expander plus batch
submission later.

### Option P — Pure Python in-process (rejected)

`pythia8` + `rivet` Python bindings in one Python process. Loses
`PythiaParallel` ergonomics and C++ Monitor/Record integration; GIL and
per-event Python overhead. Rejected for generation; Python stays the
plotting/orchestration layer.

---

## 3. Evaluation

Scores 1 (poor) – 5 (good).

| Criterion (weight) | 0 | A | B | A+B+C | D | E |
|---|---|---|---|---|---|---|
| Config unification (3) | 1 | 5 | 3 | 5 | 3 | 2 |
| Monitor/observability (3) | 1 | 4 | 5 | 5 | 4 | 1 |
| Failure semantics (3) | 3 | 3 | 5 | 5 | 4 | 3 |
| Throughput (2) | 2 | 2 | 4 | 4 | 3 | 3 |
| Provenance (2) | 2 | 4 | 5 | 5 | 4 | 3 |
| Interop / community tools (2) | 5 | 5 | 4 | 5 | 5 | 3 |
| Build/portability (2) | 5 | 4 | 3 | 3 | 3 | 4 |
| Effort (inverse) (2) | 5 | 4 | 3 | 2 | 1 | 4 |
| Risk (inverse) (1) | 5 | 4 | 3 | 3 | 3 | 4 |
| **Weighted total (/100)** | **58** | **78** | **80** | **86** | **68** | **56** |

---

## 4. Decision (proposed)

Adopt **0 → A → B → C** as a staged path; defer **D**; treat **E** as
optional; reject **F**, **P**. Rationale:

- Option 0 items are defects, not design choices — fix regardless.
- A is valuable on its own and is a prerequisite for B (shared schema,
  Monitor decoupling).
- B removes the structural problems of the FIFO pipeline (hang, σ,
  serialisation) while keeping Rivet analyses and YODA outputs
  unchanged — downstream plotting does not notice.
- C is where the two projects actually merge: one event loop, many sinks.
- The FIFO/HepMC path is **kept** as `rivet.mode = "external"` so
  non-Pythia generators and debugging workflows keep working.

## 5. Compatibility requirements (Config & Monitor)

| Requirement | Why | Where it lands |
|---|---|---|
| Monitor runs without a Writer: `AsyncLogger::initialise(const Monitor::RunPaths&)`; Writer overload forwards `writer.runPaths()` | Rivet-only runs have no Writer (A3) | Roadmap Phase 2 |
| Report text built from hooks, not from `Record::Writer` | Breaks the Monitor↔Record include cycle | Phase 2 |
| Output naming independent of Record: `Config::OutputPlan{dir, title, logs, checkpoints}`; extension chosen by sink | `.yoda`/`.hepmc` need the same naming rules as `.root` | Phase 2 |
| √s resolved **after** `init()` from `pythia.info.eCM()`; TOML `beam_energy` rejected when `Beams:frameType != 1` | A2 | Phase 1 |
| One parsed `toml::table` passed to all `configure*` overloads (path overloads kept as wrappers) | A5; lets Python-validated and C++-validated configs share one document | Phase 1 |
| Strict getters + unknown-key warnings in `Utility::Toml` | Parity with `rivpyth_common` strictness | Phase 1 |
| Provenance record reused for YODA (`Record::Meta::Record` → YODA annotations / sidecar) | N2 | Phase 3 |
| `[threads].pythia` precedence reused; new `[threads].rivet` only meaningful with `processAsync` | Consistent thread vocabulary | Phase 3 |
| Makefile: per-target feature flags (`NEEDS_RIVET`, `NEEDS_ROOT`…) or `pkg-config`-style lazy flags; header deps restored | N4, M1–M3 | Phase 0 |

## 6. What to revisit as the system grows

- Batch submission (HTCondor/SLURM): a `[sweep]` point should be runnable in isolation (`--point i`) — design for it now, build later.
- Multi-weight (PDF/scale) variations: Pythia can emit weight variations and Rivet handles them natively — this may **replace** sequential PDF re-runs for the proton PDF. Revisit once B lands (open question Q5).
- HepMC3-ROOT format for Option D parallel reading.
- If the Mac stack lacks Rivet, the in-process driver must compile out cleanly (feature macro) while Lambda drivers still build.
