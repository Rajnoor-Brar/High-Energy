# 01 — Overview

What the framework is, the model it is built on, the words the rest of the manual uses, and the
principles behind its shape: what each one buys, what it costs, and what is refused because of it.

---

## 1. What it is

A framework for **Monte Carlo studies in high-energy physics** on one machine, for one
physicist-developer. It generates events with a standard generator, analyses them with Rivet or your
own program, sweeps the settings that matter, and compares the curves with each other and with data.

Its whole shape is one sentence of the brief ([07 §1](07_Record.md#1-the-brief)): **tools are
processes, chained by a TOML**.

- A run TOML names a configuration, and its sweeps expand into points.
- For each point the runner writes each tool's native card, connects the tools with agreed files and
  FIFOs, runs them in order, watches them, checks what they made, and records it.
- After all the points it draws the pages.

The runner decides and supervises. The tools do the physics.

---

## 2. The model in one picture

```
hep run PhotoProduction/eic energy_pdf                      utils/Env/hep → utils/Env/run → runner.cli
  │
  ├─ load     configs/PhotoProduction/eic.toml  (+ utils/Env/quantities.toml, <tool>/quantities.toml: quantity → tool maps)
  ├─ resolve  [run.energy_pdf]: sweeps, plot_points, tools, static, prelim
  ├─ expand   sweeps = ["energies", "pdf"]  →  16 points   (a grid of axes; entangled groups zip)
  ├─ plan     per point: cards, config files, argv, connections, identity, seeds; every check (C1–C14)
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
  ├─ combine  points that differ only in a combined quantity (replicas) merged into one, per group
  ├─ post     tools run once after every point, handed every point's products and points.json
  └─ plot     the sweep merged into plots/root/energy_pdf.root; its figures made into pages: one per
              energy and histogram, the PDFs as curves; drawn by build/Paint.exe (and/or mkhtml, mpl)
```

**Every box is a process or a file.** No tool runs inside another, the runner links no physics
library, and no tool reads the run TOML. The runner's whole job is to decide, write the files each
tool reads, start the processes in order, watch them, check what they made, and record what
happened.

---

## 3. Vocabulary

These words carry the design. The full glossary is [07 §10](07_Record.md#10-glossary).

| Word | Means |
|---|---|
| **run** | one TOML under `configs/<Project>/` |
| **configuration** | a named recipe inside a run (`[run.<name>]`): sweeps, tools, events, threads |
| **quantity** | a named value that can be swept or held static (`[quantities.<q>]`) |
| **point** | one combination of swept values: one chain of processes, one output directory |
| **tool** | one process in the chain (`[tools.<tag>]`), of a kind a tool folder describes |
| **group** | tools that run together, connected by FIFOs (an inner list in `tools`) |
| **stage** | tools run once rather than per point: `pre` before the points, `post` after them, and a combined group (`combine`) |
| **object** | the data: one histogram, estimate or scatter in a point's YODA (`/ZEUS_2012_I1116258/d01-x01-y01`) |
| **figure** | a recipe for pages (`[plot.figures.<f>]`): which objects, how they are built (its *class*: defined, overlay, merged, compare, derived, scan, sheet) and what is drawn (its *type*: Hist1D, Scatter2D, HeatMap). `[plot].objects` is the implicit one |
| **page** | the output: one drawn file. A figure gives a page per `plot_points` cell, and per object when it names a glob; the other swept quantities are its curves |

---

## 4. Principles

Each principle is stated, then justified by what it buys. A principle that cannot name what it paid
for is decoration.

### 4.1 Every tool is a process, and the runner only decides

App_Pythia, Rivet, Herwig, Delphes and a module program are each a process of their own. They read
files the runner wrote and write files the runner checks. No tool runs inside another, the runner
links no physics library, and no tool reads the run TOML.

**Buys:**
- a tool you trust works exactly as it does by hand, and its log is its own;
- any program in any language joins a chain by being an executable;
- a failure belongs to one process, with its exit code.

**Costs:** in-process speed (end to end, 0.90× v1's rate, measured) and one text serialisation per
hop. An in-process loop is still possible as *your* program, given the chain's card and seeds (an
integrated program, [02 §6.2](02_User_Guide.md#62-an-integrated-program)), but it is never the
framework's.

### 4.2 Physics lives in the native card

A Pythia setting belongs in the `.cmnd`, a Sherpa setting in its YAML, a Whizard one in SINDARIN.
TOML carries run control, wiring and sweeps. A quantity renders an *override* into a point card, and
each tool combines it with its base card by its own rule: for Pythia the last line wins, for Sherpa
the cards are deep-merged, and for Whizard the point card goes before the base.

**Buys:** there is no cross-generator "same physics" dialect to maintain and re-verify against every
tool release, and the card on disk is the card that ran. **Costs:** "the same study with another
generator" means matching each knob by hand (L24).

### 4.3 Resolved means resolved

Every tool gets a finished card and a finished argv. `threads = 0` becomes a number at plan time;
seeds are numbers in the card; paths are absolute. No tool interprets a default.

**Buys:** `--plan` prints exactly what will run, and the tools cannot disagree about what a value
means.

### 4.4 Say it once, where it belongs

Each kind of knowledge has one home:
- **a kind of tool:** its folder, `utils/Env/<tool>/`. That covers how to run it, write its card,
  read its progress, count its events and cache its slow step.
- **how a quantity reaches a tool:** the master TOML.
- **every key a run TOML may hold:** `utils/Env/schema/run.toml`, with its type, default and
  meaning.
- **the look of a page:** `base.toml`.

The runner's core names no tool. The reference's key tables are generated from the schema and the
style file ([04](04_Config_Reference.md)), not written twice.

**Buys:** a new tool is a new folder, a quirk is fixed in one file, and the knowledge is data you
can read. v1 decided a quantity's effect with a nine-way type dispatch in code; here it is a table.

### 4.5 Require the explicit statement; refuse the convenient inference

Nothing is guessed:
- connections are named (`input`, `output_file`);
- reference data are matched through an explicit map, never by histogram name;
- a quantity must be consumed by a tool, or it is refused;
- a Rivet option must be declared by its analysis;
- a style key must exist.

**Buys:** the failures v1 kept meeting cannot happen silently:
- ZEUS data drawn over a different observable (00/B5);
- options that changed nothing (00/B14);
- a swept value that renamed a directory and nothing else (00/B40);
- a legend key parsed and dropped.

In every case the system did something plausible instead of refusing. **Costs:** a few more lines
in a config, and errors you have to read.

### 4.6 Refuse early, and say what to do

Every check runs at plan time, before any process starts: the schema, the connections, the
consumers, the analyses' options, the providers, the paths, the styles and the figures. Every
refusal names the file and key, and gives a hint, with the nearest spelling for a misspelt name.
`hep check` runs them all over every config and runs nothing.

**Buys:** a sixteen-point sweep never fails at point nine because of a typo.

### 4.7 A partial result has a different name

A product is written as `*.partial.*` and renamed only after its checks pass, and `.complete` is
written last. A consumer's event count is checked against the producer's sidecar, because a
generator that dies mid-stream leaves Rivet with a plausible YODA and exit 0.

**Buys:** a truncated result is never mistaken for a complete one, and a rerun resumes exactly where
the last one stopped.

### 4.8 Identity decides; location is only location

A point's identity hashes everything that decides its result, and its seeds derive from the
generator's part of it. So:
- the same point gets the same events in every run;
- two points never share events;
- the thread count changes the partition, not the statistics.

A point is skipped when its identity is complete; a serial or a directory name never decides
anything.

**Buys:** a rerun of an unchanged study does nothing, and a changed one reruns exactly what changed.
A chain and an integrated program with the same generator set-up are comparable bin for bin.

### 4.9 Knowledge outlives code

v1 was deleted, but what it learned by running things is kept as a ledger (L1–L29), and the code
that honours a row cites it. Findings, decisions and risks keep their ids for ever.

**Buys:** the reason a line is shaped as it is survives the next rewrite. A comment that says "L2"
says why App_Pythia re-stamps every event's cross section.

### 4.10 Measure it, and say the number when it is bad

Gates produce numbers: σ to 1.3e-8, byte-identical YODAs, 17 of 17 ranges, mpl's pages pixel for
pixel against mkhtml's. Budgets are measured, not felt; the record says where the code stands
against them and why ([07 §9](07_Record.md#9-budget)).

### 4.11 Enforce the rules you can

These rules are enforced by tests:
- the runner's import ranks;
- tests never write into `results/` or `configs/`, and a guard fails the run if they do;
- the manual's keys, links, examples and generated tables are checked against the code.

A rule a test enforces is a rule; a rule in a document is a hope.

### 4.12 Small by surface area

The surface stays small:
- one `hep` command with a few subcommands ([05 §1](05_Commands_and_Tools.md#1-commands)), plus
  `hep build` and `make`;
- seven sections in a run TOML;
- a few C++ headers;
- one flat runner package.

Anything a user does not ask for is not there (v1 had 19 commands).

---

## 5. What is refused

| Refused | Why |
|---|---|
| A general DAG or workflow engine | `tools` is a sequence of groups; the connection rules only check it |
| Physics in TOML | §4.2 |
| An in-process event loop in the framework | §4.1 (V2); your program may run one |
| Inferring connections, units, data maps or which tool a quantity is for | §4.5 |
| Silently ignoring a key a backend or tool cannot honour | §4.5: it is an error |
| Built-in statistics and fits | a fit is a custom tool in `post` (V4) |
| Sharing events between points | V9; deferred with a named trigger (`bots/intent.md` T1–T2) |
| A C++ library layer | V7: a program links what it needs |
| CMake | V6: `make <path>.exe` is the interface |

---

## 6. Where it came from

| | |
|---|---|
| **v0** | a hand-built `utils/` (10,404 lines of C++) and four unversioned scripts around Pythia → FIFO → `rivet` |
| **v1** (`rework/v1-final`) | a Python orchestrator (`hekit`, 17k lines, 19 commands) over one in-process C++ event loop (`hep-run`, 6.8k lines, 11 namespaces), CMake, and 33k lines of tests. It worked and was measured and well evidenced, but its pipeline was *derived* (stage chains from roles, phases inferred, a nine-way quantity dispatch), and it had two ways of doing most things |
| **v2** (2026-09-26/27) | the user's own design (the brief): tools as processes, one run TOML, conventions for where things live. v1's code was deleted and its knowledge kept. It was built in five phases, each gated by numbers (07 §8) |
| **after** | the user's additions (V23–V51): a pre stage, the sweep in one file, the mkhtml look and the style in TOML, shards, combine, sweeps of runs, seeds by choice, other generators, integrated programs |
| **audit 1** (V52–V79) | the schema, frozen test fixtures, the tool folders as data, labels in LaTeX, the event stream and `hep watch`, the mpl backend, `hep check`, `migrate` and `reproduce` |
| **figures** (V80–V89) | `[plot.figures]`: seven ways to build a page and three things to draw |
| **audit 2** (V90–) | this manual, rebuilt on generated reference tables |

The decisions and what each gave up are in [07 §2](07_Record.md#2-decisions).
