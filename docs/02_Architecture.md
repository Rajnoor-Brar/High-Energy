# 02 — Architecture

How the framework works, and why its boundaries are where they are. The principles behind it are
[01_Philosophy.md](01_Philosophy.md); every key named here is in
[04_Config_Reference.md](04_Config_Reference.md), every tool in [05_Tools_Reference.md](05_Tools_Reference.md).

---

## 1. The model in one picture

```
hep run PhotoProduction/eic energy_pdf                      utils/Env/hep → utils/Env/run → runner.cli
  │
  ├─ load     configs/PhotoProduction/eic.toml  (+ utils/Env/master.toml: quantity → tool maps)
  ├─ resolve  [run.energy_pdf]: sweeps, plot_points, tools, static, prelim
  ├─ expand   sweeps = ["energies", "pdf"]  →  16 points   (a grid of axes; entangled groups zip)
  ├─ plan     per point: cards, config files, argv, connections, identity, seeds; every check (C1–C13)
  │
  ├─ pre      tools run once before every point (their products are inputs of every point)
  ├─ for each point ──────────────────────────────────────────────────────────────────────────────┐
  │    skip?     output/…/<point>/.complete holds this identity  →  next point                      │
  │    prelim    mkfifo events.hepmc, touch agreed files, run prelim commands                       │
  │    prepare   cached slow steps (Sherpa's integration, Herwig's read), once per card             │
  │    group 1   App_Pythia ══FIFO══► rivet          together, one process group each, supervised   │
  │    settle    rivet's event count == App_Pythia's sidecar "written"; photo.partial.yoda → photo.yoda │
  │    group 2   App_yd2rt  photo.yoda → photo.root   (only after group 1 settled)                   │
  │    record    provenance.json, then .complete (last)                                            │
  └─────────────────────────────────────────────────────────────────────────────────────────────┘
  ├─ post     tools run once after every point, handed every point's products and points.json
  └─ plot     the sweep merged into plots/root/energy_pdf.root; 4 pages (one per energy) per histogram,
              the PDFs as curves, drawn by build/Paint.exe (and/or rivet-mkhtml)
```

**Every box is a process or a file.** No tool runs inside another, the runner links no physics
library, and no tool reads the run TOML. The runner's whole job is: *decide, write the files each
tool reads, start the processes in order, watch them, check what they made, record what happened.*

---

## 2. Vocabulary

