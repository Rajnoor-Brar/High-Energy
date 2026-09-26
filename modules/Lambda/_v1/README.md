# Lambda

Λ → p π⁻ reconstruction from Pythia, as a C++ module analyzer. A worked example of the framework: the
legacy `Lambda` (839 lines across nine headers plus four `main()`s) rebuilt as **one module plus one
TOML**.

## Run it

```bash
hep build --modules Lambda
```

```bash
hep run configs/Lambda/lambda.toml --study single --events 20000
```

```bash
hep proc configs/Lambda/lambda.toml --study single
```

You get `results/Lambda/points/lambda_7tev/analysis.root` — a TDirectory `Lambda` holding 22 TH1Ds,
with bin errors. `hep plot` works on the same results if you want figures instead.

## What it produces

Three **nested** candidate sets, each with the same six distributions plus a per-event count:

| Set | What it is |
|---|---|
| `unvalidated` | every (p, π⁻) pair in the event — the full combinatorics |
| `validated` | the pairs inside the mass window |
| `selected` | the greedy one-to-one matching: best mass agreement first, no track reused |

Distributions: `mass`, `energy`, `momentum`, `pt`, `pz`, `eta`. Paths are `/Lambda/<set>_<property>`,
which become `Lambda/<set>_<property>` in the ROOT file.

On 20k events at 7 TeV: 21.5 → 8.1 → 1.7 candidates per event, peak at 1.1077–1.1157 GeV
(m(Λ) = 1.115683).

## Configure it

Everything analysis-specific is in `[analyzers.module.options]` of
[`configs/Lambda/lambda.toml`](../../configs/Lambda/lambda.toml):

| Option | Default | |
|---|---|---|
| `mass_tolerance` | 0.15 | \|m(pπ) − m(Λ)\| accepted, GeV |
| `cos_theta_tolerance` | 0.0 | 0 = off; else \|cos θ* + 1\| tolerance |
| `reserved_protons` | 2 | beam protons per event, 2 × Z — **2 for pp, 20 for Ne–Ne** |
| `track_pt_min`, `track_eta_max` | 0.0, 8.0 | acceptance the tracks must pass before pairing |
| `bins`, `mass_axis`, `energy_axis`, `momentum_axis`, `pt_axis`, `eta_axis`, `count_axis` | | histogram axes |

Physics that belongs to *Pythia* is in [`lambda.cmnd`](../../configs/Lambda/lambda.cmnd), not the
TOML (D3) — including the line that makes the whole thing possible:

```
3122:onIfMatch = 2212 -211
```

With Λ decay off there is nothing to reconstruct.

## Why it is split this way

| File | Holds | Why separate |
|---|---|---|
| `Reconstruction.hh` | the physics: pairing, the mass window, cos θ*, the greedy matching | takes and returns `FourVector`s, so it needs no generator, no YODA and no framework — and `tests/cxx/test_lambda.cc` exercises every branch without running Pythia |
| `Lambda.cc` | the framework half: four verbs, options, booking, filling, scaling | the only part that knows about `Module::Base` |

The legacy version could not be tested this way: `harvestParticles` took a `Pythia8::Pythia&`, so
checking the selection meant generating events and hoping one had the case you wanted.

## What the framework does instead of the module

| legacy Lambda | now |
|---|---|
| own worker pool and collectors | `Analyzer::Modules` shards; one clone per worker |
| own ROOT `Record::Writer` | `Results::Booker` → YODA → `[proc.export]` |
| own checkpoints, heartbeat, logs | the supervisor and the status stream |
| own serial/directory/file naming | the results layout |
| four `main()` variants | one `hep run`, three studies in one TOML |
| hand-rolled TOML reading | the schema, validated before anything starts |

**It declares `threadSafe() == true`**, because it clusters nothing and shares nothing — so the analyzer
shards and the module is free on a many-threaded run. Compare `modules/Examples/ToyJets.cc`, which
must say `false` because FastJet keeps clustering state in process-wide statics (00/B31).

## Why the ROOT file is written by `hep proc`, not by the module

D7 and D14 make YODA the results format; D15 keeps ROOT out of `hep-run` entirely. A module writing
ROOT directly would put a second results format inside the event loop and contradict both.

So the run produces `analysis.yoda` — the record, which carries the annotations, is what `hep plot`
and `hep compare` read, and is what provenance hashes — and `[proc.export]` turns it into
`analysis.root` afterwards, in the half that is allowed to know about ROOT. The ROOT file is a
**derived view**: delete it, re-run `hep proc`, get it back.

The writer is `uproot`, so this works in a build with no PyROOT.

## The same measurement as a Rivet analysis

[`analyses/Lambda/Lamriv.cc`](../../analyses/Lambda/Lamriv.cc) does the same thing through Rivet.
Both are enabled in `lambda.toml`, so one run writes both into one `analysis.yoda`:

```
/Lamriv:RESERVED=2/<set>_<property>     the Rivet analysis  (Rivet puts options in the path)
/Lambda/<set>_<property>                the module
```

**They share the physics**: `Lamriv.cc` includes this directory's `Reconstruction.hh`, so a
disagreement between them is a framework defect and cannot be a difference in the reconstruction.
The build passes `-I utils -I modules/<project> -DHEKIT_WITH_HEPMC=1` to `rivet-build`, which is
what lets a plugin use `Phys` and a project's own headers.

`tests/integration/test_lambda_paths.py` (ctest: `lambda_paths`) holds the two to exact agreement —
21/21 histograms, floating-point tolerance, because it is one sample written twice rather than two
samples compared.

Drop either analyzer and the other still works. Rivet takes HepMC however it arrives — Pythia in
process here, or an external generator's FIFO if `[generator].tool` changes — and writes YODA either
way; `Analyzer::Rivet` is the same analyzer.

**What it caught: 00/B42.** Rivet's `finalize` writes a *density* (dσ/dx); `Results::Final::normalise()`
leaves per-bin integrals. The two disagreed by exactly the bin width — 125× on the mass axis, 0.25× on
p_z, 6.25× on η — with no complaint from anything, because both are plausible numbers in plausible
units. This module now divides by the bin width itself, which is also what makes its own `dσ/dx` axis
labels true. The framework-level fix touches every existing module and wants its own step.

## Known limitation

**You cannot sweep a module option** (00/B40). A `type = "option"` quantity targets a Rivet analysis
and its value never reaches a module's `configure()` — declaring one would give you several point
directories with identical numbers. To vary a cut today, edit the value or run twice with `--label`.
