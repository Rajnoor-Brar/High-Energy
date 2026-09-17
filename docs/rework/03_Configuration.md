# 03 — Configuration

**Goal:** TOML alters behaviour "to reasonable extents" (guideline 1).

**Principle:** TOML never *re-expresses* physics that already has a native language:
- `.cmnd` for Pythia;
- YAML for Sherpa;
- `.in` for Herwig;
- SINDARIN for Whizard;
- cards for MadGraph;
- `.tcl` for Delphes.

TOML carries:
1. **Run control:** events, seeds, threads, outputs.
2. **Wiring:** which generator, which sinks, which analyses.
3. **Overrides and sweeps** that are rendered *into* the native card.
4. **Presentation:** plots, terminal.

This is the base + point design that already works for PhotoProduction (`eic.toml`), generalised to all generators.

---

## 1. File anatomy

```toml
schema  = 2
extends = ["../common/eic_beams.toml"]      # optional layering (§2)

[run]                                       # run control
name          = "eic"                       # output stem
events        = 1_000_000
seed          = 270403                      # base of the identity seed policy (§5); never offset by position
threads       = 20                          # 0 = all cores (resolved by hep)
skip_existing = true
label         = ""                          # optional free text for manifests; never used in paths

[generator]
tool = "pythia"                             # pythia | sherpa | herwig | whizard | madgraph | store
card = "photo_ep.cmnd"                      # native base card, relative to this file
# madgraph only: shower = "shower.cmnd"     # Pythia card used to shower the LHE
# store only:    input  = "eic_5x41_em_NNLO" # point name, "sha256:…", or path to an events/ dir (11)

[beams]                                     # generator-neutral; each adapter renders it (04)
ids      = [2212, 11]                       # PDG ids, [A, B] — Pythia's idA/idB order
energies = [41, 5]                          # GeV, [E_A, E_B] → lab frame
# energies = 28.64                          # scalar → √s in the CM frame (warned if ids differ, §3)

[rivet]
analyses     = ["photo_eic"]                # "NAME" or "NAME:OPT=V:OPT=V"
options      = { R = 1.0 }                  # applied to every project analysis that declares the option
paths        = ["analyses/PhotoProduction"] # plugin search path (added to RIVET_ANALYSIS_PATH for children)
mode         = "inprocess"                  # inprocess | native (Sherpa only)
check_beams  = true
weights      = "nominal"                    # nominal | all (multi-weight YODA)
xsec         = "generator"                  # generator | <number in pb>
dump_every   = 100_000                      # periodic finalize → partial YODA (0 = off)

[store]                                     # optional HepMC3 event store (11)
enabled     = false
compression = "gz"                          # gz | zst (after D-STORE-COMP) | none

[[sinks.module]]                            # optional user C++ module → YODA objects in analysis.yoda (05 §5)
name    = "mymodule"                        # registered name (HEKIT_MODULE), found in modules/<project>/
options = { window = 0.010 }

[delphes]                                   # optional detector simulation (external stage; in-process deferred)
card = "delphes_card_EIC.tcl"

[output]
root      = "results/{project}"
tag_style = "tag"                           # tag | value | index

[plot]                                      # was [yoda]
backend      = "mkhtml"                     # mkhtml | mpl
merge        = "overlay"                    # overlay | yodamerge (seed-only sweeps)
void_empty   = false
min_entries  = 1
auto_range   = true
range_pad    = 1
legends      = "label"                      # label | tag | value
analysis     = ""                           # common analysis name when plugins differ ("" = first)

[plot.data]
file      = "datasets/zeus_eic.yoda"
legend    = "Data"
show      = true                            # was data_hist
reference = true                            # ratio denominator
rivet_refs = false
map       = { "d01-x01-y01" = "/REF/ZEUS_2012_I1116258/d01-x01-y01" }   # explicit; no name-only matching (00/B5)

[[proc.fit]]                                # optional post-run processing (12)
name   = "peak"
target = "/mymodule/m_ppi"
model  = "gauss + poly2"
range  = [1.08, 1.16]

[terminal]                                  # see 06
dashboard = "auto"                          # auto | live | plain
log_tail  = 6
stall_after = "5m"

[settle]  …   [quantity.<q>]  …   [sweep]  …   [study.<s>]  …     # §3–§5
```

