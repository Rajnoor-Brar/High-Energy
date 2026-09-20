# Using the toolkit

A working guide to the implemented system. It assumes the `~/HEP` stack is on your path
(`source ~/HEP/setup.sh`) and that you have built once with `hep build`.

For *why* things are shaped this way, see [rework/](rework/); for *where* things live, see
[MAP.md](MAP.md). This document is about getting work done.

---

## 1. The shape of a session

Everything starts from one TOML config and goes in one direction:

```
hep plan   CONFIG      what would run, without running it
hep run    CONFIG      generate and analyse
hep proc   CONFIG      fit and derive, from results that already exist
hep plot   CONFIG      draw pages
```

Each command reads the same config and the same selectors, so "the points I mean" is one idea rather
than four. Nothing later regenerates events: `hep proc` and `hep plot` work on what is on disk, so
retuning a fit or restyling a figure never costs a generation.

**Look before you run.** `hep plan` prints the points, their identities, the stages each needs and
where output will go. It is the cheapest way to find out that a sweep expands to 240 points rather
than 24.

---

## 2. A config, in the order it is read

```toml
schema = 2
project = "PhotoProduction"

[run]
name = "photo"          # the stem of what gets written
events = 200000
seed = 1001             # the point's identity, not the generator's seed (see §6)
threads = 8
mode = "auto"           # auto | serial | sharded  (§5)

[generator]
tool = "pythia"         # pythia | sherpa | whizard | madgraph
card = "photo_ep.cmnd"  # the native card; physics lives here, not in TOML

[beams]
ids = [2212, -11]       # PDG codes: hadron, lepton

[rivet]
analyses = ["photo_eic"]
paths = ["build/analyses/PhotoProduction"]

[output]
tag_style = "tag"
```

**Physics stays in the native card.** TOML carries run control, wiring, overrides and sweeps; a
Pythia setting belongs in the `.cmnd`, a Sherpa setting in the run card. The toolkit renders the
parts that must vary per point and appends them, so the card you already trust keeps working.

`hep config init` writes a starter; `hep config validate` checks one; `hep config reference` prints
every key with its type, default and meaning (also committed as
[rework/reference/config.md](rework/reference/config.md)).

### Sweeps

A *quantity* is a named axis with values, labels and tags; a *study* says which axes vary.

```toml
[quantity.pdf]
type = "pdf"
values = ["MSTW2008lo68cl", "NNPDF23_lo_as_0130"]
tags = ["MSTW08lo", "NNPDF23lo"]

[study.pdf]
description = "PDF comparison at fixed beams"
across = "pdf"
```

`hep studies CONFIG` lists them; `hep plan CONFIG --study pdf` expands one. `--pin`, `--across`,
`--overlay` and `--set` narrow or reshape a run without editing the file.

---

## 3. Running

```bash
hep run configs/PhotoProduction/eic.toml --study pdf
```

A live dashboard shows each point's stage, rate and ETA; tool chatter goes to `logs/`, with curated
warnings on screen. `hep watch` attaches from another terminal — including to a job someone else
started, since it reads the same status files.

Results land under `results/<project>/`:

```
points/<point>/       analysis.yoda, run.summary.json, provenance.json, logs/
studies/<study>/      plots/, proc/
```

A run that is interrupted writes `analysis.partial.yoda` rather than a truncated `analysis.yoda`, so
a partial result can never be mistaken for a complete one.

**Re-running is cheap.** A point whose identity and inputs are unchanged is skipped. `hep runs`
lists what exists; `hep show POINT` prints its provenance — the exact card, the seeds, the tool
versions, the git revision.

---

## 4. Getting results out

| Want | Command |
|---|---|
| Draw a page per sweep group | `hep plot CONFIG` |
| Draw one point on its own | `hep plot CONFIG --points` |
| Compare two curves numerically | `hep compare A B` |
| Fit a histogram | `hep proc CONFIG` with `[[proc.fit]]` |
| Histogram a Delphes branch | `hep proc CONFIG` with `[[proc.hist]]` |
| Look at the events themselves | `hep events CONFIG --tree` |

