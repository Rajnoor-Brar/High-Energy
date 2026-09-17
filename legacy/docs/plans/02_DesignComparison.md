# 02 — Design Philosophy Comparison

Date: 2026-09-16. Companion to `01_CurrentState.md`.

The two workflows solve different problems — **A** builds a custom
reconstruction and writes analysis-ready ROOT data; **B** generates events
and compares them to published measurements through a community-validated
analysis layer. This document compares *how* they are designed, not
*what* they compute, so the good ideas of each can be kept when they are
brought together.

---

## 1. One-line characterisation

| | Workflow A — module stack | Workflow B — toolchain |
|---|---|---|
| Metaphor | **Framework**: the library owns the run; the driver is a composition root | **Unix pipeline**: independent tools own their own runs; a script wires them |
| Unit of reuse | Namespaced header subsystem (`Config`, `Probe`, `Record`, `Monitor`, `Paint`) | Executable / community tool (`generator.exe`, `rivet`, `rivet-mkhtml`, `yodamerge`) |
| Contract between parts | C++ types (fill requests, `Watch`, `Paths`, hooks) | File formats (HepMC3, YODA) and CLI arguments |
| Where complexity lives | Inside the library (threading, lifecycle, provenance) | At the seams (process supervision, path conventions, format quirks) |

---

## 2. Configuration philosophy

### 2.1 Side by side

| Dimension | A | B | Assessment |
|---|---|---|---|
| **Scope of one file** | Everything about one run: counts, threads, generator overrides, outputs, metadata, monitoring, physics cuts, limits | One run *campaign*: plugin, cmnd, counts, PDF sweep, plotting, paths | B's "campaign" (a run matrix) is a concept A lacks |
| **Sectioning principle** | By **subsystem** (`[pythia]`, `[record]`, `[monitor]`) | By **tool/stage** (`[analysis]`, `[yoda]`, `[rivpyth]`) | Same idea, different axis; A's is more stable as tools change |
| **Who parses** | Each subsystem parses its own section (decentralised, re-parsed several times) | One function parses everything (centralised) | B's single typed config object is the better model; A's per-subsystem ownership is the better *boundary* |
| **Typing & validation** | `value_or` with defaults (type errors fall back silently), range validators on a few keys, rich *migration* errors for removed keys | Strict type checks on every key, ranges, cross-field rules; no migration story | Combine: B's strictness + A's migration errors |
| **Unknown keys** | Ignored | Ignored | Both should warn (typo → silently default) |
| **Layering / reuse** | Directory-of-files merge; `[threads]` global → per-section precedence | None | A's merge enables "base + variant" configs (valuable for PDF/pT0Ref/energy scans) |
| **Documentation** | `all.toml` canonical reference + annotated templates naming the C++ field each key feeds | Embedded `EXAMPLE` string in the script | A's approach scales; B's drifts (see B2) |
| **Physics boundary** | `.cmnd` for physics, TOML for run control — but TOML *can override* `Beams:eCM` | `.cmnd` for physics, CLI overrides seed/PDF/threads | Both agree physics belongs in `.cmnd`; A's eCM override is unsafe for `frameType = 2` (A2) |
| **Paths & naming** | Explicit keys with booleans composing a title (prefix/serial/energy/events) + subdirs | Convention (`<root>/<project>/`) + serial + variant suffix; `path_literal` escape | B is terser; A is more self-describing. Both are deterministic |
| **Run matrix** | None — one config = one run | First class (PDF list, aliases, suffix policy, seed offset) | Must be kept in any integration |
| **Analysis parameters** | In TOML (`[lambda]`), read at runtime | Hard-coded in plugin source (3 copies) | A's runtime parameters are better; Rivet *options* give B the same capability |

### 2.2 What each gets right

**A**
- *Subsystem-owned sections*: a new tool adds a section without touching others.
- *Migration errors*: renamed keys fail loudly with the replacement name.
- *Composable files*: `configs/<run>/00_base.toml + 10_variant.toml`.
- *Reference file + templates*: the schema is discoverable.

**B**
- *One typed config object* validated up front, before any process starts.
- *Run matrix as data*: sweeps are declared, not scripted.
- *Convention over configuration*: four keys locate everything.
- *Clear physics boundary*: TOML never rewrites beam kinematics.

### 2.3 Where each is weak

**A**: silent type fallbacks; repeated parsing with no single config
object; Lambda-specific defaults leak into generic `Config::Register`;
beam energy inferred from a setting that is not authoritative.

**B**: three configuration languages for one run (TOML, positional CLI,
C++ constants in the plugin); schema lives outside the repo; no layering,
so every variant is a full copy (`eic_18x275_*.cmnd` ×4 differ by 1 line).

---

## 3. Inter-tool coordination philosophy

### 3.1 Side by side

| Dimension | A | B |
|---|---|---|
| Coupling | Tight, compile-time (types, includes; Monitor↔Record include cycle) | Loose, run-time (files, exit codes) |
| Data transport | In-memory `FillRequest`s over bounded queues | HepMC3 ASCII over a FIFO |
| Backpressure | Bounded queues block producers | Pipe buffer blocks the generator |
| Parallelism | Generator N + writer M + logger 1, tuned per stage | Generator N → **one** serialising writer → **one** Rivet thread |
| Progress & liveness | `countEvent/publish`, bar/ETA, stall → fatal shutdown | None |
| Cancellation | Cooperative flag; partial output finalised | SIGINT/TERM forwarded; partial YODA not written by Rivet on kill |
| Failure propagation | Exceptions + barriers across threads | Exit codes; one ordering bug hangs (B1) |
| Provenance | Built into the writer (`About/`) | None |
| Swappability | Generator swap requires C++ changes | Any HepMC producer (Herwig, Sherpa, file) plugs in |
| Validation pedigree | Custom code, tested locally | Rivet analyses + HEPData references, community-validated |
| Debuggability | One process, one debugger | Each stage runnable alone (`rivpyth -p` prints commands) |

### 3.2 The core trade-off

A optimises for **control** — throughput, observability, provenance and
failure semantics are designed in. B optimises for **interoperability** —
the stages are standard tools whose inputs and outputs every HEP
physicist already reads.

The integration question is therefore not "which one wins" but **where
the process boundary should sit**:

```
   A-style (in-process)                        B-style (process boundary)
   ───────────────────                        ──────────────────────────
   Pythia ─cb─► Rivet handler(s)              Pythia ─► HepMC ─► rivet
      │                                           (file/FIFO)
      └─cb─► Record::Writer                   good when: generator ≠ Pythia,
   good when: throughput, progress,           events reused many times,
   provenance, σ normalisation matter         external tools (Delphes) consume HepMC
```

Both are legitimate; a mature stack should support **in-process as the
default** and **HepMC files as an optional sink/source**, chosen by
config — not by which script you run.

---

## 4. Principles to carry forward

1. **Physics in `.cmnd`, run control in TOML.** TOML never rewrites beam
   kinematics; derived values (√s) are read *after* `init()` from
   `pythia.info.eCM()`.
2. **One parsed, validated config object per run**, with sections still
   owned (parsed/validated) by their subsystem.
3. **Strict typing + migration errors + unknown-key warnings.**
4. **Run matrices are data** (`[sweep]`), expanded before execution,
   each point a fully-resolved run with its own seed and name.
5. **Library owns lifecycle** (progress, stall, signals, provenance) for
   anything that runs for minutes.
6. **Standard formats at the edges** (HepMC3, YODA, ROOT) — never invent
   a new interchange format.
7. **Everything the run depends on is versioned in the repo**, including
   orchestration scripts.
8. **Optional dependencies are optional at build time too.**