**Section ownership:**
- Each section maps to one Python dataclass in `hekit.config.schema`.
- Adapters and sinks read **only** their own section.
- The planner is the only reader that sees everything.

## 2. Layering and precedence

Precedence, lowest to highest:
```
built-in defaults  <  machine file  <  extends chain (left→right)  <  this file
                   <  [settle]  <  --study  <  --pin / --set  <  sweep values at a point
```

- **Machine file:** `~/.config/hekit/machine.toml`.
  - Holds only an allow-listed set of machine keys: `run.threads`, `terminal.*`, `paths.lhapdf`, `tools.<name>.exe`.
  - The allow-list stops a machine file from silently changing physics.
- **`extends`:**
  - tables merge deeply; arrays and scalars replace;
  - "deeply" stops at a key that holds one value: an inline table on such a key (for example the per-tool
    `[quantity.<q>].key = { pythia = "PDF:pSet" }`) replaces as a whole, while a *free* table — `[settle.gen]`,
    `[rivet].options`, `[plot.data].map` — merges key by key (P1-S02);
  - paths are resolved relative to the file that wrote them;
  - cycles are an error.
- **`--set key=value`:** a CLI escape hatch for any scalar. It is recorded in provenance as an override.
- **Every resolved value keeps its origin** (`file:line` or `cli`). `hep plan --explain run.threads` prints the chain.

## 3. Quantities (the sweep catalogue)

This generalises `[sweep.cmnd.*]` / `[sweep.rivet.*]` into one flat catalogue `[quantity.<name>]`. Addressing by bare name (`"pdf"`) is shorter than the old `cmnd.pdf`. The **side** (generation vs analysis) is derived from the type.

| `type` | Side | Value form | Rendered as |
|---|---|---|---|
| `setting` | gen | scalar, or a `{key = value, …}` table for coupled keys | a native setting line; `key` syntax per tool (below) |
| `beams` | gen | `[idA, idB]` PDG ids; or a single id with `side = "a"\|"b"` | the adapter's beam-particle settings |
| `energies` | gen | `[E_A, E_B]` in GeV (lab frame), or a scalar √s (CM frame) | the adapter's beam-energy settings |
| `seed` | gen | int | the tool's seed setting |
| `card` | gen | path | an extra native fragment appended to the point card (e.g. a tune file) |
| `generator` | gen | `{tool = "...", card = "..."}` | switches the whole generator: generator comparison |
| `events` | gen | int | `run.events` for that point (scaling studies) |
| `analysis` | ana | name | replaces the `[rivet].analyses` entry |
| `option` | ana | scalar | `:OPT=value` on the target analysis (`target =` optional) |

**`setting` keys per tool.** The adapter validates the syntax.

| Tool | `key` example | Rendered line |
|---|---|---|
| pythia | `"PDF:pSet"` | `PDF:pSet = LHAPDF6:…` |
| sherpa | `"PDF_LIBRARY"` or a YAML path `"BEAMS.1"` | a merged YAML override document |
| herwig | `"/Herwig/Partons/RemnantDecayer:ladderPower"` | `set <key> <value>` |
| whizard | `"sqrts"` | `<key> = <value>` before `integrate` |
| madgraph | `"run_card.ptj"` | `set ptj <value>` in the launch script |

When the `generator` quantity is swept, `key` may be a per-tool table:
`key = { pythia = "PDF:pSet", sherpa = "PDF_SET" }`.
A swept setting with no key for the active tool is a planning error.

**Beams and energies are separate quantities.** Particle identity and beam energy used to be mixed: energies were a `beams` quantity and the lepton was a `pythia` setting on `Beams:idB`. Now:
- `beams` holds PDG ids only, and `energies` holds energies only.
- Either one can be scanned, pinned or coupled independently.
- `[beams].ids` and `[beams].energies` give the file-wide values. Catalogue entries of the matching type override them.

```toml
[quantity.beams]                  # lepton charge (was cmnd.lepton)
type   = "beams"
side   = "b"                      # only beam B varies; A stays [beams].ids[0]
values = [11, -11]
labels = ["$e^-$", "$e^+$"]
tags   = ["em", "ep"]
use    = 1

[quantity.energies]               # was cmnd.beams
type   = "energies"
values = [[41, 5], [100, 10], [275, 18], [920, 27.5]]
labels = ["5x41 GeV", "10x100 GeV", "18x275 GeV", "27.5x920 GeV"]
tags   = ["5x41", "10x100", "18x275", "27x920"]
use    = 1
```