Fits and derived histograms are written to `studies/<study>/proc/` as `fits.json` and `proc.yoda`;
setting `[plot].show_fits = true` overlays the fitted curves on the histograms they came from.

---

## 5. Threads, and when they are not used

`[run].threads` is how many workers generate; `[run].mode` is how the *sinks* are fed.

- `serial` — one event at a time. Always correct.
- `sharded` — each worker holds its own copy of a sink's state and they are merged at the end.
- `auto` (the default) — sharded when it is both possible and worth it, serial otherwise, and it
  says which sink asked for serial.

**Jet clustering cannot be shared out.** FastJet keeps clustering state in process-wide statics, so
any analysis or module that makes jets runs under a lock or serially. `auto` detects this before the
first event rather than producing quietly wrong jets. If you write a module that clusters, say so:

```cpp
bool threadSafe() const override { return false; }
```

`hep bench CONFIG` measures generation, sinks and replay separately and recommends a mode with
numbers attached.

---

## 6. Seeds and reproducibility

A point's seed comes from its **identity** — the config, the card, the point's own settings — so the
same point in two runs gets the same events, and two different points never collide. Each worker
takes a disjoint block, so thread count changes the *partitioning* of a run, not its statistics.

Everything needed to explain a number is written next to it: `provenance.json` records the resolved
config, the card's hash, every tool's version, the host and the git revision.

---

## 7. Keeping events

```toml
[store]
enabled = true
compression = "zst"
```

Events are written as sharded HepMC3 with an index, and `hep run` on a config with a store can be
replayed later:

```bash
hep events CONFIG --final          # look at what was generated
hep store ls|info|verify PATH      # inspect or check a store
```

A replay through the same sinks gives a **byte-identical** YODA, so an analysis can be changed and
re-run without regenerating.

---

## 8. Writing your own analysis

Two ways, and the choice is about what you need rather than about taste.

**A Rivet analysis** when you want Rivet's projections, its reference data and its ecosystem:

```bash
hep new analysis MyAna --project MyProject
hep build
```

**A C++ module** when you want to fill YODA objects directly, with the run's own concurrency:

```bash
hep new module MyMod --project MyProject
hep build
```

Both scaffolds compile as they stand. A module implements four verbs, and the order matters:

| Verb | Given | May do |
|---|---|---|
| `configure` | the config's options | read settings |
| `book` | a `Results::Booker` | declare objects, once |
| `process` | the event and **this worker's** objects | fill, with raw weights |
| `finalize` | σ and Σw, after the merge | **scale** |

There is no `scale()` on a worker and no `fill()` on a final result, so "scaled during the run" and
"scaled twice" are not mistakes you can make. `Phys` gives you PDG data, kinematics, selectors and
jet definitions; `ML` runs an ONNX model with one session shared across workers.

---

## 9. Other generators

`[generator].tool` selects it; the rest of the config is unchanged.

| Tool | Notes |
|---|---|
| `pythia` | in process, the default |
| `sherpa` | integrates once per group and caches it; the cache is keyed on the card |
| `whizard` | SINDARIN; no photon structure function, so direct processes only |
| `madgraph` | writes LHE, which Pythia then showers |

A detector stage is a separate process reading a file, not a pipe:

```toml
[delphes]
card = "delphes_card_CMS.tcl"
```

`hep doctor` says which of these are actually available on this machine.

---

## 10. Housekeeping

```bash
hep clean CONFIG --dry-run        # what is taking the space
hep clean CONFIG --events --older-than 30
```

YODA files, `fits.json` and provenance are **never** removed automatically, and no category is on by
default. Removing a store keeps its index, so a cleaned store can still say what it held.

---

## 11. When something goes wrong

| Symptom | First thing to try |
|---|---|
| A command refuses a config | the message names the key and the file; `hep config validate` gives the same check on its own |
| A point will not start | `hep run --check` runs every preflight and generates nothing |
| A tool is missing or wrong | `hep doctor` |
| A run seems stuck | `hep watch`, then `logs/` for the stage named |
| Numbers changed and you do not know why | `hep show` both points and compare their provenance |

Exit codes are stable: `1` config, `2` usage, `3` generator init, `4` input, `5` output, `6` stopped
(partial results written), `7` stalled, `70` a bug.
