# 01 — Philosophy

What the framework is for, the principles it follows, what each one buys, and what it refuses. The
rest of the manual is a consequence of this page.

---

## 1. What it is

A framework for **Monte Carlo studies in high-energy physics** on one machine, for one
physicist-developer: generate events with a standard generator, analyse them with Rivet or your own
program, sweep the settings that matter, and compare the curves with each other and with data.

Its whole shape is one sentence of the brief ([07 §1](07_Record.md#1-the-brief)): **tools are
processes, chained by a TOML**. A run TOML names a configuration; its sweeps expand into points; for
each point the runner writes each tool's native card, connects the tools with agreed files and
FIFOs, runs them in order, watches them, and records what happened; after all points it draws the
pages. The runner decides and supervises; the tools do the physics.

---

## 2. Principles

Each is stated, then justified by what it buys, because a principle that cannot name what it paid
for is decoration.

### 2.1 Every tool is a process, and the runner only decides

App_Pythia, Rivet, Herwig, Delphes, a module program: each is its own process, reading files the
runner wrote and writing files the runner checks. No tool runs inside another, the runner links no
physics library, and no tool reads the run TOML.

**Buys:** a tool you trust keeps working exactly as it does by hand, and its log is its own; any
program in any language joins a chain by being an executable; a failure is one process's, with its
exit code. **Costs:** in-process speed (0.90× v1's rate end to end, measured) and one text
serialisation per hop. An in-process loop is still possible, as *your* program with the chain's
card and seeds (an integrated program, 03 §4.14), but it is never the framework's.

### 2.2 Physics lives in the native card

A Pythia setting belongs in the `.cmnd`, a Sherpa setting in its YAML, a Whizard one in SINDARIN.
TOML carries run control, wiring and sweeps. A quantity renders an *override* into a point card, and
each tool combines it with its base card by its own rule: last wins for Pythia, a deep merge for
Sherpa, the point card before the base for Whizard.

**Buys:** no cross-generator "same physics" dialect to maintain and re-verify against every tool
release; the card on disk is the card that ran. **Costs:** "the same study with another generator"
is a matching of each knob by hand (L24).

### 2.3 Resolved means resolved

Every tool gets a finished card and a finished argv. `threads = 0` becomes a number at plan time;
seeds are numbers in the card; paths are absolute. No tool interprets a default.

**Buys:** `--plan` prints exactly what will run, and the tools cannot disagree about what a value
means.

### 2.4 Say it once, where it belongs

Everything about a kind of tool is in its folder (`utils/Env/<tool>/`): how to run it, write its
card, read its progress, count its events, cache its slow step. Everything about how a quantity
reaches a tool is in the master TOML. Everything about the look of a page is in `base.toml`. The
runner's core names no tool.

**Buys:** a new tool is a new folder; a quirk is fixed in one file; the knowledge is data you can
read. v1 decided a quantity's effect with a nine-way type dispatch in code; here it is a table.

### 2.5 Require the explicit statement; refuse the convenient inference

Connections are named (`input`, `output_file`), never guessed. Reference data are matched through an
explicit map, never by histogram name. A quantity must be consumed by a tool, or it is refused. A
Rivet option must be declared by its analysis. A style key must exist.

**Buys:** the failure v1 kept meeting cannot happen silently: ZEUS data drawn over a different
observable (00/B5), options that changed nothing (00/B14), a swept value that renamed a directory
and nothing else (00/B40), a legend key parsed and dropped. In every case the system did something
plausible instead of refusing. **Costs:** a few more lines in a config, and errors you have to read.

### 2.6 Refuse early, and say what to do

Every check runs at plan time, before any process starts: the schema, the connections, the
consumers, the analyses' options, the providers, the paths, the styles. Every refusal names where
(the file and key) and gives a hint, with the nearest spelling for a misspelt name.

**Buys:** a sixteen-point sweep never fails at point nine because of a typo.

### 2.7 A partial result has a different name

A product is written as `*.partial.*` and renamed only after its checks pass; `.complete` is
written last. A consumer's event count is checked against the producer's sidecar, because a
generator that dies mid-stream leaves Rivet with a plausible YODA and exit 0.

**Buys:** a truncated result is never mistaken for a complete one, and a rerun resumes exactly
where the last one stopped.

### 2.8 Identity decides; location is only location

A point's identity hashes everything that decides its result; seeds derive from the generator's
part of it. The same point gets the same events in every run, two points never share events, and the
thread count changes the partition, not the statistics. A point is skipped when its identity is
complete; a serial or a directory name never decides anything.

**Buys:** a rerun of an unchanged study does nothing, a changed one reruns exactly what changed,
and a chain and an integrated program with the same generator set-up are comparable bin for bin.

### 2.9 Knowledge outlives code

v1 was deleted, but what it learned by running things is kept as a ledger (L1–L26), and the code that
honours a row cites it. Findings, decisions and risks keep their ids for ever.

**Buys:** the reason a line is shaped as it is survives the next rewrite. A comment that says
"L2" says why App_Pythia re-stamps every event's cross section.

### 2.10 Measure it, and say the number when it is bad

Gates produce numbers (σ to 1.3e-8, byte-identical YODAs, 17 of 17 ranges), and budgets are
measured, not felt: the code is 1.41× its budget, and the record says where and why
([07 §9](07_Record.md#9-budget)).

### 2.11 Enforce the rules you can

The runner's import ranks are a test; tests never write into `results/` or `configs/`, and a guard
fails the run if they do; the manual's keys are checked against the code. A rule a test enforces
is a rule; a rule in a document is a hope.

### 2.12 Small by surface area

A few commands (`hep run`, `hep plot`, `hep overlay`, `hep watch`, and `ls`, `explain`, `status`,
`clean`, `check` to look after them) plus `hep build` and `make`; seven config
sections; two C++ headers; one flat runner package. Anything a user does not ask for is not there
(v1 had 19 commands).

---

## 3. What is refused

| Refused | Why |
|---|---|
| A general DAG or workflow engine | `tools` is a sequence of groups; the connection rules only check it |
| Physics in TOML | §2.2 |
| An in-process event loop in the framework | §2.1 (V2); your program may run one |
| Inferring connections, units, data maps or which tool a quantity is for | §2.5 |
| Silently ignoring a key a backend or tool cannot honour | §2.5: it is an error |
| Built-in statistics and fits | a fit is a custom tool in `post` (V4) |
| Sharing events between points | V9; deferred with a named trigger (`bots/intent.md` T1–T2) |
| A C++ library layer | V7: a program links what it needs |
| CMake | V6: `make <path>.exe` is the interface |

---

## 4. Where it came from

| | |
|---|---|
| **v0** | a hand-built `utils/` (10,404 lines of C++) and four unversioned scripts around Pythia → FIFO → `rivet` |
| **v1** (`rework/v1-final`) | a Python orchestrator (`hekit`, 17k lines, 19 commands) over one in-process C++ event loop (`hep-run`, 6.8k lines, 11 namespaces), CMake, 33k lines of tests; it worked, and was measured and well-evidenced, but its pipeline was *derived* (stage chains from roles, phases inferred, a nine-way quantity dispatch) and it had two ways of doing most things |
| **v2** (2026-09-26/27) | the user's own design (the brief): tools as processes, one run TOML, conventions for where things live. v1's code was deleted, its knowledge kept. Executed in five phases, gated by numbers (07 §8) |
| **after** | the user's additions: a pre stage, the sweep in one file, `hep plot`, the mkhtml look and the style in TOML, both backends, the gutters (V23–V29), and this manual (V30) |

The decisions and what each gave up are [07 §2](07_Record.md#2-decisions).