Seven words carry the design; the full glossary is [07 §10](07_Record.md#10-glossary).

| Word | Means |
|---|---|
| **run** | one TOML under `configs/<project>/` |
| **configuration** | a named recipe inside a run (`[run.<name>]`): sweeps, tools, events, threads |
| **point** | one combination of swept values: one chain of processes, one output directory |
| **quantity** | a named value that can be swept or held static (`[quantities.<q>]`) |
| **tool** | one process in the chain (`[tools.<tag>]`), of a kind a tool folder describes |
| **group** | tools that run together, connected by FIFOs (an inner list in `tools`) |
| **page** | one plot of one histogram: a cell of the `plot_points` grid, the other swept quantities as curves |

---

## 3. Components

```
configs/<Project>/            run TOMLs and native base cards (the physics)
modules/<Project>/            your C++: programs (<Name>.cc) and Rivet plugins (Rivet/<x>.cc, Rivet_<x>.cc)
utils/
├── Env/                      ─── shell and Python ───
│   ├── hep                   the `hep` command: run | plot | watch → the runner; build → make
│   ├── run                   the runner's entry script
│   ├── hep_env.sh            the shell environment (load_hep, quit, hep_cd, hep_status, …)
│   ├── flags.sh              probes each library's *-config once → build/flags.mk
│   ├── master.toml           how each standard tool consumes named quantities
│   ├── runner/               the runner: one flat Python package (§3.1)
│   └── <tool>/               one folder per standard tool: tool.toml (+ render.py, filters.toml)
├── Status.hh                 ─── C++ ─── the status protocol (JSON lines on $HEP_STATUS_FD)
├── Module.hh                 the kit for module programs
├── App_Pythia.cc             the standard Pythia tool
├── App_yd2rt.cc              YODA → ROOT, and a sweep into one file
└── Apps/Paint/               the ROOT plotting app (+ base.toml, the style)
build/                        everything compiled; output/ technical files; results/ products
```

### 3.1 The runner

**One flat package**, `utils/Env/runner/`, with a declared rank per module. A module imports only
from its own rank or a lower one, and the import graph has no cycles; `tests/runner/test_imports.py`
enforces both. (v1's lesson: the half of v1 whose layering was written down and checked held; the
half whose layering was not had nine cycles.)

| Rank | Module | Owns |
|---|---|---|
| 0 | `errors.py` | `HepError(message, where, hint)`, `did_you_mean` |
| 0 | `paths.py` | the repository root (by markers, or `$HEKIT_ROOT`), `output/` and `results/` roots, the path rules (04 §2) |
| 1 | `config.py` | load the TOML, `--set`, the strict schema check; the typed model (`RunConfig`, `Configuration`, `Tool`, `Quantity`) |
| 1 | `quantities.py` | the master TOML, static values and selectors, who consumes what (C7), provider checks (C10) |
| 1 | `sweep.py` | points from `sweeps` (grid and zip), point names, pages, `--points` |
| 2 | `tools.py` | the tool folders; per point: interfaces, connections (C6), cards, configs, exports, prepare keys, argv; seeds last |
| 3 | `execute.py` | `[prelim]`, prepare steps, groups as supervised process groups, the count checks, settling products |
| 3 | `status.py` | the status pipes, the filter rules, the journal |
| 3 | `record.py` | identity, seeds, skip, provenance, `points.json` |
| 4 | `watch.py` | the live and plain views, `hep watch` |
| 4 | `plot.py` | the plot stage: the merged sweep, page configs, the style layers, Paint and the other backends; `hep plot` on files |
| 4 | `post.py` | the pre and post stages |
| 5 | `cli.py` | `argparse`: `run`, `plot`, `watch`; the order of events |

A **tool plugin** (`utils/Env/<tool>/render.py`, a plot backend's `backend.py`) may import only
`errors`, `paths` and `quantities`, and never another plugin. The runner is standard library only,
plus `tomli_w` for writing TOML and, lazily, `yaml` (Sherpa's plugin) and `uproot` (the Delphes
count); `rich` for the live view is optional.

### 3.2 The C++

No libraries and no namespace hierarchy (V7): two headers and three apps, each linking only what
its `// requires:` line names.

| File | Is | Links |
|---|---|---|
| `Status.hh` | `Status::Reporter`: JSON lines to `$HEP_STATUS_FD`, or plain stderr; heartbeat; drop-on-full | nothing |
| `Module.hh` | the kit for module programs: argv, the config, HepMC input (file or FIFO, gz, zst), ΣW, σ, `RootOut`, the report | HepMC3, toml++, (ROOT) |
| `App_Pythia.cc` | Pythia → HepMC3, threaded, σ combined, sidecar | Pythia 8, HepMC3, zstd, zlib |
| `App_yd2rt.cc` | YODA → ROOT; `--merge` | YODA, ROOT |
| `Apps/Paint/` | one page per call, from a page TOML and the style | ROOT, toml++ |

---

## 4. Tool categories and what the runner does with each

The brief's ten categories are informal. They matter to the runner only through **when a tool runs
and what it reads and writes**, which its tool folder declares.

| # | Category | Examples | Runner role |
|---|---|---|---|
| 1 | Providers | LHAPDF, FeynRules, SARAH | **plan-time checks**: a PDF set a quantity names must be installed (C10). No process. |
| 2 | Bridges | HepMC3, LHE | the **formats at tool boundaries**: `[prelim]` FIFOs and files; libraries the apps link |
| 3 | Process generators | MadGraph, Whizard | per-point tools writing a file, with a **prepare cache** keyed by the card |
| 4 | Event generators | App_Pythia, Herwig, Sherpa | per-point tools → HepMC; the usual head of a chain; `produces_events` (their identity is the seed basis) |
| 5 | Detector simulators | Delphes, Geant4 | Delphes: a tool reading a **file** (not streamable). Geant4 has no command line: a simulation is a module program with `// requires: geant4` |
| 6 | Analysis algorithms | FastJet, ROOT libraries | build flags only (`// requires: fastjet`) |
| 7 | Analysis applications | Rivet; module programs | per-point tools → YODA/ROOT, **count-checked** against the producer |
| 8 | Visualisation | YODA, ROOT | `yd2rt`, `plotmerge`, and the plot stage (Paint, rivet-mkhtml) |
| 9 | Statistics | RooFit, pyhf, uproot, ML | custom tools, per point or in `post`; no built-in fitter (V4) |
| 10 | Database | xrootd, rucio | none yet; a fetch would be a `[prelim]` command or a `pre` tool |

---

## 5. A run, from command to pages

`runner.cli.run_one` does this for one run, in order. Under `[run].sweep_runs` (V38, 04 §4.1)
`cmd_run` first plans every swept configuration (a config error anywhere exits 2 with nothing run),
then does all of it for each in turn, after a `run NN - <title> -` line: each is a run of its own,
planned again at its turn, and a stop starts no more.

1. **Load** the run TOML, apply `--set` to the raw table, and check the file (C1–C5, C12): every
   section, key and type; sweeps, plot_points and tool lists. `threads = 0` becomes a number.
2. **Expand** the configuration's points (04 §5.1): the grid of the axes, names from the tags;
   unique names (C11); then `--points` picks which to run.
3. **Plan the pre stage**, if any, then **every point** (`tools.plan_point`): the active quantities
   and their consumers (C7, C8, C10); the interfaces from `[prelim]`, outputs and inputs, and the
   connection rules (C6); each tool's card lines, config file, exports (C13), prepare key and argv.
   Nothing is spawned and nothing is written yet.
4. **Identity** of every point (§8), then **seeds**, disjoint across the plan, then the seed lines
   written into the cards (`tools.finalise`). Then the post stage's plan and the plot checks.
5. With `--plan`: print it all and stop.
6. **Run**: the pre stage (skipped when complete; its failure stops everything); every point that is
   not complete, one after another (§5.1); `points.json`; the post stage (only when every point is
   complete); the plot stage (§13).

### 5.1 One point

`execute.run_point`:

1. **Prepare the directories**: write the cards and configs, delete an old `.complete` (an attempt is
   under way) and any product left by an earlier attempt, make the FIFOs fresh, touch the agreed
   files, run the `[prelim]` commands.
2. **Prepare steps** (§9): each tool's cached slow step, if it has one and it is not cached.
3. **The groups, in order.** Each tool of a group starts at once, each in its own process group,
   with stdout and stderr to its log and, for a standard-status tool, a status pipe. The supervisor
   polls them (§11). After a group succeeds it **settles**: the runner writes the sidecars of
   generators that always make what they are asked for, runs the count checks, and renames the
   group's products from `*.partial.*` to their final names, so the next group can read them.
4. **Record**: FIFOs removed, `provenance.json` written, then `.complete` holding the identity,
   **last**.

A failure anywhere stops the point: its products keep their partial names, no `.complete` is
written, and the run goes on to the next point.

---

## 6. Connections

**Connections are explicit.** A tool table names what it reads (`input`) and writes
(`output_file`), by `[prelim]` names or paths; the runner never guesses that "the HepMC of the
previous tool" is meant.

| Interface | Made by | Lives in | Connects |
|---|---|---|---|
| FIFO (`[prelim] fifo`) | the runner, fresh per attempt; removed when the point ends | the point's output dir | a writer and **one** reader **in the same group** |
| file (`[prelim] files`) | the runner (empty), then its writer; kept | the point's output dir | a writer and readers **in later groups** |
| product (any other `output_file`) | its tool, as `*.partial.*`, renamed after the checks | the point's results dir | readers in later groups; the plot stage; post tools |
| pre product | a pre tool | `…/<cfg>/pre/` | every point |
| every point's product | the points | their results dirs | a post tool (`input` naming the product) |

**The rules** (C6), checked at plan time:

| Rule | Why |
|---|---|
| A FIFO connects tools in the same group only | a FIFO needs both ends open at once: a reader in a later group leaves the writer blocked for ever (L8) |
| Between groups, the interface is a regular file | the earlier group has finished, so the file is complete |
| A FIFO has exactly one reader; fan-out is a list-valued `output_file` on the producer (V16) | two readers would split the stream, each getting some events |
| A **sharded** tool (`shards = K`) reads from a producer that can **deal** | the runner replaces its FIFO by K, the producer sends each event to one of them, and a merge step joins the K products (V31, §6.1) |
| No FIFO into a tool that is not `streamable` | Delphes skips zero-length input, which a FIFO always is (L11) |
| Every input is produced earlier or in the same group, is a `[prelim]` file, or already exists | the brief's "inexistence error" cannot happen |
| Every output has exactly one writer | two writers race |

### 6.1 Sharding: one tool as K processes

A Rivet process uses one core, and in a Pythia → Rivet chain it sets the pace whatever Pythia's
threads (measured at ~1,500 events/s for ZEUS_2012). `shards = K` on the table (V31) is rewritten,
for each point, before anything else is planned:

```
[["pythia", "rivet"], "yd2rt"]         with [tools.rivet] shards = 3
  → [["pythia", "rivet.1", "rivet.2", "rivet.3"], ["rivet.merge"], ["yd2rt"]]
     pythia writes  events.s1.hepmc+events.s2.hepmc+events.s3.hepmc   (a deal group: one each)
     rivet.<i>      reads events.s<i>.hepmc, writes output/…/shards/photo.s<i>.yoda
     rivet.merge    rivet-merge -e the three → results/…/photo.yoda
```

Every rule of this section then applies to the rewritten chain as to any other. Each shard is
count-checked against its own share of the producer's sidecar. The generator's seeds follow its
cards, not its argv, so the events are the same as unsharded (§8). The shards' products are
technical: not the point's products, not in `points.json`, not drawn.

**Standard configurations** move *configuration*, where connections move *data*: a custom or module
tool may ask for a standard tool's rendered card or values (`pythia_cmnd = true`), and that tool is
then configured without being run (04 §9.4). That is how an **integrated program**, one process
running Pythia and Rivet, gets the chain's card and seeds.

---

## 7. Scopes

| Scope | What runs there | Configured by |
|---|---|---|
| per run, once | load, expand, plan, checks | `[run]`, `[master]` |
| **pre**, once before every point | a download, a shared build: products every point may name; its identity is in theirs | `[run.<cfg>].pre` |
| **per point** | `[prelim]`, the prepare steps, then the `tools` groups | `[run.<cfg>].tools`, `[prelim]` |
| **post**, once after every point | seed-replica merges, the sweep in one file, fits, any statistics; handed `points.json` and every point's product | `[run.<cfg>].post` |
| **plot**, once, last | one page per `plot_points` cell and histogram | `[plot]` |

Points run **one after another**, each with the configuration's `threads`. A post stage runs only
when every point is complete, because a merge or a fit over a subset would look like the whole.

---

## 8. Identity, seeds and skip

**The identity of a point** is the sha256 of everything that decides its result:

```
identity = sha256( threads, events, the groups, [prelim],
                   for every rendered tool: its tag, tool, binary path and sha256, card lines (without
                     lines that repeat the base card's own value), base cards' sha256, flags, analysis
                     options, config values, analyses (and each plugin's sha256), the extracted config,
                     exported tools' identities, argv (with the point's directories as {out}/{res}),
                     the prepare key, replica values;
                   the seed rule; for pre and post, the identities upstream )
```

It is computed from the cards **before** seeds are written into them; the seeds are then derived
and appended, so there is no circularity.

**Seeds follow the generator** (V22). The *seed basis* is the identity of the event-producing steps
alone (their cards without comments, base cards, binaries, replica values) with threads and events;
a detector simulation or an analysis downstream does not move it.

```
base  = 1 + int(basis[:12], 16) mod (9·10⁸ − threads)        threads use base … base + threads − 1
```

Blocks are checked for overlap across the whole plan, and a clash moves up by `threads` (L4), so two
points of one plan never share events. Across configurations, **the same generator set-up gives the
same events**: eic's `single` point and its integrated `inproc` point can be compared bin for bin.
Consequences (v1's D21, kept): the same point gets the same events in every run, and the thread
count changes the partition, not the statistics. For Pythia the card always gets `Random:setSeed =
on`, `Random:seed = base`, and at threads > 1 `Parallelism:seeds = {base, …}`; other tools get their
own seed line or flag. The runner's seed lines come after the base card, so a seed set in the card
(`Random:seed = 0`) never counts: `seed_type` is how to choose.

**`seed_type`** (V39; `[run]` or `[run.<cfg>]`, 04 §4) chooses the base; the threads always use
base … base + threads − 1:

| `seed_type` | base | in the identity |
|---|---|---|
| `"identity"` (default) | from the seed basis, as above | `"generator"`, what every identity said before V39 |
| `"manual"` | exactly the value of a quantity targeting `<tool>/seed`, else `manual_seed`: every point shares it | `["manual", base]` |
| `"random"` | drawn from the OS when the point runs (`--rerun` draws again); a complete point keeps the seed its `provenance.json` records | `"random"` |

Under `"manual"`, points whose physics differs may share a seed. Two points with one generator set-up
(the seed basis without the seed value) whose blocks overlap without being equal are refused: they
would repeat some of each other's events. The pre, post and combined stages keep the identity rule.
Every mode records the seed in `provenance.json` and `points.json`, so any point can be repeated
with `seed_type = "manual"` and its seed.

**Skip-unchanged.** A point is complete when `output/…/<point>/.complete` holds its identity; it is
then skipped (`--rerun` runs it anyway). `.complete` is written last, after the count checks, so a
half-written point is never skipped. Change anything the identity covers and the points it affects
run again; change a serial and the location is new.

**No sharing between points** (V9): every point runs its whole chain, so a sweep of a Rivet
analysis option regenerates the events for each value. The way around it today is to keep the events
as a `[prelim]` file in one configuration and analyse them in another; the designs that would share
are T1 and T2 in `bots/intent.md`.

---

## 9. The prepare cache

A tool folder may declare a **prepare step**: slow work that depends on the card but not on the
seed or event count (Sherpa's and Whizard's integrations, `Herwig read`, MadGraph's process
directory).

- It runs before the point's groups, as its own supervised step (with at least an hour before it
  counts as stalled), in a cache entry `output/<P>/.cache/<tool>/<key>/`.
- The **key** is the tool, its binary's sha256, the base cards' sha256 and the card lines, without
  the lines the folder says to ignore (the event count, the seed) or, with `key = "base"`, the base
  cards alone (MadGraph builds from the proc card only). So every point, replica, rerun and event
  count with the same physics shares one entry.
- An entry is a hit when it holds a **`.prepared` stamp**, written only after the step exited 0 and
  left its `marker` file: an interrupted integration is redone, never used.
- `{prepared}` names the entry in argv and cards; `--plan` shows each prepare step and whether it is
  cached. An export that needs a prepared product (`herwig_run`) runs the step on demand.

---

## 10. Status, the journal and the watch view

| Source | Channel | Read by |
|---|---|---|
| our apps and module programs (`status = "standard"`) | JSON lines on the fd in `$HEP_STATUS_FD` (`Status.hh`) | `status.Reader`, from a pipe per process |
| every other tool (`status = "filters"`) | its stdout and stderr, which go to its log | the log tail, matched against `filters.toml` rules |
| a tool with `status = "none"` | its log | the last line only |

- **stdout is never the status channel**: it may carry HepMC and always carries chatter. Every
  process's output goes to `output/…/<point>/logs/<tag>.log`.
- **A filter rule never fails a run.** The exit code does that.
- **The journal**, `output/…/<cfg>/status.jsonl`, gets every status message tagged with its point,
  tool and time, plus the runner's `run`, `point` and `exit` records.
- **The views.** The live view (with `rich`, on a terminal) shows each running point below the
  finished blocks, after a blank line: its heading and time so far (`mm:ss`, `hh:mm:ss` once there
  are hours), then a line per running tool: progress, rate, ETA, σ, the last warning. The plain view (`--plain`, or not a terminal) prints progress every
  few seconds. **A view never blocks the run** (V32): everything it prints goes through one
  background thread, so a terminal that stops reading (a paused tab, Ctrl-S) stops the display, not
  the supervision. With `parallelism = K` (V36) up to K points run at once, each on a thread of its
  own through the same executor: the views keep a part per running point (the live view shows each
  under its own heading), a block is printed whole when its point ends, the journal takes one line at
  a time, and a prepare cache entry is filled by one point at a time (a lock in the runner, `flock`
  across runners). Both print **one block per finished point**:

  ```
  ── point 2/4: NNPDF23lo ── ok after 1min 12s
     done → results/PhotoProduction/zeus/default/NNPDF23lo
  ```

  A failed point's block names the tool to blame, its exit and the message; a cached prepare step
  is one line in the block. `hep watch` rebuilds the same blocks from the journal in another
  terminal, and leaves when the run finishes.

---

## 11. Failure handling and exit codes

A FIFO chain fails in two ways a single process does not; both are handled by construction.

**Deadlock at open (L8).** Opening a FIFO blocks until both ends are open, and a dead writer leaves
its reader blocked for ever with no SIGPIPE. So:

- each tool runs in **its own process group**; the first nonzero exit is a failure, and after 2 s the
  rest of the group get SIGTERM, then after 5 s more SIGKILL;
- a tool **silent** for `stall_after` seconds (no log line, status message or heartbeat; default
  300) fails as stalled; one past its `timeout` fails as timed out;
- FIFOs are made fresh per point, per attempt.

**A partial result that looks complete.** If the generator dies mid-stream, Rivet sees end of file,
finalises, and exits 0 with a plausible YODA. So every event producer writes a **sidecar** (written,
σ, seeds), every event consumer's count is **checked** against it (Rivet: `/RAW/_EVTCOUNT`, L7; a
module: its report; Delphes: its tree), and a mismatch fails the point with the product still
`*.partial.*` and no `.complete`.

**Attribution.** When several processes die together, the report names the cause: the first process
to exit nonzero before the runner sent any signal. **A SIGPIPE death is never the cause** (its
reader went away first), even when both exits are seen in one poll.

**Ctrl-C** sends SIGINT to the running tools (SIGTERM 2 s later, SIGKILL 5 s after that) and stops
the run with exit 6: the point is left partial, and rerunning the same command resumes, since
finished points are skipped. A second Ctrl-C is the default behaviour.

**Exit codes of our apps** (App_Pythia, App_yd2rt, Paint, module programs):

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

**Exit codes of `hep run`**: 0 every point done or skipped; 1 a point, the post stage or a page
failed; 2 a config error before anything ran; 6 stopped by the user.

---

## 12. Provenance and manifests

- `output/…/<point>/provenance.json` (V23): the point's values; its identity, seed, threads and
  events; per tool the binary's path, sha256 and version, the argv, the card and its sha256, the
  config, and the result (exit, seconds, note); the host, platform, user, git revision and dirty
  flag; start and end times.
- `output/…/<cfg>/points.json`: every point's values (tag, label, value), page, products, directories,
  identity, seed and whether it is complete. Post tools and the plot stage read it, so they never
  have to know the layout; it is also stored inside the merged sweep file.
- Sidecars and reports travel with their products (04 §15).

---

## 13. The plot stage

After the points and the post stage (and on `--only plot` or `hep plot <config>`), from the
complete points only:

1. **Objects**: the 1D objects of the points' YODA product (not `/RAW`, `/TMP`, the run counters or
   weight variations), narrowed by `[plot].objects`. A swept analysis option gives each point its
   own variant path; pages are keyed by the option-free path, and each variant is a curve.