**Rules:**
| Check | Result |
|---|---|
| ids are not integers, or are not in the PDG table (`ParticleData` / `hekit.phys.pdg`) | error |
| Particle names instead of ids | not accepted; the error suggests the id |
| An energy pair where either value is ≤ 0 | error |
| A scalar energy (√s, CM frame) with ids that differ | warning: events are generated in the CM frame, so lab-frame η observables shift |
| A `side` quantity together with a pair-valued `beams` quantity on the same point | clash error |

**Other catalogue fields** carry over unchanged: `values`, `labels`, `tags`, `use` (1-based; applied when the quantity is not scanned), `note`.

## 4. Sweeps, settle, studies

These are unchanged in meaning from the current design, which has proven itself on `eic.toml`:

- **`[sweep] across = ["energies+beams", "pdf"]`:**
  - `+` couples quantities by index; commas or list entries form a grid;
  - `overlay = "pdf"` picks the curve quantity; other combinations become pages.
- **`[settle]`:** fixed values that are not scanned.
  - `[settle.use]` pins catalogue indices;
  - `[settle.<section>]` fixes raw keys (`[settle.gen] "PhaseSpace:pTHatMin" = 4`);
  - a clash with a quantity is an error.
- **`[study.<name>]`:** `description`, `across`, `overlay`, `pin`, plus any section override (`[study.x.run] events = 1e5`).
- **Point naming:** `<name>_<tags of applied quantities in catalogue order>`. Pages end in `_by_<overlay>`.

**New: shared generation.**
- Points that differ **only in analysis-side quantities** (types `analysis`, `option`) form one **event group**.
- The planner runs one `hep-run` per group, with every analysis variant in one `Sink::Rivet`. Rivet supports the same analysis with different options in one handler.
- A group can also replay a stored run (`[generator] tool = "store"`, [11](11_EventStore.md)). On a store, only analysis-side quantities are allowed.
- Example: a jet-radius study with three R values costs one generation instead of three.

## 5. Point identity and reuse

