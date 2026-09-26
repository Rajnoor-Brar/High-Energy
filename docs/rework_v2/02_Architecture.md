# 02 — Architecture

How v2 works, and why its boundaries are where they are. The brief is
[00_Brief.md](00_Brief.md); why v1's code is not reused is [01_Assessment.md](01_Assessment.md).

---

## 1. The model in one picture

```
hep run PhotoProduction/eic energy_pdf                (utils/Env/hep → utils/Env/run)
  │
  ├─ load     configs/PhotoProduction/eic.toml  +  utils/Env/master.toml (quantity → tool maps)
  ├─ resolve  [run.energy_pdf]:  sweeps, plot_points, tools, static
  ├─ expand   sweeps = ["energies", "pdf"]  →  16 points  (grid of axes; entangled groups zip)
  ├─ plan     per point: rendered cards, argv, paths, identity, seeds; checks (04 §10)
  │
  ├─ for each point ────────────────────────────────────────────────────────────────────────────┐
  │    skip?     results/…/<point>/.complete holds this identity → next point                    │
  │    prelim    mkfifo output/…/<point>/events.hepmc; touch agreed files; run prelim commands   │
  │    execute   tools = [["pythia", "rivet"], "yd2rt"]                                           │
  │                 group 1: App_Pythia ══FIFO══► rivet          (together, one process group)    │
  │                 group 2: App_yd2rt  photo.yoda → photo.root   (after group 1 succeeded)       │
  │    check     rivet's event count == App_Pythia's sidecar "written"                          │
  │    record    provenance.json, then .complete (last)                                         │
  └──────────────────────────────────────────────────────────────────────────────────────────┘
  │
  ├─ post     tools that need every point, handed points.json
  └─ plot     4 pages (one per energy) × each histogram, PDFs as curves → build/Paint.exe
                → results/PhotoProduction/03_eic/03_energy_pdf/plots/
```

**Every box is a process or a file.** No tool runs inside another, the runner links no physics
library, and no tool reads the run TOML. The runner's whole job is: *decide, write the files each
tool reads, start the processes in order, watch them, record what happened.*

---

## 2. Vocabulary

| Word | Means |
|---|---|
| **run** | one TOML file under `configs/<project>/` (`[run]`) |
| **configuration** | a named recipe inside a run (`[run.<name>]`): sweeps, tools, event count |
| **point** | one combination of swept values: one chain of processes, one output directory |
| **quantity** | a named thing that can be swept or held static (`[quantities.<q>]`) |
| **tool** | one process in the chain, configured by `[tools.<tag>]` |
| **group** | tools that run together (an inner list in `tools`) |
| **page** | one plot: one cell of the `plot_points` grid, with the other swept quantities as curves |

---

## 3. Components

```
utils/
├── Env/                           ─── shell and Python ───
│   ├── hep_env.sh                 environment (load_hep, quit, hep_cd …), from v1's env/
│   ├── hep                        the `hep` command: run | watch | build
│   ├── run                        entry script → runner.cli
│   ├── flags.sh                   writes build/flags.mk
│   ├── master.toml                quantity → tool maps (04 §2)
│   ├── runner/                    the runner: one flat package (below)
│   └── pythia/ rivet/ yd2rt/ module/ custom/ paint/ yoda/ delphes/ herwig/ sherpa/ whizard/ madgraph/
│                                  tool folders: tool.toml (+ render.py, filters.toml)
├── Status.hh                      ─── C++ ─── JSON-lines status on $HEP_STATUS_FD (~120 lines)
├── Module.hh                      the kit for modules/<P>/*.cc programs (~200 lines)
├── App_Pythia.cc                  the standard Pythia tool
├── App_yd2rt.cc                   YODA → ROOT
└── Apps/Paint/                    the ROOT plotting app
```

### The runner: `utils/Env/runner/`

**One flat package** of about 12 modules. There are no sub-packages, because at ~2,000 lines a
module is the right unit.

