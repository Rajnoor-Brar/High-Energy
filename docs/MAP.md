# Map of the implemented system

Where things are and what owns what. For how to *use* it see [GUIDE.md](GUIDE.md); for why it is
shaped this way see [rework/](rework/).

---

## 1. The two halves

| | `hep` (Python, package `hekit`) | `hep-run` (one C++ executable) |
|---|---|---|
| Owns | configuration, judgement, orchestration, output | the event loop |
| Decides | what to run, with what seeds, in what order, where it goes | nothing — it is told |
| Speaks | TOML in, terminal and files out | a resolved spec in, JSON-lines status on fd 3 |

The contract between them is deliberately narrow: `hep` writes a **resolved spec** (every value
already decided) and reads a **status stream**. Nothing else crosses. That is what lets either side
be tested without the other, and why `hep-run` links no ROOT, no plotting and no config parser.

```
hep  ──spec.toml──►  hep-run  ──status(fd 3)──►  hep
                        │
                        └── source ──► sinks ──► files
```

---

## 2. `utils/` — the C++ side (~6.8k lines)

One facade header per namespace, with submodules beside it (`Core.hh` + `Core/`). Layered, and a
lower layer never links a higher one:

```
Core ─► Status ─► Events ─► { Store, Results, ML, Phys } ─► { Source, Module } ─► Sink ─► Run ─► apps/
```

| Namespace | What it owns |
|---|---|
| `Core` | spec reading, hashing, clocks, signals, exit codes, provenance |
| `Status` | the JSON-lines stream, heartbeats, progress |
| `Events` | the per-event view: live Pythia or a lazy `GenEvent`, weights, worker and slot |
| `Store` | sharded HepMC3 writing and reading, the index, the replay queue |
| `Results` | YODA booking per worker, merging, the scaling contract, atomic writes |
| `ML` | ONNX sessions with per-worker scratch; a named feature schema |
| `Phys` | PDG data, kinematics on `FourVector`, `GenEvent` selectors, jet definitions |
| `Source` | where events come from: Pythia, a store replay, a stream |
| `Module` | the user-module interface and its `dlopen` loader |
| `Sink` | where events go: Rivet, the store, modules, the Delphes tee |
| `Run` | wires source to sinks; chunking, the concurrency mode, the summary |

`utils/apps/hep-run.cc` is the executable, and is short on purpose — everything it does is in the
namespaces above.

### Two invariants worth knowing before reading the code

- **The scaling contract.** Fills carry raw weights; scaling happens once, in `finalize`, when σ and
  Σw are known. `Results::Worker` has no `scale()` and `Results::Final` has no `fill()`, so the
  rule is the shape of the types rather than something to remember.
- **Concurrency is a property of the sink.** `Sharded` sinks hold one instance per worker and take
  no lock; `Locked` ones share one; `Serial` ones want the callback thread. `Run::Loop` asks and
  then decides, and says why.

---

## 3. `utils/python/hekit/` — the `hep` side (~17k lines)

| Package | What it owns |
|---|---|
| `config` | schema, loading, validation, migration from v1, the generated reference |
| `sweep` | quantities, studies, selection (`--study`, `--pin`, `--across`, `--overlay`) |
| `plan` | expansion to points, identity hashing, the resolved spec, stage chains |
| `adapters` | the external generators (Sherpa, Whizard, MadGraph, Delphes) and the prepare cache |
| `run` | the supervisor, transport, signals, the journal, `hep bench` |
| `term` | the live dashboard, `hep watch`, `hep events` |
| `results` | layout, manifests, comparison statistics, replica merging, `hep clean` |
| `plot` | the page pipeline and two backends (`rivet-mkhtml`, matplotlib) |
| `proc` | fits (Minuit2, RooFit, scipy) and derived histograms (RDataFrame, uproot) |
| `store` | `hep store ls|info|verify` |
| `prov` | provenance capture |
| `env` | `hep doctor`, `hep build`, `hep pdf`, `hep new` |

`cli.py` is the command tree and nothing else: subcommands are imported on demand, so `hep --help`
stays fast.

---

## 4. Where a run's files go

```
results/<project>/
  points/<point>/
    analysis.yoda              results (analysis.partial.yoda if the run was stopped)
    run.summary.json           counts, σ, seeds, mode, warnings, and `inputs` (what was read)
    provenance.json            the resolved config, hashes, tool versions, host, git revision
    events/                    optional HepMC3 store: shards + events.index.json
    delphes.root               optional, from the detector stage
    logs/                      one file per stage
  studies/[NN_]<study>/
    plots/<page>/              figures and an index
    proc/                      fits.json, proc.yoda, proc.root (optional)
  .cache/<tool>/<hash>/        prepare caches (Sherpa integration, MadGraph output)
```

The serial prefix (`01_`, `02_`) says "the Nth run", across every study.

---

## 5. The rest of the repository

| Directory | What it is |
|---|---|
| `analyses/<project>/` | Rivet plugins, built by `hep build` |
| `modules/<project>/` | user C++ modules, one shared library each |
| `configs/<project>/` | the TOML configs and their native cards |
| `tests/` | `python/` (unit), `integration/` (real binaries), `cxx/`, `golden/` (frozen fixtures), `e2e/` |
| `legacy/` | the pre-rework code and docs, frozen and tracked, never imported from |
| `docs/` | this map, the guide, and `rework/` |
| `bots/` | working notes for agents: `BOT.md` and `current_plan.md` |
| `output/scratch/` | where tests and dry runs write; never `results/` or `configs/` |

---

## 6. Finding your way in

| Question | Where to look |
|---|---|
| What does this config key mean? | `hep config reference`, or [rework/reference/config.md](rework/reference/config.md) |
| What does this command do? | `hep <command> --help`, or [GUIDE.md](GUIDE.md) |
| Why is it built this way? | the numbered documents in [rework/](rework/) |
| What was decided, and what was not? | [rework/10_Roadmap.md](rework/10_Roadmap.md) §2, and the register in [rework/steps/README.md](rework/steps/README.md) |
| What was wrong with the old code? | [rework/00_Audit.md](rework/00_Audit.md) — every finding, with where it was fixed |
| What did this step actually measure? | the Log at the bottom of its file in [rework/steps/](rework/steps/) |

The step Logs are the most useful and least obvious of these: each records what was *measured*
rather than what was intended, including the times the design turned out to be wrong.
