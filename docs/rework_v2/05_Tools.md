# 05 — Tools

What a tool is to the runner, the standard tools v2 ships, and the C++ it builds: three apps and
the module kit. It implements *Brief §Tools* and the tool parts of *Brief §Commands*
([00_Brief.md](00_Brief.md)): *"utils/Env/run script, dict of standard tools, in Env/{tool}/ for
standard operation scripts, such as config parser and whatever for that respective tool."*

Everything here is **written fresh** (V5). Where v1 learned something the hard way, the entry
cites its row in the knowledge ledger ([01 §7](01_Assessment.md#7-the-knowledge-ledger)).

---

## 1. The tool folder contract

**Every standard tool is a folder `utils/Env/<tool>/`.** The folder name is the value of `tool = …`
in a run TOML. The set of folders **is** the brief's "dict of standard tools". The runner discovers
the folders, and its core names none of them.

```
utils/Env/<tool>/
  tool.toml        required   what the tool is and how to run it (below)
  render.py        optional   how to write its native point card, when [card] style is not enough
  filters.toml     optional   stdout/stderr rules, for a tool without the standard status protocol
  README.md        optional   quirks and measured behaviour (the ledger rows that apply)
```

### `tool.toml`

```toml
# utils/Env/rivet/tool.toml
[tool]
category        = "analysis-application"   # one of the ten (02 §4); printed by --plan
executable      = "rivet"                  # on PATH, or a build/ path for our own apps
streamable      = true                     # may read its input from a FIFO
status          = "filters"                # "standard" ($HEP_STATUS_FD) | "filters" | "none"
consumes_events = true                     # its count is checked against the producer's sidecar

[card]
style = "none"                             # rivet has no card; everything is a flag

[command]                                  # argv template; {…} are placeholders (03 §2)
argv = ["rivet", "--pwd", "-o", "{partial:output}", "{analyses}", "{in:input}"]
env  = { RIVET_ANALYSIS_PATH = "{repo}/build/Rivet" }

[options]                                  # tool-specific keys a [tools.<tag>] table may carry
analyses = { kind = "list", item = "str", required = true }
options  = { kind = "table" }              # analysis options, applied to every analysis

[outputs]
products    = ["yoda"]
event_count = "yoda:/RAW/_EVTCOUNT"        # how the count check reads it back (L7)

[exports.analyses]                         # a custom tool may ask for this with rivet_analyses = true
gives = ["analyses", "plugin_path"]        # values, not files: rivet has no card
```

**A rendered card is exported automatically** as `<tool>_card` (`path`, `parts`). Nothing needs to
be declared for it (V21). `[exports.<name>]` is for everything else:
- an **alias** of the card, e.g. `[exports.cmnd] alias = "card"` in `pythia/`, which makes
  `pythia_cmnd` equal to `pythia_card`;
- **values**, like rivet's `analyses` above;
- **products of a prepare step**, which add `needs_prepare = true`, e.g. `[exports.run]` in
  `herwig/`.

| Section | Holds |
|---|---|
| `[tool]` | category, executable, `streamable`, status mode, `consumes_events` / `produces_events` |
| `[card]` | how a point card is made. `style` is one of: `"append"` (last wins: Pythia, Herwig, Delphes), `"prepend"` (the point card first, then include the base: Whizard, L13), `"none"`, or `"render"` (`render.py` writes the whole card: Sherpa's YAML merge, L12). `line` is the native form of one value (`"{key} = {value}"` by default, `"set {key} {value}"` for ThePEG and Tcl); `footer` lines end the card (Herwig's `saverun`); `seed` lines come after both |
| `[command]` | the argv template and environment |
| `[options]` | a schema for the tool-specific keys, in the runner's field vocabulary: `kind`, `item`, `required`, `choices`. Every option is also an argv placeholder; `kind = "flag"` (with `flag = "-e"`, `default`) expands to the flag or to nothing |
| `[outputs]` | which outputs are products, and how an event count is read back: `yoda:/RAW/_EVTCOUNT`, `json:events` (the module kit's report) or `root:<tree>` (Delphes). `written = "requested"`: a generator that always makes what it is asked for or fails (Herwig, Sherpa) gets its sidecar written by the runner |
| `[prepare]` | optional: a step run before the point, in a cache entry `output/<P>/.cache/<tool>/<key>/` (`argv`, a `marker` it must leave, and card keys to `ignore` in the key, like the event count). A hit, stamped `.prepared`, runs nothing; `{prepared}` names the entry |
| `[checks]` | optional: Rivet's `.info` directories, and `files` that must exist before a plan (Herwig's repository) |
| `[exports.<name>]` | optional: configuration a custom tool may request as `<tool>_<name> = true` ([04 §7.3](04_Config.md#73-standard-configurations-for-custom-tools)): what it gives (`path`, `parts`, or named values), and `needs_prepare` |

**How a tool consumes quantities** is not in the tool folder. It is in the master TOML
(`[quantities.<tool>.compatible_quantities]`, [04 §2](04_Config.md#2-master)), where the brief puts
it, so all quantity knowledge is in one readable file.

### `render.py`

Only for dialects that `[card] style` cannot write. It is plain functions, not classes:

```python
# utils/Env/sherpa/render.py (as built, P4 S2)
def card(bases: list[str], overrides: list[Override], context: dict) -> str: ...   # the whole card, before seeds
```

The prepare key is not the plugin's business: the runner hashes the card lines, minus `[prepare]
ignore` keys. Sherpa's keys are paths into the tree, with list indices (`PDF_SET[0]`).

`Override` is the runner's own `NamedTuple(key, value, origin)`. Tests use the real type, never a
look-alike (L26, the F1 lesson). A plugin imports only `errors`, `paths` and `quantities`
([02 §3](02_Architecture.md#3-components)).

---

## 2. The standard tools

| Tool | Category | Executable | Streamable | Status | Phase |
|---|---|---|---|---|---|
| `pythia` | event generator | `build/App_Pythia.exe` | — (writes) | standard | P1 |
| `rivet` | analysis application | `rivet` | yes | filters | P1 |
| `custom` | any | `executable = …` | per table | per table | P1 |
| `yd2rt` | visualisation | `build/App_yd2rt.exe` | no (file) | standard | P3 |
| `paint` | visualisation | `build/Paint.exe` | — | standard | P3 (driven by `[plot]`) |
| `yoda` | visualisation | `rivet-mkhtml` | — | none | P3 (driven by `[plot] backend = "yoda"`): `utils/Env/yoda/backend.py`, no `tool.toml` |
| `merge` | analysis application | `rivet-merge` | no (files) | none | P3, in `post`: one product of every point, `-e` unless `equivalent = false` |
| `module` | analysis application | `build/<P>/<Name>.exe` (a `Module.hh` program) | yes | standard | P4 S1; count check from the kit's report |
| `delphes` | detector simulator | `DelphesHepMC3` | **no** (L11) | filters | P4 S2: `set` card with `RandomSeed`, count from the `Delphes` tree |
| `herwig` | event generator | `Herwig` (read as a cached prepare, then run) | — (writes) | filters | P4 S2: needs `build/Herwig/HerwigDefaults.rpo` (`hep build`); seed and events are flags |
| `sherpa` | event generator | `Sherpa` | — (writes) | filters | P4 S2: `render.py`; integration as a cached prepare |
| `whizard` | process generator | `whizard` | — (writes) | filters | P4 |
| `madgraph` | process generator | `mg5_aMC` | — (writes a file) | filters | P4 |

**Exports.** These are what a custom or module tool can request with a `<tool>_<export> = true`
key ([04 §7.3](04_Config.md#73-standard-configurations-for-custom-tools)). **Every tool with a card
exports `<tool>_card` automatically.** The rows below are the named aliases and the declared extras:

| Request key | Gives | Needs prepare | Phase |
|---|---|---|---|
| `<tool>_card` (automatic) | `path` (base + point overrides in one file, in the tool's dialect), `parts` (the files in reading order) | no | with each tool |
| `pythia_cmnd` | alias of `pythia_card` | no | P1 |
| `rivet_analyses` | `analyses` (with the point's options applied, e.g. `photo_eic:R=0.4`), `plugin_path` | no | P1 |
| `herwig_in` | alias of `herwig_card`: the point `.in` | no | P4 |
| `herwig_run` | `path`: the `.run` file written by `Herwig read` | yes | P4 |
| `sherpa_yaml` | alias of `sherpa_card`: the merged `Sherpa.yaml` | no | P4 |
| `sherpa_results` | `path`: the integration directory | yes | P4 |
| `whizard_sin` | alias of `whizard_card`: the point `.sin`, which includes the base | no | P4 |
| `madgraph_proc` | alias of `madgraph_card`: the `proc_card.dat` | no | P4 |
| `madgraph_process` | `path`: the built process directory | yes | P4 |
| `delphes_tcl` | alias of `delphes_card`: the detector card | no | P4 |

**Providers** (LHAPDF, FeynRules, SARAH) are not tools. They are **plan-time checks** in
`utils/Env/providers.py`; for example, every PDF named by a `pdf` value must be installed
(`lhapdf ls --installed`). **Analysis algorithms** (FastJet, ROOT libraries) are only `requires:`
names ([03 §5.2](03_Layout_Build.md#52-what-to-link-the-requires-line)).

**Where the P4 tools start from.** v1's adapters are consulted in git
(`git show rework/v1-final:utils/python/hekit/adapters/<tool>.py`), not copied:

| Tool | Ledger |
|---|---|
| delphes | L11 |
| sherpa | L12, L24 |
| whizard | L13 |
| madgraph | L14 |
| herwig | L15 |

---

## 3. Status: the standard protocol and the filter rules

### 3.1 The standard protocol

A tool with `status = "standard"` writes **JSON lines to the file descriptor named in the
environment variable `HEP_STATUS_FD`**. With the variable unset, it writes plain progress lines to
stderr. The runner opens one pipe per process and passes it with `pass_fds`.

```json
{"t": 1790000000.123456, "k": "phase",    "phase": "generating"}
{"t": 1790000001.500000, "k": "progress", "done": 12000, "total": 1000000, "rate": 8123.4}
{"t": 1790000002.000000, "k": "xsec",     "value_pb": 11950.0, "err_pb": 34.0, "final": false}
{"t": 1790000003.000000, "k": "log",      "level": "warn", "msg": "3 events failed hadronisation"}
{"t": 1790000900.000000, "k": "summary",  "written": 1000000, "attempted": 1020031, "outputs": ["events.hepmc"]}
```

- The kinds are in [02 §8](02_Architecture.md#8-status-and-the-watch-view). **An unknown kind is
  kept and ignored**, so the set can grow.
- **C++:** `#include "Status.hh"`, then `Status::Reporter status;`, which reads the variable itself,
  and calls such as `status.progress(done, total)`. Writes are non-blocking and drop on a full
  pipe, so a slow reader never slows the generator. A heartbeat thread runs every 500 ms.
- **Python custom tools:** `utils/Env/runner/status_client.py` (~30 lines), with the same envelope.

### 3.2 Filter rules

For tools that only print:

```toml
# utils/Env/sherpa/filters.toml
[[rule]]
match = 'Event\s+(?P<done>[\d ,]+)\s*\('
emit  = "progress"                   # progress | phase | warn | error | ignore

[[rule]]
match = '(?P<phase>Integrat\w+|Simulat\w+)'
emit  = "phase"

[[rule]]
match = 'ERROR|Exception'
emit  = "error"                      # shown on screen; the exit code, not this, fails the run

[defaults]
last_line = true                     # show the last log line when nothing matched
```

- **A rule never fails a run.**
- A run TOML can point one tool table at its own rules: `status = "filters:<file>"` (root
  `configs/<project>/`).
- Every line also goes to `logs/<tag>.log`.
- The starting patterns for each tool are in v1's `run/parsers.py:78-98`, in git.

---

## 4. App_Pythia — `utils/App_Pythia.cc`

**The** Pythia runner (F5). It is ~250 lines, `// requires: pythia8 hepmc3`.

```
App_Pythia.exe [--threads N] [--events N] [--seeds S1,S2,…] [--sidecar FILE]
               OUTPUT[,OUTPUT…] CARD [CARD …]
```

| Behaviour | Ledger |
|---|---|
| Read the cards in order with `Print:quiet`, the point card last (last wins) | — |
| `Parallelism:processAsync = off`; **one serialised writer** behind a mutex | L3 |
| Validate the seed list before `init()`: length = threads, each in 1…9·10⁸ | L4 |
| Chunked `run()`, so SIGINT takes effect within a chunk | L6 |
| Catch in the callback and re-raise on the main thread | L3 |
| σ combined over instances: ΣW-weighted mean, errors in quadrature | L1 |
| Several `OUTPUT`s (fan-out, V16); a `.gz` or `.zst` suffix picks HepMC3's compressed writer | L25 |
| Status on `$HEP_STATUS_FD` through `Status.hh`; exit codes as in 02 §9 | — |
| **Sidecar** `<first output>.json`: `written`, `attempted`, `accepted`, `sigma_pb`, `sigma_err_pb`, `sum_w`, `seeds`, `threads`, `pythia_version`, the card sha256s, `stopped` | L5 |

**σ reaching Rivet (L2, F6).** The serialised writer keeps each instance's latest
(ΣW, σ, err). Before writing each event, it overwrites the event's `GenCrossSection` with the
**combined** value. The last event Rivet reads therefore carries the final combined σ.

**The gate** (P1 S1):

- at threads = 4, Rivet's `/_XSEC` must equal the sidecar's `sigma_pb` to 1e-6 relative;
- at threads = 1, the result must equal the legacy reference YODA bin for bin.

If the overwrite approach fails the gate, the fallback is to run Rivet with `-x <σ>`, re-finalising
from the sidecar after generation.

---

## 5. The module kit — `utils/Module.hh`

A module is **a plain program** (V8): `modules/<P>/<Name>.cc` with its own `main()`, built to
`build/<P>/<Name>.exe`. `Module.hh` removes the boilerplate and nothing else.

```cpp
// modules/Lambda/Lambda.cc               requires: root   (Module.hh adds hepmc3 toml)
#include "Module.hh"
#include "Reconstruction.hh"
#include "TH1D.h"

int main(int argc, char** argv) {
    Module::Job job(argc, argv);                          // CONFIG.toml --input F --output F [--sidecar F]
    const double massTol = job.config().get("mass_tolerance", 0.15);
    Module::RootOut out(job.output());                    // writes out.partial.root, renames on success
    auto* mass = out.book<TH1D>("mass", ";m_{p#pi} [GeV];dN", 100, 1.08, 1.16);

    for (const Module::Event& event : job.events()) {     // file or FIFO, plain/gz/zst; weights; ΣW; status
        for (const auto& lambda : reconstruct(event.hepmc(), massTol))
            mass->Fill(lambda.mass, event.weight());
    }
    out.scale(job.crossSectionPb() / job.sumW());         // σ from the sidecar, else the last event
    return job.finish();                                  // exit code; .partial if the stream ended early
}
```

| `Module.hh` provides | |
|---|---|
| `Module::Job` | argv parsing; the config TOML (toml++), with the consumed quantities under `[quantities]`; status reporting |
| `job.events()` | iteration over `HepMC3::GenEvent`s through `HepMC3::deduce_reader` (file or FIFO, plain/gz/zst); weight; running ΣW and count; `progress` status |
| `job.crossSectionPb()`, `job.sumW()` | σ from `--sidecar` if given, else the last event's `GenCrossSection` (Rivet's rule, L2) |
| `Module::RootOut`, `Module::YodaOut` | atomic output: `*.partial.*` until `finish()` succeeds |
| `job.finish()` | the exit code (02 §9); `*.partial.*` if the stream was truncated or interrupted |
| `job.standard("pythia_cmnd")`, `job.standardParts(…)`, `job.standardValues(…)` | a standard tool's rendered configuration, when the tool table requests it ([04 §7.3](04_Config.md#73-standard-configurations-for-custom-tools)). A request that was not made is an error naming the missing key. |
| `job.hasInput()` | false for an integrated program that makes its own events; `job.events()` is then unavailable |
| `job.progress(done, total)`, `job.fail(code)` | status reporting and an early exit with one of the 02 §9 codes, for programs that loop themselves |

**An integrated program**, such as Pythia and Rivet in one process, uses the same kit without an
input stream:

```cpp
// modules/PhotoProduction/InprocJets.cc       requires: pythia8 rivet   (Module.hh adds hepmc3 toml)
#include "Module.hh"
#include "Pythia8/Pythia.h"
#include "Pythia8Plugins/HepMC3.h"
#include "Rivet/AnalysisHandler.hh"

int main(int argc, char** argv) {
    Module::Job job(argc, argv);                          // tool table: pythia_cmnd = true, rivet_analyses = true
    Pythia8::Pythia pythia;
    pythia.readFile(job.standard("pythia_cmnd"));         // the point card: same seeds as App_Pythia would get
    if (!pythia.init()) return job.fail(Module::Exit::Init);

    Rivet::AnalysisHandler rivet;
    rivet.addAnalyses(job.standardValues("rivet_analyses").list("analyses"));
    // … loop: pythia.next() → Pythia8ToHepMC → rivet.analyze(event); job.progress(i, n) …
    rivet.setCrossSection({pythia.info.sigmaGen() * 1e9, pythia.info.sigmaErr() * 1e9});   // L2: σ once, at the end
    rivet.finalize();
    rivet.writeData(job.output());
    return job.finish();
}
```

This is v1's in-process `hep-run` loop, back as **a user program** rather than as the framework
(V2). The runner neither knows nor cares that Pythia runs inside it.

**The one rule the types no longer enforce** (v1's scaling contract): fill with raw weights, and
scale **once**, after the loop. It is documented in `Module.hh`, and `RootOut::scale` refuses a
second call. If a histogram is drawn beside Rivet's, divide by the bin width as well (L21):
`out.scale(σ/ΣW, "width")`.

**As built (P4 S1).**
- The CLI is `CONFIG.toml --input=F --output=F --events=N --sidecar=F`. Both `--x=v` and `--x v`
  work. An empty `--input=` means an integrated program, and an empty `--sidecar=` means none.
- The module folder (`utils/Env/module/`) always passes a config and the `.partial` output. The
  kit writes it as given, with a report beside it, `<output>.json` (events, ΣW, the σ used and its
  source). The report travels with the product when the runner renames it, and the count check
  reads it (`event_count = "json:events"`).
- **σ.** `{input_sidecar}` names the producer's sidecar only when the producer ran in an earlier
  group (a file chain). App_Pythia closes its outputs before writing the sidecar, so a FIFO reader
  would race it. In a FIFO chain σ is the last event's, as Rivet's is (L2), which is also what
  makes Lambda equal Lamriv.
- **`RootOut` lives in `Module.hh`**, but only when ROOT's headers are on the include path
  (`__has_include(<TFile.h>)`), which is exactly when the source requires `root`. `YodaOut` is not
  written: no module needs it yet.
- Integrated programs report their own events with `job.countEvent(w)` and
  `job.setCrossSection(pb, err)`.

Modules run single-threaded. A module that needs threads and clusters jets must respect L16.

---

## 6. App_yd2rt — `utils/App_yd2rt.cc`

```
App_yd2rt.exe IN.yoda OUT.root [--select GLOB …] [--keep-raw]
```

About 250 lines, `// requires: yoda root`.

- **One `TDirectory` per analysis.**

  | YODA | ROOT |
  |---|---|
  | `Histo1D` | `TH1D`, errors included |
  | `Histo2D` | `TH2D` |
  | `Scatter2D`, `Estimate1D` | `TGraphAsymmErrors` |
  | `Counter` | a one-bin `TH1D` |

  These are the conventions of v1's `proc/export.py`, read in git.
- **Variant paths** (`/photo_eic:R=0.4/d01-x01-y01`) become safe directory names. The original path
  is kept in the object title, and a `paths` TTree maps back.
- `/RAW/*` objects are skipped unless `--keep-raw` is given.
- The output is a **product** in `results/`, non-temporary as the brief asks.

---

## 7. Paint

`utils/Apps/Paint/` builds to `build/Paint.exe PAGE.toml`: *"a legacy Paint like utils, that can be
compiled as standalone program, and called to output based on config file"* (*Brief §Plotting*).
It is about 900 lines, `// requires: root toml`.

**Input.** One page config per page and object, written by the runner from `[plot]`
(`output/…/plots/<page>/<object>.toml`). `raw` names the curve's `/RAW` twin, whose `__entries`
App_yd2rt writes with `--keep-raw`, for `min_entries`:

```toml
[page]
name     = "pdf/d01-x01-y01"
formats  = ["pdf", "png"]
output   = "results/PhotoProduction/03_eic/01_pdf/plots/d01-x01-y01"
title    = "Inclusive jet E_{T}, k_{T}"         # from the Rivet .plot, or a [plot.object] override
x_label  = "E_{T}^{jet} [GeV]"
y_label  = "d#sigma/dE_{T} [pb/GeV]"
logy     = true
y_gutter = 1.5
x_gutter = 1.0
ratio    = true

[[curve]]
file   = "results/…/27x920_MSTW08lo/photo.root"
object = "photo_eic/d01-x01-y01"
label  = "MSTW 2008 LO"

[[curve]]
file   = "results/…/27x920_NNPDF23lo/photo.root"
object = "photo_eic/d01-x01-y01"
label  = "NNPDF 2.3 LO"

[data]
file   = "output/PhotoProduction/.cache/datasets/zeus_eic.root"    # yd2rt of datasets/zeus_eic.yoda
object = "REF/ZEUS_2012_I1116258/d01-x01-y01"
label  = "ZEUS 2012"
```

**What it does, in this order.** v1 found the order load-bearing:

1. load the curves;
2. **void** bins across the whole page (`void_empty`, `min_entries`);
3. overlay the **reference data**, aligned to the drawn binning (L18);
4. **auto-range** over curves and data together;
5. apply the gutters: y maximum = `y_gutter ×` the largest drawn value (the brief's definition),
   and `x_gutter` widens x symmetrically;
6. draw the main pad, the legend and the optional ratio pad. The ratio pad divides each curve by
   the data, or by the first curve when there are none; its range is at least 0.5–1.5, widened to
   the ratios drawn, within 0–3. A curve whose every bin is voided stays in the legend as
   "(no entries)";
7. save each format.

The algorithms of steps 2–4 are v1's `plot/transform.py` and `plot/data.py`, read in git and
written again in C++. The config-driven style layer (canvas, palette, draw options, scales) follows
`legacy/utils/Paint/`, also read in git. The overlays across files, the ratio pad, the reference
data and the gutters are new.

**`Paint --dump-ranges PAGE.toml`** prints the final axis ranges as JSON, which is how the gutter
and auto-range tests check it without looking at pixels.

---

## 8. Custom tools

Anything with an executable. The runner:

- builds its argv from `arguments` with placeholders
  ([03 §2](03_Layout_Build.md#2-how-a-name-becomes-a-path));
- passes the extracted config as the first argument;
- sets `HEP_STATUS_FD` in case the tool speaks the protocol;
- otherwise applies the table's `status` setting.

A custom tool is count-checked only if its table says `consumes_events = true` and names how to read
its count.

**Standard configurations.** A custom tool can request any standard tool's rendered configuration
with `<tool>_<export> = true` ([04 §7.3](04_Config.md#73-standard-configurations-for-custom-tools)).
It then finds the paths under `[standard.<tool>_<export>]` in its config, or in `arguments` through
`{std:<tool>_<export>}`. That is how an integrated run, meaning one program doing what a chain of
tools would, gets the same cards and seeds as the chain.

**Statistics tools belong here** (V4). A RooFit fit, an uproot script or an ML training script is a
custom tool in `post`, handed `points.json`.
