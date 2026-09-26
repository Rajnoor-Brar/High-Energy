# 02 — Design

The architecture as built. [MAP.md](../MAP.md) is the directory of what lives where; this explains
why the boundaries are where they are, and what happens if you move one.

---

## 1. Two halves, one contract

```
                  ┌──────────────────────── hep (Python, package hekit) ───────────────────────┐
  config.toml ──► │ config → sweep → plan → adapters → run(supervisor) → results → plot / proc │
                  └───────┬──────────────────────────────────────────────▲────────────────────┘
                          │ spec.toml (resolved)                         │ JSON lines on fd 3
                          ▼                                              │
                  ┌─────────────────────────── hep-run (C++) ────────────┴────────────────────┐
                  │  Source ──► Run::Loop ──► Analyzers {Rivet, Modules, Store, Delphes, Count}   │
                  └───────────────────────────────────────────────────────────────────────────┘
                                                      │
                                                      ▼
                                       analysis.yoda, events/, *.root, logs/
```

| | `hep` | `hep-run` |
|---|---|---|
| Owns | configuration, judgement, orchestration, output | the event loop |
| Decides | what to run, with what seeds, in what order, where it goes | nothing — it is told |
| Links | ROOT, matplotlib, uproot, rich, click | Pythia, YODA, and optionally Rivet/HepMC3/ONNX |
| Speaks | TOML in, terminal and files out | resolved spec in, status on fd 3 out |

**The narrowness is the design.** `hep-run` has no config parser, no defaults, no knowledge of
studies or sweeps. It cannot disagree with `hep` about what a value means, because it never
interprets one.

### The executable's whole surface

```
hep-run SPEC.toml              run it
hep-run SPEC.toml --check      configure and initialise, generate nothing
hep-run SPEC.toml --list N     print the first N events as status messages
hep-run SPEC.toml --plain      force plain progress on stderr, even with fd 3 open
hep-run --capabilities         what this build can do, as JSON
```

You never add a flag here. You add a key to the spec schema.

**Parsing is strict** — an unknown option is a usage error, because a silently ignored flag in a
batch job is worse than a failure. **Exit codes are a contract**: `0` ok, `1` spec/card, `2` usage,
`3` init, `4` source, `5` analyzer, `6` stopped-with-partials, `7` stalled, `70` internal.

---

## 2. The C++ side: eleven namespaces, strictly ranked

```
Core ─► Status ─► Events ─► { Store, Results, ML, Phys } ─► { Source, Module } ─► Analyzer ─► Run ─► apps
 0       1         2          3                              4                    5       6
```

A lower layer never links a higher one. The ranking is enforced by the CMake link graph — each
namespace is an `INTERFACE` library naming exactly its allowed dependencies — which is why it
mostly held: **two violations in 6,837 lines**, both caused by the same 9 lines of value types
(`Analyzer::Needs`, `Analyzer::Output`) living in the namespace of the thing they *describe* rather than in
one both sides can see. `Core::AnalyzerSpec` already exists as the precedent for the fix.

| Namespace | Owns | Depends on |
|---|---|---|
| `Core` | spec reading, hashing, clocks, signals, exit codes, provenance | — |
| `Status` | the JSON-lines stream, heartbeats, progress | Core |
| `Events` | the per-event view: live Pythia or a lazy `GenEvent`, weights, worker and slot | Core, Status |
| `Store` | sharded HepMC3 writing/reading, the index, the replay queue | Events |
| `Results` | YODA booking per worker, merging, the scaling contract, atomic writes | Events |
| `ML` | ONNX sessions with per-worker scratch; a named feature schema | Events |
| `Phys` | PDG data, kinematics on `FourVector`, `GenEvent` selectors, jet definitions | Events |
| `Source` | where events come from: Pythia, a store replay, a stream | Events, Store |
| `Module` | the user-module interface and its `dlopen` loader | Results, Phys, ML |
| `Analyzer` | where events go: Rivet, store, modules, the Delphes tee | Results, Store, Module |
| `Run` | wires source to analyzers; chunking, concurrency mode, the summary | Analyzer, Source |