| Rank | Module | Owns | ~Lines |
|---|---|---|---|
| 0 | `errors.py`, `paths.py` | `HepError(msg, where, hint)`, did-you-mean; repo root by markers; path resolution rules (03 §2) | 150 |
| 1 | `config.py` | load the TOML, then a strict schema check (unknown keys, types, `where`/`hint`) | 300 |
| 1 | `quantities.py` | master overlay, static values, consumer resolution (04 §6) | 200 |
| 1 | `sweep.py` | points from `sweeps` (grid and zip), point names, pages from `plot_points` | 150 |
| 2 | `tools.py` | load the tool folders; render point cards; build argv from placeholders; extract custom configs | 300 |
| 3 | `execute.py` | prelim, groups as process groups, stall and failure handling, the count check | 350 |
| 3 | `status.py` | read `$HEP_STATUS_FD` pipes; apply `filters.toml`; append to `status.jsonl` | 150 |
| 3 | `record.py` | identity, seeds, skip, provenance, `points.json` | 150 |
| 4 | `watch.py` | the live view (rich if available, plain otherwise); `hep watch` | 200 |
| 4 | `plot.py` | page configs → Paint, or the backend in `utils/Env/<backend>/backend.py` | 150 |
| 4 | `post.py` | the post stage, planned as one more point (04 §4.3) | 60 |
| 5 | `cli.py` | `argparse`: `run`, `watch`; `--plan`, `--points`, `--set`, `--rerun`, `--only` | 100 |

A module may import only from its own rank or a lower one, and the import graph has no cycles.
`tests/runner/test_imports.py` checks both in about 40 lines. It is the one piece of v1's layering lesson worth its cost at this size.