- **Name:** human-readable, from tags. It can collide when the base card changes.
- **Hash:** `sha256` of the canonical JSON of the generation-relevant **effective** settings:
  - base card bytes, the *effective* override set (a value equal to the base card's counts as unset, so `pth6`/`allproc`/`r10` hash like the base — 00/B15), generator tool and version;
  - events, beam ids, beam energies;
  - the replica index for seed studies.
  - The seed itself is *derived* from the hash, so it is not an input to it.
- **Equal hashes, different names:** points with the same hash but different names become **one generation** with aliases.
- **Identity seeds** (replacing `seed_step`; 00/B1, 00/B2):
  - `seed_point = f(run.seed, hash)`: a stable function, independent of sweep position and of catalogue order.
  - Pythia instance seeds are a disjoint block `Parallelism:seeds = [seed_point·k + i for i < threads]`. The planner checks at plan time that no two points in the plan share any instance seed.
  - The exact function (and whether `Parallelism:seeds` behaves as documented with chunked runs) is fixed in P1-S04/P2-S02.
  - A test-only `seed_policy = "legacy"` reproduces the old seeds for golden comparisons.
- The hash and seeds are stored in `provenance.json`.
- **`skip_existing`** skips a point only when **name, hash and a complete output** all match.
  - A `.partial` output is never "complete".
  - Same name with a different hash → error: "point X exists with different physics; use `--rerun` or bump `run.name`".
- **Replay points** hash as `sha256(store hash + analysis configuration)`.

## 6. Validation

All validation runs in `hep plan`, before any process starts.

| Check | Example message |
|---|---|
| Unknown key (with a did-you-mean suggestion) | `eic.toml:[plot] min_entry — unknown key (did you mean min_entries?)` |
| Type, range, enum | `[run] threads = -1 — must be ≥ 0` |
| Removed or renamed key | `[yoda] — renamed to [plot]; run 'hep config migrate eic.toml'` |
| Cross-field | `plot.merge = "yodamerge" requires a seed-only sweep` |
| Tool capability | `generator.tool = "herwig" but ThePEG has no HepMC module (hep doctor)` |
| Native-card preflight | Pythia: `hep-run --check` runs `readFile` + `init()` with 0 events. Sherpa/Whizard: syntax check where the tool offers one. |
| Resources | Missing LHAPDF set → `hep pdf install NNPDF23_lo_as_0130_qed?` |

**Schema as code.**
- Each dataclass field carries `doc`, `type`, `default`, `range`, `since`.
- Generated from it:
  - `hep config reference` (Markdown reference, replacing `configs/all.toml` and `configs/templates/`);
  - `hep config init <project>` (a commented starter file);
  - `hep config migrate old.toml` (rewrites the schema-1 `[analysis]/[yoda]/[rivpyth]/[sweep.cmnd.*]` keys).
    - Old `type = "beams"` quantities (energy pairs or √s) become `type = "energies"`.
    - A `pythia` quantity on `Beams:idA`/`Beams:idB` becomes `type = "beams"` with `side = "a"`/`"b"`.
    - `[settle.cmnd] beams = […]` becomes `[beams].energies`.
    - `[analysis]` → `[run]` + `[generator].card`; `[yoda]` → `[plot]` + `[plot.data]`; `[rivpyth]` → dropped (`threads` → `[run]`, `plugin_dir` → `[rivet].paths`, `yoda_file` stem → `[run].name`; `serial`, `generator`, `hepmc_file` and `path_literal` are removed).
    - `[settle.rivet] plugin/options` → `[rivet].analyses/options`; `[sweep.cmnd.*]`/`[sweep.rivet.*]` → `[quantity.*]` (`pythia` → `setting` with `setting` → `key`; `plugin` → `analysis`).
    - `seed_step` is dropped in favour of identity seeds.

**Transition.** Migrated files are committed **next to** the originals (`eic.v2.toml`) while the old tools are still in use (P1-S06). They replace the originals at P4-S06, and the `.v2` suffix is dropped in P10-S01.

## 7. The resolved spec (hep → hep-run)

One file per event group: `results/<project>/points/<group>/run.toml`. Everything is explicit. There are no `use` indices, `extends`, sweeps or relative paths.

```toml
[meta]
schema = 2
point  = "eic_5x41_em_NNLO"
hash   = "sha256:4c1e…"
origin = "configs/PhotoProduction/eic.toml --study pdf [3/4]"

[run]
events = 1000000
seed = 270405
threads = 20

[run.seeds]
point    = 83920417
instances = [83920417, 83920418, …]      # rendered as Parallelism:seeds

[source]
kind = "pythia"                           # pythia | store | stream
cards = ["/…/photo_ep.cmnd", "/…/eic_5x41_em_NNLO/point.cmnd"]
# kind = "store";  input = "/…/points/eic_5x41_em_NNLO/events"     (index-driven replay)
# kind = "stream"; inputs = ["/tmp/hekit-…/events.hepmc"]           (FIFO/file from an external generator)

[output]
dir     = "/…/points/eic_5x41_em_NNLO"
yoda    = "analysis.yoda"                 # written as .tmp, renamed on success; analysis.partial.yoda if stopped
summary = "run.summary.json"              # merged σ, counts, seeds, warnings → provenance.json

[[sink]]
kind = "rivet"
analyses = ["photo_eic:R=0.4", "photo_eic:R=1.0"]
paths = ["/…/build/analyses/PhotoProduction"]
xsec = "generator"
weights = "nominal"
dump_every = 100000                       # only for re-entrant analyses
check_beams = true

[[sink]]
kind = "module"
name = "mymodule"
library = "/…/build/modules/PhotoProduction/libhekit_mymodule.so"
options = { window = 0.010 }

[[sink]]
kind = "store"
dir = "/…/points/eic_5x41_em_NNLO/events"
compression = "gz"

[status]
fd = 3
heartbeat_ms = 500
```

`hep-run` validates only the structure (required keys, types). It knows nothing about studies. This removes the duplicated config logic (00 F2).

## 8. Dependencies

- Reading TOML: standard-library `tomllib`.
- Writing TOML (resolved specs, migrations): **`tomli_w`** (tiny, pure Python). It is added to the venv in P0-S02 (Q5 answered yes).
- The resolved-spec structure is also described by a JSON Schema (`hekit/plan/spec_v2.json`), which the Python and C++ tests share.
- C++ side: `toml++` (already used).