**Why `Events` is separate from `Core`** despite being only 143 lines: it depends on Pythia and
HepMC3, and folding it downward would drag both into the bottom layer and cost the all-off build.
Small is not a defect.

**Why `Phys` and `ML` sit at rank 3** rather than beside `Analyzer`: they are libraries a *user's*
module calls, so they must be visible to `Module` without `Module` reaching upward.

### The two invariants to know before reading the code

**The scaling contract.** Fills carry raw weights in `process`; scaling happens once in `finalize`,
when σ and Σw are known. `Results::Worker` has no `scale()`; `Results::Final` has no `fill()`.

**Concurrency is a property of the analyzer.** Each analyzer answers `Serial`, `Locked` or `Sharded`;
`Run::Loop::decideMode()` asks all of them and decides. The measured cost that made `Locked` worth
having: 92 µs/event locked against 124 µs/event fully serial.

---

## 3. The Python side: twelve packages, no declared rank

| Package | Owns | Lines |
|---|---|---|
| `config` | schema, loading, validation, migration from v1, generated reference | 1,977 |
| `sweep` | quantities, studies, selection (`--study`, `--pin`, `--across`, `--overlay`) | 629 |
| `plan` | expansion to points, identity hashing, the resolved spec, stage chains | 1,150 |
| `adapters` | external generators + the prepare cache | 2,062 |
| `run` | supervisor, transport, signals, journal, `hep bench` | 2,137 |
| `term` | live dashboard, `hep watch`, `hep events` | 1,561 |
| `results` | layout, manifests, comparison statistics, replica merging, `hep clean` | 1,618 |
| `plot` | the page pipeline and two backends | 1,719 |
| `proc` | fits (Minuit2, RooFit, scipy) and derived histograms (RDataFrame, uproot) | 1,822 |
| `store` | `hep store ls\|info\|verify` | 435 |
| `prov` | provenance capture | 461 |
| `env` | `hep doctor`, `hep build`, `hep pdf`, `hep new`, paths | 1,088 |

**This half has no written layering, and it shows**: four module-level import cycles (nine counting
deferred imports), against two on the C++ side. The difference is not discipline — it is that one
half has a rank written down and enforced by a link graph and the other has neither. That is the
single most transferable finding in this document, and the proposals to fix it are in
[post_rework/02_Proposals.md](../post_rework/02_Proposals.md).

The knot is `results/`, which fuses three jobs at three different layers: *where things go*
(`layout`, `manifest`, `skip` — the lowest layer, needed by five packages), *judging numbers*
(`stats`, `compare`, `merge` — near the top), and *housekeeping* (`clean` — needed by nobody).
Fusing the bottom with the top is what forces `results → plot` and `prov → results`.

---

## 4. How a run actually flows

```
hep run CONFIG --study pdf
  │
  ├─ config.load_config()          strict TOML, one error type, `where` + `hint`
  ├─ sweep.select()                study/pins/across/overlay → a Selection
  ├─ plan.build()                  Selection → points, each with an identity hash
  │     └─ identity = f(config, card sha256, point settings)  →  seeds, directory name
  ├─ adapters.<tool>.render()      native point card, base untouched
  ├─ adapters.<tool>.prepare()     integration grids etc., via the prepare cache
  │
  ├─ run.supervisor                spawns Stages by phase
  │     │   phase 0: prepare        (runs alone, first)
  │     │   phase 1: generate + hep-run   (run TOGETHER — a FIFO deadlocks otherwise)
  │     │   phase 2: detector       (a file, so it waits)
  │     │
  │     └─ reads fd 3 ──► term dashboard, journal, per-stage logs
  │
  └─ results/<project>/points/<point>/{analysis.yoda, run.summary.json, provenance.json, logs/}
                      /studies/NN_<study>/{plots/, proc/, manifest}
```

### The things worth understanding

**Identity, not position, decides a seed.** A point's seed derives from its identity hash — the
config, the card, the point's own settings — so the same point in two runs gets the same events and
two different points never collide. Each worker takes a disjoint block, so **thread count changes
the partitioning of a run, not its statistics** (D21). The old `seed + (i-1)*step` scheme could not
promise either.