2. **The sweep in one file**: every complete point's YODA merged by `App_yd2rt --merge` into
   `results/…/plots/root/<cfg>.root` (a directory per point, raw entries, `points.json`), rebuilt
   only when a point's YODA changed. The pages read it. The reference data, if any, are converted
   once into `output/<P>/.cache/datasets/`.
3. **Page configs**: one TOML per `plot_points` cell and object in `output/…/plots/`, with the labels
   from the analysis's `.plot` file (TLatex), the `[plot]` values and `[plot.object]` overrides, the
   style layers' changes, the curves and the mapped data.
4. **Draw**: `build/Paint.exe` on each page (the root backend), and/or the yoda backend on the same
   pages with Paint's ranges and voids (`--dump-ranges`). A failed page is counted, and the run exits
   1, but the others are drawn.

The style is a stack of TOML layers over `utils/Apps/Paint/base.toml` (V27), checked against it at
plan time (04 §12). Keys a backend cannot honour are errors, never silently dropped (v1's
`LegendXPos` was parsed and ignored).

---

## 14. Where files go

**Technical files in `output/`, products in `results/`, compiled things in `build/`.** Nothing else
is written by a run.

```
output/<P>/<run>/<cfg>/
  points.json   status.jsonl
  <point>/      cards/  config/  logs/  FIFOs, [prelim] files  provenance.json  .complete
  pre/, post/   the same, for the stages
  plots/        [<cell>/]<object>.toml (Paint's page configs), merged.sha256; yoda/ (mkhtml's work files)
output/<P>/.cache/<tool>/<key>/      prepare caches
output/<P>/.cache/datasets/          reference data converted for Paint
output/tests/                        everything tests write

results/<P>/<run>/<cfg>/
  <point>/                           the products only
  pre/, post/                        the stages' products
  plots/root/<cfg>.root              the sweep in one file
  plots/root/[<cell>/]<object>.<fmt> the ROOT pages
  plots/yoda/[<cell>/]…              rivet-mkhtml's pages
```

`<run>` and `<cfg>` are `NN_<name>` when they have a serial; `<point>` is the swept tags joined by
`_`, or `point`. `datasets/` (your reference data) is not in git; Rivet's are `rivet:<Analysis>`.