**A tool plugin** (`utils/Env/<tool>/render.py`, or a plot backend's `backend.py`) may import
`errors`, `paths` and `quantities` only, and never another plugin.

### The C++

**No libraries, no namespaces hierarchy** (V7). There are two headers and three apps:

| File | Is | Links |
|---|---|---|
| `Status.hh` | `Status::Reporter`: JSON lines to `$HEP_STATUS_FD`, or plain stderr if unset; a heartbeat thread; drop-on-full | nothing |
| `Module.hh` | for project programs: open a HepMC input (file, FIFO, gz, zst), iterate events with weights, running ΣW, σ at the end (sidecar or last event), read the config TOML, write a ROOT or YODA output atomically | HepMC3, toml++, and ROOT or YODA |
| `App_Pythia.cc` | [05 §4](05_Tools.md#4-apppythia-utilsapppythiacc) | Pythia8, HepMC3 |
| `App_yd2rt.cc` | [05 §6](05_Tools.md#6-appyd2rt-utilsappyd2rtcc) | YODA, ROOT |
| `Apps/Paint/` | [05 §7](05_Tools.md#7-paint) | ROOT, toml++ |

The v1 house rules still hold for the little that exists: PascalCase namespaces checked against the
toolchain (X11's `#define Status int` is guarded), `camelCase` functions, and no `using namespace`
of external libraries at namespace scope.

---

## 4. Tool categories → what the runner does

The brief's ten categories are informal. They matter to the runner only through **when a tool runs
and what it reads and writes**, which its `tool.toml` declares
([05 §1](05_Tools.md#1-the-tool-folder-contract)).

| # | Category | Examples | Runner role |
|---|---|---|---|
| 1 | Providers | LHAPDF, FeynRules, SARAH | **plan-time checks** (a PDF set named by a quantity is installed; a UFO model exists). No process. |
| 2 | Bridges | HepMC3, LHE | **formats at tool boundaries**: the `[prelim]` FIFOs and files. They are also libraries the apps link. |
| 3 | Process generators | MadGraph, Whizard | per-point tool, file output, with a **prepare cache** keyed by the card |
| 4 | Event generators | App_Pythia, Herwig, Sherpa | per-point tool → HepMC; the usual head of a chain |
| 5 | Detector simulators | Delphes, Geant4 | per-point tool with `streamable = false`: it reads a **file** |
| 6 | Analysis algorithms | FastJet, ROOT libraries | **build flags only** (`// requires: fastjet`); never a runner tool |
| 7 | Analysis applications | Rivet, CMSSW; our module programs | per-point tool → YODA/ROOT |
| 8 | Visualisation | YODA, ROOT | the `yd2rt` tool, and the `[plot]` stage driving Paint |
| 9 | Statistics | RooFit, RooStats, uproot, ML | custom tools, per point or in `post`; no built-in fitter (V4) |
| 10 | Database | xrootd, rucio | not in v2. When needed, it becomes a `[prelim]` fetch command. |

---

## 5. Connections: how data moves between tools

**Connections are explicit.** A tool table names what it reads (`input`) and writes (`output_file`),
using `[prelim]` names or paths. The runner never guesses that "the HepMC from the previous tool" is
meant.

```toml
[prelim]
fifo = ["events.hepmc"]

[tools.pythia]
tool        = "pythia"
output_file = "events.hepmc"      # writes into the FIFO

[tools.rivet]
tool        = "rivet"
input       = "events.hepmc"      # reads the same FIFO
output_file = "photo.yoda"
```

**Rules**, checked at plan time, before any process starts:

| Rule | Why |
|---|---|
| A **FIFO** connects tools **in the same group** only. | A FIFO needs both ends open at once. A reader in a later group would leave the writer blocked for ever (L8). |
| Between groups, the interface is a **regular file**. | The earlier group has finished, so the file is complete. |
| A FIFO has exactly **one reader**. Fan-out is a list-valued `output_file` on the producer (V16). | Two readers split the stream, each getting some of the events. |
| No FIFO into a tool with `streamable = false`. | Delphes skips zero-length input, which a FIFO always is (L11). |
| Every `input` is produced by an earlier or same-group tool, a `[prelim]` entry, or an existing path. | This removes the brief's "inexistence error" risk. |
| Every `output_file` has exactly one writer. | Two writers are a race. |

**Standard configurations for custom tools.** Connections move *data*; exports move
*configuration*. A custom or module tool may set `pythia_cmnd = true` (or `rivet_analyses`,
`herwig_run`, …). The runner then renders that standard tool's point card as usual, even if the
tool is not in the chain, and hands its absolute path to the custom tool under `[standard.<key>]`
in its config ([04 §7.3](04_Config.md#73-standard-configurations-for-custom-tools)). This is how an
**integrated run** works: one program running Pythia and Rivet in-process, with the runner's
sweeps, quantities and identity seeds. There is no FIFO between them, so the connection rules above
have nothing to check.

---

## 6. Scopes

| Scope | What runs there | Configured by |
|---|---|---|
| **per run** (once) | load, expand, plan, provider checks | `[run]`, `[master]` |
| **per point** | the `[prelim]` actions, then the `tools` groups | `[run.<cfg>].tools`, `[prelim]` |
| **post** (once, after all points) | seed-replica merges (`rivet-merge`), fits, any statistics | `[run.<cfg>].post` (V15) |
| **plot** (once, last) | one page per `plot_points` cell and histogram | `[plot]` |

A post tool gets `points.json`: every point's quantity values, tags and product paths. It never has
to know the directory layout.

**Points run one after another**, each with the configuration's `threads`. Running several points
at once changes only the scheduler, and waits until a sweep's wall time is dominated by the number
of points rather than by events per point.

---

## 7. Identity, seeds and skip

**Identity is per point** (V9):

```
identity(point) = sha256( for each tool in the chain:
                              tool name, tool binary sha256, rendered card text, argv,
                              extracted config text (which includes any exported cards' text),
                              sha256 of every external input;
                          threads, event_count )
```

- **Seeds** come from the **generator's** identity (P4 S1): the identity parts of the
  `produces_events` steps (their card lines without comments, base cards, binary, replica values),
  with threads and events, but not the rest of the chain, a detector simulation included. `base = 1 + int(basis[:12], 16) mod (9·10⁸ − threads)`,
  and the thread seeds are `base … base + threads − 1`. That is disjoint within a point and in
  Pythia's range (L4). Across the plan, the seed blocks are checked for overlap, and a clash is
  moved up by `threads`, so two points of one configuration never share events. Across
  configurations, **the same generator setup gives the same events**: the chain's `single` point
  and an integrated program's `inproc` point (04 §7.3) can be compared bin for bin. Until P4 S1 the
  basis was the whole point's identity; the identity carries the rule (`"seeds": "generator"`), so
  the change reran every point once. For Pythia, the card always gets `Random:setSeed = on` with `Random:seed = base`, and,
  at threads > 1, `Parallelism:seeds = {base, …}` as well. A serial `Pythia8::Pythia` in an
  integrated program (04 §7.3) and a `PythiaParallel` both read a seed meant for them; neither ever
  falls back to the base card's time-based `Random:seed = 0`.
  **Order:** the identity is hashed from the cards *before* seeds are written into them.
  The seed lines are then derived and appended, so there is no circularity. Consequences (v1's
  D21, kept): the same point gets the same events in every run, two points never collide, and the
  thread count changes the partition but not the statistics.
- **Skip-unchanged.** `results/…/<point>/.complete` holds the identity. If it matches, the point is
  skipped. `--rerun` ignores it. `.complete` is written **last**, after the count check, so a
  half-written point is never skipped.
- **No sharing between points.** Every point runs its whole chain. A sweep of a Rivet analysis
  option therefore regenerates the events for each value. v1 avoided that by running all the
  variants in one Rivet pass; v2 gives it up for simplicity (V9).
  - **Workaround available today:** keep the events as a file (`[prelim] files`), then run an
    analysis-only configuration whose Rivet reads `./output/…/events.hepmc`.
  - **Trigger to revisit:** the first option sweep where regeneration costs more than the user is
    willing to wait. The design is then per-step identity, which the first draft of this plan
    described, preserved in git history.

---

## 8. Status and the watch view

| Source | Channel | Parsed by |
|---|---|---|
| Our apps and module programs | JSON lines on the fd in `$HEP_STATUS_FD` (via `Status.hh`) | `status.py` |
| Everyone else (rivet, Herwig, Sherpa, Delphes …) | their stdout/stderr | `utils/Env/<tool>/filters.toml`: regex → progress, phase, warn, error, ignore |

- **stdout is never the status channel.** It may carry HepMC, and it always carries chatter. Every
  process's output goes to `output/…/<point>/logs/<tag>.log`.
- **A filter never fails a run.** A regex that stops matching costs a progress bar, not a result.
- **The watch view** is one line per running tool (point, tool, progress, rate, ETA, last warning)
  and one line per finished point. `hep watch` reads `status.jsonl` from another terminal.

**Message kinds.** The envelope is `{"t": <unix time>, "k": <kind>, …}`. An unknown kind is kept
and ignored, so the set can grow.

| Kind | Fields |
|---|---|
| `phase` | `phase`, `detail` |
| `progress` | `done`, `total`, `rate` |
| `xsec` | `value_pb`, `err_pb`, `final` |
| `log` | `level`, `msg` |
| `summary` | tool-defined (counts, σ, outputs) |
| `heartbeat` | — |

---

## 9. Failure handling

A FIFO chain has two failure modes a single process does not. Both are handled by construction.

**Deadlock at open (L8).**

- Each group runs as **one process group**. The first nonzero exit kills the rest of the group
  after a short grace period.
- **Stall detection**: no output, status or heartbeat for `stall_after` seconds counts as a failure.
- FIFOs are created fresh, per point, per attempt.

**A partial result that looks complete.** If the generator dies mid-stream, Rivet sees end of file,
finalises and exits 0 with a plausible YODA. So:

- every event producer writes a **sidecar** (`<output>.json`: written, σ, error, ΣW, seeds);
- every event consumer's count is **checked against it** (Rivet: `/RAW/_EVTCOUNT`, L7);
- a mismatch renames the product `*.partial.*`, writes no `.complete`, and fails the point.

**Attribution.** When several processes die together, the report names the one that caused it,
such as Pythia's init failure rather than Rivet's broken pipe. The rule is simple: the first
process to exit nonzero *before* any signal was sent is the cause.

**Ctrl-C** stops the current group (SIGINT, then SIGTERM, then SIGKILL), marks the point partial,
and stops. Rerunning the same command resumes, because finished points are skipped.

**Exit codes for our apps:**

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | config or card |
| 2 | usage |
| 3 | init |
| 4 | input |
| 5 | output |
| 6 | stopped, with partials written |
| 7 | stalled |
| 70 | internal |

The runner exits `0` when everything succeeded, `1` when a point failed, and `2` on a config error
before anything ran.

---

## 10. Provenance

`results/…/<point>/provenance.json` (V14) holds:

- the resolved point (quantity values and tags);
- per tool: the rendered card's sha256, argv, the binary's path, sha256 and version;
- the identity and seeds;
- the host, git revision and dirty flag, and the start and end times.

---

## 11. What v2 deliberately refuses

| Refused | Why |
|---|---|
| A general DAG/workflow engine | `tools` is a **sequence of groups**. The connection rules (§5) only check. |
| Physics in TOML | a quantity renders an override into the native card; the card stays the physics |
| An in-process event loop *in the framework* | V2. A user program may run one; it gets its cards through exports (§5). |
| Inferring connections, units, or which tool a quantity is for | every silent-inference defect in v1 (`00/B5`, `00/B14`, `00/B40`) had this shape |
| Built-in statistics | V4; a fit is a custom tool in `post` |
| Sharing events between points | V9, deferred with a trigger (§7) |
| A C++ library layer | V7; a module links what it needs |
