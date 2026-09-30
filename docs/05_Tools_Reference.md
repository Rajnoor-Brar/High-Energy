# 05 — Tools reference

Every standard tool: what it runs, how its card is written, which quantities it consumes, what it
writes, how its events are counted, what it can export to a custom tool, and the quirks that shaped
it (the ledger rows, [07 §3](07_Record.md#3-the-knowledge-ledger)). Then the three apps, the module
kit and the status protocol. Written from `utils/Env/<tool>/`, `utils/*.cc`, `utils/*.hh` and
`utils/Apps/Paint/`. How to write a new tool folder is [06 §4](06_Developer_Guide.md#4-the-tool-folder-contract).

---

## 1. The standard tools at a glance

A **standard tool** is a folder `utils/Env/<tool>/`; its name is the value of `tool = …`. The
runner discovers the folders and names none of them.

| `tool =` | Category | Runs | Card | Streamable | Status | Count check | Prepare | Exports |
|---|---|---|---|---|---|---|---|---|
| `pythia` | event generator | `build/App_Pythia.exe` | `.cmnd`, append | — (writes) | standard | produces: sidecar | — | `card`, `cmnd` |
| `rivet` | analysis application | `rivet` (or K of them: `shards`) | none (flags) | yes | filters | `/RAW/_EVTCOUNT` | — | `analyses` |
| `yd2rt` | visualisation | `build/App_yd2rt.exe` | none | file | standard | — | — | — |
| `merge` | analysis application (post) | `rivet-merge` | none | files | none | — | — | — |
| `plotmerge` | visualisation (post) | `App_yd2rt.exe --merge` | none | files | standard | — | — | — |
| `custom` | any | your `executable` | none | per table | none (set it) | only if you set it | — | — |
| `module` | analysis application | your `Module.hh` program | none | yes | standard | the report's `events` | — | — |
| `delphes` | detector simulation | `DelphesHepMC3` | `.tcl`, append (`set`) | **no** (L11) | filters | the `Delphes` tree | — | `card`, `tcl` |
| `herwig` | event generator | `Herwig run` | `.in`, append (`set`) | — (writes) | filters | produces: runner-written sidecar | `Herwig read` | `card`, `in`, `run` |
| `sherpa` | event generator | `Sherpa` | `.yaml`, render (merge) | — (writes) | filters | produces: runner-written sidecar | integration | `card`, `yaml`, `results` |
| `whizard` | process generator | `whizard` | `.sin`, render | — (writes) | filters | produces: runner-written sidecar | integration | `card`, `sin` |
| `madgraph` | process generator | `mg5_aMC` | launch script, render | — (writes a file) | filters | produces: runner-written sidecar | process directory | `card`, `proc`, `process` |

Two more folders are not tools in a chain:

- **`yoda`** holds `backend.py`, the `[plot] backend = "yoda"` plot backend (§14);
- **Paint** (`utils/Apps/Paint/`) is driven by the plot stage, never named in `tools` (§17).

**Not tools at all.** *Providers* (LHAPDF, FeynRules, SARAH) are plan-time checks: a mapping with
`check = "lhapdf"` (a bare set name) or `"pythia_pdf"` (`LHAPDF6:<set>`) refuses an uninstalled PDF
set (C10). *Analysis algorithms* (FastJet, ROOT
libraries) are `// requires:` names in a source ([06 §2](06_Developer_Guide.md#2-the-build)). A
*detector simulation* with no command line of its own (Geant4) is a module program with
`// requires: geant4`. *Statistics* (RooFit, pyhf, uproot, scikit-learn) are custom tools, usually
in `post`.

---

## 2. `pythia` — App_Pythia

```toml
[tools.pythia]
tool        = "pythia"
baseconfig  = "photo_ep.cmnd"        # configs/<P>/photo_ep.cmnd
output_file = "events.hepmc"         # a [prelim] FIFO or file; an array fans out (V16)
```

- **Runs** `build/App_Pythia.exe <outputs> <base cards…> <point card>` (§15): the base cards in
  order, then the point card, so its settings win.
- **Card** (`cards/pythia.point.cmnd`, and `cards/pythia.cmnd` = base + point): a header comment,
  one `Key = value` line per consumed value (`on`/`off` for bools), the footer, then the seeds:
  `Random:setSeed = on`, `Random:seed = <seed>`, and at threads > 1 `Parallelism:seeds = {…}`.
- **Footer** `Beams:LHEF = <input>`, only when the tool has an input: a shower of an LHE file from
  an earlier group (MadGraph); the base card sets `Beams:frameType = 4`.
- **Consumes** through the master: `energies`, `sqrts`, `beam_a`, `beam_b`, `beams`, `pdf`
  (checked installed), `events`, `threads` (04 §3); anything else with `key = { pythia = … }`.
- **Writes** HepMC3 to every output, and the **sidecar** `<first output>.json` (§15). It can
  **deal** its events among a sharded tool's inputs (`[outputs] deal = true`, §3.1).
- **Exports** `pythia_card` = `pythia_cmnd`: `path` (the combined card, seeds included) and `parts`.
- **Identity** includes the binary's sha256; **version** from `pythia8-config --version`.
- Ledger: L1–L6, L25.

## 3. `rivet`

```toml
[tools.rivet]
tool        = "rivet"
input       = "events.hepmc"
analyses    = ["photo_eic", "MC_JETS"]      # "NAME" or "NAME:OPT=V:OPT=V"
options     = { R = 0.4 }                   # applied to every analysis (optional)
output_file = "photo.yoda"
```

| Option | Kind | Notes |
|---|---|---|
| `analyses` | array, **required** | Rivet analyses; inline options as `NAME:OPT=V` |
| `options` | table | options given to every analysis |

- **Runs** `rivet -o <partial output> -a <analysis[:options]>… <input>`, with
  `RIVET_ANALYSIS_PATH = build/Rivet`.
- **Options**, in increasing precedence: inline (`NAME:OPT=V`), `options`, then quantities
  targeting `"<tag>/<analysis>"`. Each analysis must have a `.info` (`build/Rivet/`, then
  `rivet-config --datadir`), and every option it is given must be declared in the `.info`'s
  `Options:` (C9, L19). A quantity's option aimed at an analysis the tool does not run is an error.
- **Consumes** nothing through the master: beams and energies come from the events (L9).
- **σ** is the last event's `GenCrossSection` (L2): App_Pythia re-stamps it with the combined value.
- **Count check**: `/RAW/_EVTCOUNT`'s entries against the producer's sidecar `written` (L7).
- **Identity** includes each project plugin's `.so` (`build/Rivet/Rivet_<analysis>.so`); version
  from `rivet --version`.
- **Exports** `rivet_analyses`: `analyses` (with this point's options applied, e.g.
  `photo_eic:R=0.4`) and `plugin_path` (`build/Rivet`).
- Status by filters: `Event N (` → progress, `ERROR`/`Exception` → error, `WARN` → warning (the
  "unvalidated" warning ignored). Ledger: L7, L9, L10, L19.

### 3.1 Sharded Rivet: `shards = K`

One Rivet process is one core: with ZEUS_2012_I1116258 about 1,500 events/s, a third of it reading
the HepMC text and the rest clustering jets. It sets the pace of a Pythia → Rivet chain whatever
Pythia's threads (measured 2026-09-29: 20 threads left the machine at 4%). `shards = K` runs K Rivet
processes, each on a share of the events, and merges them (V31):

```toml
[tools.rivet]
tool        = "rivet"
input       = "events.hepmc"          # a [prelim] FIFO (or file) written by pythia
analyses    = ["ZEUS_2012_I1116258"]
output_file = "zeus.yoda"
shards      = 10
```

- **The chain does not change** (`tools = [["pythia", "rivet"], "yd2rt"]`). For each point the
  runner makes the FIFOs `events.s1.hepmc` … `events.s10.hepmc` in place of `events.hepmc`; App_Pythia
  deals the events among them (§15); the steps `rivet.1` … `rivet.10` run in the group, each writing
  `output/…/<point>/shards/zeus.s<i>.yoda`; each is count-checked against **its own share**
  (`written_per_output` in the sidecar); then `rivet.merge`, a step of its own in the next group,
  runs `rivet-merge -e` (the `merge` folder) into the table's `output_file` (`zeus.yoda`, in
  `results/`). Logs: `logs/rivet.<i>.log`, `logs/rivet.merge.log`. `--plan` shows every step.
- **The events do not change.** Seeds follow the generator's cards, not its argv (V22), so a
  sharded point has the same events as the same point unsharded; the merged YODA is the same up to
  the rounding of summing in another order. The point's identity does change (its argv), so
  changing `shards` reruns it.
- **Requirements**, refused at plan time otherwise: the tool reads one input and writes one output;
  the input is a `[prelim]` FIFO or file with exactly one producer in the chain, whose folder can
  deal (`pythia`); every analysis is re-entrant (`Reentrant: true` in its `.info`), because
  `rivet-merge -e` runs `finalize()` again on the summed histograms. Other outputs of the producer
  (a module program's FIFO) still get every event.
- **Quantities aimed at the table reach every shard**: `target = "rivet/photo_eic"` (eic's
  `radius`) or `key = { rivet = … }` gives each `rivet.<i>` the same option; `--plan` shows it as
  `rivet.1–10:R`.
- **Choosing K.** Each shard is one core, and so is each Pythia thread: `threads + shards` should
  not exceed the machine. Measured on the lab PC (i7-13700K, 24 hardware threads), 200k ZEUS_2012
  events, steady rate after the ~5 s start:

  | `threads` + `shards` | events/s |
  |---|---|
  | 20 + unsharded | ~1,570 |
  | 8 + 8 | ~8,100 |
  | 12 + 10 | ~9,200 |
  | 14 + 10, 10 + 12 | the same as 12 + 10: the CPU is full |

  `threads = 12`, `shards = 10` is what `eic.toml` and `zeus_validation.toml` use.

## 4. `yd2rt` — YODA → ROOT

```toml
[tools.yd2rt]
tool        = "yd2rt"
input       = "photo.yoda"
output_file = "photo.root"
select      = ["/photo_eic/*"]              # optional: YODA path globs
```

| Option | Kind | Notes |
|---|---|---|
| `select` | array | YODA path globs to convert; default every object except `/RAW` and `/TMP` |

Runs `App_yd2rt.exe <input> <partial output> <select…>` (§16). The ROOT file is a product, in
`results/`. Like every tool in `tools`, it needs its `[tools.<tag>]` table (C5), because the table
says what it reads and writes.

## 5. `merge` — rivet-merge, in `post`

```toml
[run.replicas]
sweeps = ["replica"]
tools  = [["pythia", "rivet"]]
post   = ["merge"]

[tools.merge]
tool        = "merge"
input       = "photo.yoda"       # that product of every point
output_file = "merged.yoda"
equivalent  = true               # default: -e, statistically equivalent runs
```

| Option | Kind | Default | Notes |
|---|---|---|---|
| `equivalent` | flag | true | `-e`: runs of one process (seed replicas); statistics add, σ is averaged. `false` merges different processes into their sum. |

Runs `rivet-merge [-e] -o <partial output> <every point's input>`, with `RIVET_ANALYSIS_PATH` set:
it re-runs the analyses' `finalize()`, so they must be re-entrant. The same folder merges a sharded
Rivet's shards inside a point (§3.1), and each group of a `combine` (04 §5.5: one PDF's seed
replicas, say), where the runner adds it by itself.

## 6. `plotmerge` — the sweep in one file, in `post`

```toml
[tools.bundle]
tool        = "plotmerge"
input       = "photo.yoda"
output_file = "sweep.root"       # or sweep.yoda
```

Runs `App_yd2rt.exe --merge <partial output> <point>=<yoda>… --keep-raw --points points.json`
(§16). Into ROOT: a directory per point, the `paths` tree with a `point` column, and `points.json`
as a `TNamed`. Into `.yoda`: one YODA file with the point as a path prefix. Not a statistical merge
(that is `merge`). The plot stage makes the same file itself, `plots/root/<cfg>.root`, so this tool
is for a copy elsewhere or a YODA version.

## 7. `custom`

Any executable: argv is `{exe} {config} {arguments}` ([04 §9.2](04_Config_Reference.md#92-custom-tools)).
Status `none` unless the table sets it; `HEP_STATUS_FD` is passed when `status = "standard"`.

```toml
[tools.jets_reco]
tool        = "custom"
executable  = "./modules/PhotoProduction/delphes_jets.py"
arguments   = ["{in:delphes.root}", "{partial:output}"]
input       = "delphes.root"
output_file = "jets_reco.json"
```

## 8. `module` — a Module.hh program

argv: `{exe} {config} --input={input} --output={partial:output} --events={events}
--sidecar={input_sidecar} {arguments}` ([04 §9.3](04_Config_Reference.md#93-module-tools)). Status
standard. The count check reads `events` from the program's report, `<output>.json`, against the
producer's sidecar. An empty `--input=` means an integrated program (it makes its own events). The
kit is §18.

## 9. `delphes` — DelphesHepMC3

```toml
[tools.delphes]
tool        = "delphes"
baseconfig  = "delphes_card_ATLAS.tcl"
input       = "showered.hepmc"       # a [prelim] FILE from an earlier group: never a FIFO
output_file = "delphes.root"
```

- **Runs** `DelphesHepMC3 <combined card> <partial output> <input>`.
- **Card**: Tcl, append style, `set {key} {value}` lines; the seed as `set RandomSeed <seed>`.
- **Not streamable** (L11): Delphes sizes its input first and skips a zero-length one, which a FIFO
  always is. A FIFO into it is refused at plan time (C6). It creates its ROOT file before reading
  the card: it writes the partial name the runner gives.
- **Count check**: the `Delphes` tree's entries (read with uproot) against the sidecar.
- **Seeds**: Delphes is not an event producer, so it never moves the generator's seeds (V22).
- **Exports** `delphes_card` = `delphes_tcl`.

## 10. `herwig` — Herwig 7

```toml
[tools.herwig]
tool        = "herwig"
baseconfig  = "dis_ep.herwig.in"
output_file = "events.hepmc"
```

- **Prepare** (cached per card): `Herwig read --repo=build/Herwig/HerwigDefaults.rpo <card>` →
  `point.run` in the cache entry. The repository is made by `hep build` (Herwig's own install could
  not: its defaults need CT14lo/CT14nlo, L15); a plan without it is refused (C10) with `hep build`.
- **Runs** `Herwig run <cache>/point.run -N <events> -s <seed> -d 0`: events and seed are flags, so
  every point and replica with the same physics shares one read.
- **Card**: ThePEG `set {key} {value}` lines (a later `set` wins); the footer reads HepMC output
  (`read snippets/HepMC.in`, the file name, `saverun point EventGenerator`), which must come last.
- **Consumes** `energies` (`Luminosity:BeamEMaxB`, `…A`: the snippet puts the lepton on beam A) and
  `sqrts` (`Luminosity:Energy`).
- **Sidecar** written by the runner after exit 0 (`written = "requested"`: Herwig makes exactly
  `-N` events or fails).
- **Exports** `herwig_card` = `herwig_in`; `herwig_run`: `path` = the `.run` file, **prepared on
  demand** for a custom tool that asks.
- Ledger: L15.

## 11. `sherpa` — Sherpa 3

```toml
[tools.sherpa]
tool        = "sherpa"
baseconfig  = "photo_ep.sherpa.yaml"
output_file = "events.hepmc"
```

- **Card** (`render.py`): the base YAML files deep-merged in order, then each value assigned at its
  **key path** (`EPA:Q2Max`, `PDF_SET[0]`: a list entry is replaced, never appended), written whole.
  `sqrts` becomes `BEAM_ENERGIES = [√s/2, √s/2]`. `MPI_PDF_SET` follows `PDF_SET` (it agreed before,
  or was absent): Sherpa's MPI reads its own key and falls back to a PDF that is not installed
  (L12). Footer `EVENT_OUTPUT: HepMC3_GenEvent[<output name>]`; seed `RANDOM_SEED: <seed>`.
- **The plan owns** `BEAMS`, `BEAM_ENERGIES`, `RANDOM_SEED`, `EVENTS`, `EVENT_OUTPUT`,
  `RESULT_DIRECTORY`: a base card that sets one is refused.
- **Prepare** (the integration, cached by the card without `EVENTS`): `Sherpa -f <card> -e 0
  "RESULT_DIRECTORY: <cache>/Results" "EVENT_OUTPUT: None"`. `EVENT_OUTPUT: None` matters: otherwise
  Sherpa opens the FIFO at initialisation and waits for a reader that only the generation starts.
  Marker `Results.zip`.
- **Runs** `Sherpa -f <card> "RESULT_DIRECTORY: <cache>/Results"`, in the point's directory:
  Sherpa prepends `./` to the output name (L12), so the name is relative.
- **Consumes** `energies`, `beams`, `sqrts`, `pdf` (checked), `events`.
- **Sidecar** written by the runner (`written = "requested"`).
- **Exports** `sherpa_card` = `sherpa_yaml`; `sherpa_results`: the integration directory, prepared
  on demand.
- Sherpa writes a YODA variation per extra weight; the plot stage draws the nominal only. With
  `MI_HANDLER: Amisic` ep photoproduction made 0 events in 768 s (v1): the committed card has MPI
  off. Ledger: L12, L24.

## 12. `whizard` — Whizard 3

```toml
[tools.whizard]
tool        = "whizard"
baseconfig  = "photo_ep.sin"         # exactly one base card
output_file = "events.hepmc"
```

- **Card** (`render.py`): SINDARIN is a script, so the point card comes **first** and includes the
  base **last** (L13): the plan's assignments, `seed = <seed>`, `sample_format = hepmc`,
  `$sample = "<output without .hepmc>"` (Whizard appends `.hepmc`), then `include("<base>")`.
- **Beams are names**: PDG codes become the SM model's names (from `share/whizard/models/SM.mdl`),
  and the base card states its structure-function chain in a comment,
  `# hep: beam_structure = pdf_builtin, epa`, which is appended as `=> pdf_builtin, epa`.
- **The plan owns** `seed`, `n_events`, `sqrts`, `beams`, `beams_momentum`, `$sample`,
  `sample_format`: a base that assigns one is refused (it would run after the plan's value).
- **Prepare** (integration: library, phase space, grids): `whizard <prepare card>`, the point card
  without `n_events`, `$sample`, `sample_format`, keyed without them and `seed`. Generation then runs
  **in the cache entry** (`[command] cwd`), where Whizard finds them.
- **Consumes** `energies` (`beams_momentum`, in GeV), `beams`, `events` (`n_events`).
- **σ**: Whizard writes none into its events, so Rivet has none; the integration log has it.
  Whizard has no photon structure function: direct photoproduction only (L13). Its EPA record has
  no scattered lepton, so a Rivet analysis using `DISKinematics` cannot run on it.
- **Exports** `whizard_card` = `whizard_sin`.

## 13. `madgraph` — MadGraph5_aMC@NLO

```toml
[run.single]
tools = ["madgraph", ["shower", "rivet"], "yd2rt"]

[prelim]
files = ["unweighted.lhe"]
fifo  = ["events.hepmc"]

[tools.madgraph]
tool        = "madgraph"
baseconfig  = "dis_ep.proc_card.mg5"   # the proc card: processes only, no `output` or `launch`
output_file = "unweighted.lhe"

[tools.shower]
tool        = "pythia"
baseconfig  = "shower_lhe.cmnd"          # sets Beams:frameType = 4; the LHEF line is the footer
input       = "unweighted.lhe"
output_file = "events.hepmc"
```

- **Prepare** (keyed on the **proc card only**, `key = "base"`): the proc card plus
  `output <cache>/process -f` → the process directory, built once. Marker
  `process/bin/generate_events`.
- **Card** (the launch script): `set automatic_html_opening False` (else it opens a browser,
  00/B39), `launch <cache>/process -n r<seed>`, shower, detector and analysis off, then
  `set iseed <seed>` and one `set <key> <value>` per value; beams become `set lpp1/lpp2`
  (2212 → 1, −2212 → −1, leptons → 0).
- **Runs** the launch, then unpacks the run's `Events/r<seed>/unweighted_events.lhe.gz` to the
  output: a file, for a `pythia` table in a later group to shower.
- **Consumes** `energies` (`ebeam1`, `ebeam2`: beam 1 is the proc card's first incoming particle),
  `beams`, `events` (`nevents`).
- **Sidecar** written by the runner (`written = "requested"`).
- **Exports** `madgraph_card` = `madgraph_proc`; `madgraph_process`: the process directory,
  prepared on demand.
- Ledger: L14.

---

## 14. Plot backends

| `backend =` | Draws with | Pages in | Honours |
|---|---|---|---|
| `"root"` (default) | `build/Paint.exe`, one call per page | `results/…/plots/root/[<cell>/]<object>.<fmt>` | every `[plot]` key and the whole style |
| `"yoda"` | `rivet-mkhtml`, one call per cell (`utils/Env/yoda/backend.py`) | `results/…/plots/yoda/[<cell>/]<analysis>/<object>.{pdf,png}` + `index.html` | the same pages, with Paint's ranges and voids, and a `legend.position` corner |
| `"both"`, `["root", "yoda"]` | both, from the same page configs | both trees | as each |

The **yoda backend** runs `Paint --dump-ranges` on every page first, then per cell:
- copies of the point YODAs with the voided bins blanked;
- `reference.yoda`: the mapped reference objects cut to their aligned span and renamed
  `/REF/<analysis>/<object>` (mkhtml's own reference lookup is off: explicit only, L18);
- `pages.plot`: per object `XMin`/`XMax`/`YMin`/`YMax` (left out where a gutter of `"default"` leaves
  the range to the tool), `LogX`, `LogY`, `RatioPlot`, the legend corner, and label overrides
  translated TLatex → LaTeX;
- `rivet-mkhtml --no-rivet-refs -o <dir> -c pages.plot <yodas…> [reference.yoda --reflabel …]`,
  with `-f SVG`/`-f EPS` for those formats;
- the ratio pad's y ticks: YODA's generator puts them at a fifth of the pad's range with no key to
  change it (and a later `set_yscale` in its script resets them anyway), so the backend writes
  `ratio.divisions`' locators into each page's script just before it saves, and runs it again.

A backend is a module with `validate(settings, beside_root=False)` and
`draw(cells, settings, say) -> failed pages`; writing one is [06 §6](06_Developer_Guide.md#6-adding-a-plot-backend).

---

## 15. App_Pythia — `utils/App_Pythia.cc`

```
App_Pythia.exe [--threads N] [--events N] [--seeds S1,S2,…] [--sidecar FILE] OUTPUT[,OUTPUT…] CARD [CARD…]
```

Every comma-separated OUTPUT gets **every** event (fan-out, V16). An OUTPUT written **`A+B+C`** is a
**deal group**: each event goes to **one** of its members, the first that is free starting from a
rotating index (so a slow consumer gets fewer), which is how a sharded Rivet gets its shares (§3.1).
`events.s1.hepmc+events.s2.hepmc,to_module.hepmc` deals the events between two Rivet shards and
still copies every one to a module program.

`// requires: pythia8 hepmc3 zstd zlib`. The runner calls it as `{exe} {outputs} {cards}`: threads,
events and seeds are in the point card.

| Behaviour | Ledger |
|---|---|
| Reads the cards in order (the point card last: last wins) | — |
| `PythiaParallel` with `processAsync = on`: callbacks run concurrently, each instance converts with its **own** `Pythia8ToHepMC`, σ is combined under one small lock, and **each output has its own writer and lock**, so formatting the HepMC text is shared among the outputs. (With `processAsync = off` and one writer, the app was capped at ~2,200 events/s whatever its threads: 4 threads took 17.7 s and 20 threads 20.5 s for 40k events.) | L3 |
| Checks the seed list before `init()`: one per thread, each in 1…9·10⁸ (Pythia does not) | L4 |
| Opens the outputs only after `init()` succeeds: a bad card leaves no half-open FIFO | — |
| Runs in chunks of a multiple of the thread count, so SIGINT takes effect within a chunk | L6 |
| Catches in the callback and re-raises on the main thread | L3 |
| σ combined over instances: the ΣW-weighted mean, errors in quadrature | L1 |
| Once more than one instance has contributed, **re-stamps every event's `GenCrossSection` with the combination**, so the last event Rivet reads carries the final σ; at one thread the converter's numbers are untouched (bit for bit the legacy pipeline's) | L2 |
| **Every output ends on the latest σ**: each writes its events one late, and at the end its held event takes the σ of the last event stamped, so every shard of a deal group (and every copy) normalises to the σ an unsharded Rivet would | L28 |
| Several outputs: the same events to each (fan-out, V16), or one of a deal group's members each; a `.gz` or `.zst` suffix picks HepMC3's compressed writer | L25 |
| Events are numbered once, from 0, across the threads; every event carries one shared run info | — |
| Status on `$HEP_STATUS_FD` (§19) | — |

**The sidecar**, `<first output>.json` (or `--sidecar`): `tool`, `pythia_version`, `requested`,
`attempted`, `accepted`, **`written`** (what the count check compares; can be below `requested`,
L5), `write_failures`, `sigma_pb`, `sigma_err_pb`, `sum_w`, `threads`, `seeds`, `random_seed`,
`outputs` (every path, in order), **`written_per_output`** (`{"<path>": events, …}`: what a
shard's count check compares), `cards`, `stopped`. It is written after the outputs are closed.

**Exit codes**: 0 ok, 1 card or config, 2 usage, 3 init, 5 output, 6 stopped (outputs and sidecar
written, `stopped: true`), 70 internal.

## 16. App_yd2rt — `utils/App_yd2rt.cc`

```
App_yd2rt.exe IN.yoda OUT.root [GLOB …] [--keep-raw]
App_yd2rt.exe --merge OUT.root|OUT.yoda NAME=IN.yoda … [--keep-raw] [--select GLOB] [--points FILE]
```

`// requires: yoda root`.

| YODA | ROOT |
|---|---|
| `Histo1D`, `Estimate1D` | `TH1D` (an Estimate's error is the average of its total down and up errors) |
| `Histo2D`, `Estimate2D` | `TH2D` |
| `Scatter2D` | `TGraphAsymmErrors` |
| `Counter`, `Estimate0D` | a one-bin `TH1D` |

- **Directories nest as the YODA path does**: `/photo_eic/d01-x01-y01` → `photo_eic/d01-x01-y01`.
  A variant path `/photo_eic:R=0.4/…` becomes `photo_eic__R-0.4/…` (`:` → `__`, `=` → `-`). Every
  object's title is its original YODA path, and the `paths` TTree maps each ROOT path back.
- `/RAW` and `/TMP` are skipped unless `--keep-raw`, which also writes `<name>__entries` (per-bin
  raw entry counts) beside each `/RAW` histogram: Paint's `min_entries` reads them.
- **`--merge`**: each input's objects go under a directory named for it (its point). The `paths`
  tree gets a `point` column, and `--points` stores `points.json` in the file as the TNamed
  `points.json`. Into a `.yoda` file, the name is a path prefix instead.
- Exit codes: 0 ok, 2 usage, 4 input, 5 output.

## 17. Paint

```
Paint.exe PAGE.toml [--dump-ranges]
Paint.exe [PAGE.toml] --dump-style
```

`utils/Apps/Paint/` (`main.cc`, `Page.hh`, `Style.hh`, `Transform.hh`, `Draw.hh`), built to
`build/Paint.exe`, `// requires: root toml`. One page per call.

**The page config**, written by the runner to `output/…/plots/[<cell>/]<object>.toml`:

```toml
[page]
name        = "d06-x01-y01"
output      = "/…/results/…/plots/root/d06-x01-y01"    # without extension
formats     = ["pdf", "png"]
title       = "1 > #eta > 1.5, #it{k}_{#it{T}} alg"
x_label     = "#it{E}_{#it{T}} [GeV]"
y_label     = "d#sigma / d#it{E}_{#it{T}} [pb/GeV]"
logx        = false
logy        = true
y_gutter    = 0.5                  # or "default"
x_gutter    = "default"
ratio       = true
ratio_label = "MC/Data"
void_empty  = true
min_entries = 10
auto_range  = true
range_pad   = 0

[style]                            # only what the style layers changed (04 §12)
page.dpi = 300

[[curve]]
file   = "/…/plots/root/default.root"
object = "MSTW08lo/ZEUS_2012_I1116258/d06-x01-y01"
raw    = "MSTW08lo/RAW/ZEUS_2012_I1116258/d06-x01-y01"   # optional: for min_entries
label  = "MSTW 2008 LO"

[data]                             # optional
file   = "/…/output/PhotoProduction/.cache/datasets/ZEUS_2012_I1116258.yoda.root"
object = "REF/ZEUS_2012_I1116258/d06-x01-y01"
label  = "ZEUS 2012"
```

A curve object is a `TH1` or a `TGraphAsymmErrors`. `[page]` keys other than `output` default as in
the table of 04 §11. The style is `utils/Apps/Paint/base.toml`, found beside `build/` (else under
`$HEKIT_ROOT`), with the page's `[style]` merged over it; an unknown key or a value of another kind
is an error.

**What it does, in this order** (inherited from v1, load-bearing):

1. load the curves (and the `/RAW` entries when `raw` is given);
2. **void** bins across the whole page: `void_empty` (zero in every curve), `min_entries` (fewer
   raw entries in any curve); only when the curves share one binning (else a warning);
3. **align** the reference data to the first curve's bins: its longest run of bins whose edges are
   all MC edges, or drop it with a warning;
4. **x range**: auto-range (bins with content, plus `range_pad`) or the full range, then `x_gutter`;
5. **y range**: `(1 + y_gutter) ×` the largest drawn value within x (on a log axis, the gutter is
   that fraction of the decades shown); with no gutter, ROOT's own choice for one histogram holding
   every drawn value (`THistPainter`: 5% of the span above, below as well unless that crosses 0; on
   a log axis ×0.5 below and ×2·0.9/0.95 above);
6. **draw**: MC as steps per run of non-void bins (a voided bin is a gap), with error bars at the
   bin centres (or a band, or none); the data as points with x bars, under the MC; the legend (a
   "+" per entry, the title as its header, data first; a curve with every bin voided is listed as
   "(no entries)"); the ratio pad: each curve over the data, or over the first curve, on the
   reference's bins, its range at least `ratio.range` widened to the ratios drawn within
   `ratio.limits`; labels at the joint of the two pads are dropped;
7. save each format (`pdf`, `png`, `svg`, `eps`); the PDF page is `page.size`, the PNG size × dpi.

**`--dump-ranges`** prints the result of steps 1–5 as JSON and draws nothing: `x`, `y`, `largest`,
`voided` (1-based bins), `data_bins`, `data_x` (the aligned data span), `x_tool`, `y_tool` (the
range is the tool's own choice: no gutter). This is how the arithmetic is tested, and what the yoda
backend uses. **`--dump-style`** prints the merged style as TOML (base.toml's alone without a page).

**Exit codes**: 0 ok, 1 page config or style, 2 usage, 4 input, 5 output.

## 18. `Module.hh`

A module is a plain program in `modules/<P>/<Name>.cc` with its own `main()`, built to
`build/<P>/<Name>.exe`. `#include "Module.hh"` adds `hepmc3 toml` to its libraries; add `root` for
`RootOut`.

```cpp
// modules/Lambda/Lambda.cc          requires: root   (Module.hh adds hepmc3 toml)
#include "Module.hh"
#include "TH1D.h"

int main(int argc, char** argv) {
    Module::Job job(argc, argv);                        // CONFIG.toml --input= --output= --events= --sidecar=
    const double massTol = job.config().get("mass_tolerance", 0.15);
    Module::RootOut out(job.output());                  // written when the job finishes
    auto* mass = out.book<TH1D>("mass", ";m_{p#pi} [GeV];dN", 100, 1.08, 1.16);

    for (const Module::Event& event : job.events())     // file or FIFO, plain/gz/zst
        for (const auto& candidate : reconstruct(event.hepmc(), massTol))
            mass->Fill(candidate.mass, event.weight());

    out.scale(job.crossSectionPb() / job.sumW(), "width");   // once; "width" for a density (L21)
    return job.finish();
}
```

| Call | Does |
|---|---|
| `Module::Job job(argc, argv)` | parses `CONFIG.toml [--input=F] [--output=F] [--events=N] [--sidecar=F]` (`--x v` also works); reads the config; installs SIGINT/SIGTERM handlers |
| `job.config()` | a `Values` view of the config: `get(key, fallback)`, `has(key)`, `list(key)`, `table(key)`, `raw()` |
| `job.quantities()` | the config's `[quantities]` table |
| `job.events()` | iterates `Module::Event`s from the input (`HepMC3::deduce_reader`: file or FIFO, plain, gz or zst); counts events and ΣW, reports progress, stops on a signal |
| `event.hepmc()`, `event.weight()` | the `HepMC3::GenEvent`; its first weight (1 if none) |
| `job.count()`, `job.sumW()` | events read and ΣW so far |
| `job.crossSectionPb()`, `job.crossSectionErrPb()` | from `--sidecar` when given (a file chain), else the last event's `GenCrossSection` (Rivet's rule, L2) |
| `job.standard(key)`, `job.standardParts(key)`, `job.standardValues(key)` | a requested standard configuration (04 §9.4): its `path`, its `parts`, or its table; a request the table did not make is an error naming the key |
| `job.hasInput()` | false for an integrated program (empty `--input=`); `events()` is then unavailable |
| `job.countEvent(w)`, `job.setCrossSection(pb, err)` | an integrated program's own count, ΣW and σ |
| `job.progress(done, total)`, `job.status()` | status reporting (§19) |
| `job.fail(code)`, `job.stopping()` | an early exit with a `Module::Exit` code; whether a stop was requested |
| `job.finish()` | writes every output, then the report `<output>.json` (`events`, `sum_w`, `sigma_pb`, the σ source); returns the exit code: 6 when interrupted |
| `Module::RootOut out(path)` | ROOT histograms written to one file at `finish()`; `book<H>("Dir/name", args…)` books into a directory |
| `out.scale(factor, option)` | once, after the loop (a second call is an error: fill raw, scale once); `"width"` also divides by the bin width |

`RootOut` exists when ROOT's headers are on the include path (the source requires `root`). A module
runs single-threaded; one that uses threads and clusters jets must not share FastJet's SISCone
statics (L16). **Exit codes** (`Module::Exit`): `Ok` 0, `Config` 1, `Usage` 2, `Init` 3, `Input` 4,
`Output` 5, `Stopped` 6, `Internal` 70.

An **integrated program** (`modules/PhotoProduction/InprocJets.cc`, V33) asks for `pythia_cmnd`
and `rivet_analyses` (`job.standard`, `job.standardValues`), so it gets the same card and seeds as
the chain's App_Pythia would, and the rivet table's analyses with their options. It runs Pythia as
App_Pythia does and `rivet_threads` `Rivet::AnalysisHandler`s on threads of their own (V34). Its
parts are headers in `modules/PhotoProduction/Inproc/`:

| Header | Holds |
|---|---|
| `Stamp.hh` | what every event gets before Rivet sees it: one numbering, one run info, the combined σ (L1, L2), and the last σ stamped (L28) |
| `Feed.hh` | a bounded queue from the Pythia threads to the Rivets: whichever Rivet is free takes the next event; a full feed holds generation back |
| `Analysis.hh` | the Rivets: every handler initialised on the first event before any analyses; each `analyze`s on its own thread; at the end `merge` into the first (raw fills and event counters added, before any `finalize`, so re-entrancy is not needed), the L28 σ as a user σ (`setCrossSection(σ, true)`), one `finalize`, `writeData`. Above one Rivet it checks that SISCone's state is per thread (L29) and refuses otherwise |
| `Engines.hh` | `serial` (one `Pythia8::Pythia`) and `parallel` (`PythiaParallel`, `processAsync = on`, a converter per instance, chunks of 100 × threads); after Rivet's thread starts, a failure is returned, never exited on (L3, L5, L6) |

Config (`[tools.<tag>.config]`): `engine` (`"parallel"`, `"serial"`) and **`rivet_threads`** (default
1). Several Rivets in one process need FastJet's SISCone to keep its state per thread: stock SISCone
has one random generator and one η range for the process, and threads clustering at once get other
jets or a FastJet internal error (L16, L29). The patch is
`utils/Env/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch` (applied to `~/HEP` on
2026-09-29); a single-threaded Rivet gives byte-identical YODAs with it.

| 200k events of `single`, with the ~5 s start-up | photo_eic (`InProcEIC`) | ZEUS (`InProcZeus`) |
|---|---|---|
| chain, 12 threads + 10 `shards` | 29.0 s | 27.1 s |
| in one process, 12 threads + 1 Rivet | 112 s | — |
| in one process, 12 + 12 Rivets | 20.7 s | — |
| in one process, 10 + 14 Rivets | 19.3 s | 17.3 s |

One Rivet in one process was already 1.26× the old callback design (31.3 s → 24.9 s for 40k
events, the same YODA to the last digit); several make the integrated program ~1.5× the sharded
chain, because nothing formats or parses HepMC text.

## 19. `Status.hh` and the status protocol

A tool with `status = "standard"` writes **JSON lines** to the file descriptor named in
`$HEP_STATUS_FD`. The runner opens a pipe per process and reads it; unknown kinds are kept in the
journal and otherwise ignored, so the set can grow. **stdout is never the status channel**: it may
carry HepMC, and it always carries chatter, which goes to `logs/<tag>.log`.

| Kind | Fields | Shown as |
|---|---|---|
| `phase` | `phase`, `detail` | the tool's phase |
| `progress` | `done`, `total`, `rate` | the progress bar, rate and ETA |
| `xsec` | `value_pb`, `err_pb`, `final` | σ |
| `log` | `level` (`warn`, `error`), `msg` | the last warning or error |
| `summary` | tool-defined (counts, outputs) | journal only |
| `heartbeat` | — | keeps the tool from counting as stalled |

Every line has the envelope `{"t": <unix time>, "k": <kind>, …}`.

**C++**: `#include "Status.hh"` (before any X11 header: X11 `#define`s `Status`), then
`Status::Reporter status;`, which reads the variable itself.

| Call | |
|---|---|
| `Reporter(int beatMs = 500)` | a heartbeat every `beatMs` when structured |
| `structured()` | the descriptor is set |
| `phase(name, detail)`, `progress(done, total, rate, force)`, `xsec(pb, err, final)`, `log(level, msg)`, `summary(jsonFields)` | one message each; `progress` sends at most every 0.25 s unless `force` |
| `dropped()` | lines dropped because the pipe was full |

Writes are **non-blocking and drop on a full pipe**, so a slow reader never slows a generator. With
the variable unset, the same calls print plain lines to stderr, so a tool run by hand is readable.

**Python** (or any language): write the same lines yourself; there is no client module yet (F10).

```python
import json, os, time
fd = int(os.environ["HEP_STATUS_FD"]) if "HEP_STATUS_FD" in os.environ else None
def status(kind, **fields):
    if fd is not None:
        os.write(fd, (json.dumps({"t": time.time(), "k": kind, **fields}) + "\n").encode())
status("progress", done=500, total=10_000, rate=120.0)
```

A tool that stays silent (no log line, status message or heartbeat) for `stall_after` seconds
(default 300) fails as stalled.

## 20. `filters.toml`

For a tool that only prints: its log is tailed, each new line matched against the rules in order,
**the first match wins**.

```toml
# utils/Env/<tool>/filters.toml, or your own via status = "filters:<file>"
[[rule]]
match = '^Event (?P<done>\d+) \('     # a Python regex
emit  = "progress"                    # progress | phase | warn | error | ignore

[[rule]]
match = '^Reading events from'
emit  = "phase"
phase = "analysing"                   # a fixed name; else the (?P<phase>…) group, else the match

[[rule]]
match = 'ERROR|Exception'
emit  = "error"
```

| `emit` | Needs | Makes |
|---|---|---|
| `progress` | a `(?P<done>…)` group (commas and spaces allowed), optionally `(?P<total>…)` | a `progress` message |
| `phase` | `phase = "…"`, or a `(?P<phase>…)` group | a `phase` message |
| `warn`, `error` | — | a `log` message with the line |
| `ignore` | — | nothing, and stops the lines below from matching |

**A rule never fails a run**: the exit code does that. A rule that stops matching costs a progress
bar, not a result. Lines are split on `\n` and `\r` (a counter rewritten in place, like Herwig's
`event>`). The last line of the log is always shown for a tool with no progress.