**Re-running is free.** A point whose identity and inputs are unchanged is skipped.

**Phase is the subtle field.** Stages in one phase run *together*; a later phase waits. A generator
streaming into a FIFO must overlap with the `hep-run` reading it or they deadlock; a generator
writing a file (MadGraph's LHE) must finish first. `phase = -1` derives it from the role.

**An adapter never spawns anything.** It returns a `Stage` — a dataclass of `argv`, `env`, `cwd`,
`log`, `parser`, `timeout`, `produces`, `writes` — and the supervisor runs it. That is what makes
stages inspectable by `hep plan` before anything starts, and testable without running a generator.

---

## 5. Output: files, immutably, in one place

```
results/<project>/
  points/<point>/     analysis.yoda, run.summary.json, provenance.json, logs/, events/
  studies/NN_<study>/ plots/, proc/, manifest
```

- **A partial result has a different name** — `analysis.partial.yoda`, `.part` — with atomic renames
  everywhere. You cannot mistake one for the other (D22).
- **Provenance sits next to the numbers**: the resolved config, the card's hash, every tool's
  version, host and git revision.
- **The serial prefix is on the study directory only** (`studies/03_pdf/`), never in a point path,
  so a point's location is a function of its identity alone (Q3).

### The plotting pipeline is immutable files

Nothing mutates its input. Each stage writes a new YODA into a work directory the caller owns:

```
points_of → curves_for → unify → void_bins → data.overlay → fits.overlay → auto_range → backend
            workdir/unified/   workdir/voided/   …_data.yoda   fits.yoda   auto_range.plot
```

That is why the port could be compared bin-for-bin against the tool it replaced, why `--keep` is
useful, and why `proc.yoda` is never edited — the fits are *copied and renamed* onto their targets.

**The order is load-bearing**: voiding before the data overlay so the reference aligns against the
binning actually drawn; auto-range last so it sees both curves and data.

---

## 6. Extension points, and what each costs

| To add | Write | Cost |
|---|---|---|
| A Rivet analysis | `analyses/<Project>/<name>.cc` (+ `.info`, `.plot`) | glob picks it up; `hep build` |
| A C++ module | `modules/<Project>/<Name>.cc` + `HEKIT_MODULE(…)` | glob; `dlopen`'d, never relinks `hep-run` |
| A generator | `adapters/<tool>.py` with five functions + `register()` | FIFO wiring, event counting, cache, supervision all inherited |
| An analyzer | `utils/Analyzer/<Name>.hh` answering `concurrency()` | must declare its own thread-safety |
| A status message | a `Status::Kind` | old readers log-and-ignore it |
| A command | an entry in `cli.COMMANDS` | lazily imported, so `hep --help` stays fast |
| A fit backend | `proc/backends/<name>.py` | `ORDER` decides preference; falls back automatically |
| A ROOT view of a point | `[proc.export]` in the config | derived from `analysis.yoda`; `hep-run` still links no ROOT |

The property these share: **adding one thing touches one file**. Where that is not true — five
commands hand-rolling the same `load_config → select_points → build → Layout.of` preamble, already
drifted — the audit found it and named it P4.

---

## 7. Where the design was wrong

Eleven places where building it changed it, listed in full at
[rework/README.md](../rework/README.md#where-the-design-was-wrong). The three that changed the
*architecture* rather than a detail:

**Rivet analyses cannot be sharded** (`00/B31`). FastJet keeps clustering state in process-wide
statics; a race changes the jets rather than crashing. This is why concurrency became a property of
the analyzer instead of a global mode, and why `Module::Base::threadSafe()` exists.

**An analyzer exception would have called `std::terminate`** (`00/B32`). `PythiaParallel` runs the
callback on worker threads in *both* modes, so a throw unwound through `std::thread`. Both sources
now catch at the thread boundary and rethrow on the main thread.

**Delphes cannot read a FIFO.** It sizes its input and skips anything of length zero, which a FIFO
always is. That forced the three-phase stage model — a detector stage reads a regular file in a
later phase — rather than the uniform streaming assumed by the design.

Each of these was found by *running the thing*, not by reading it. See
[06_Lessons.md](06_Lessons.md).
