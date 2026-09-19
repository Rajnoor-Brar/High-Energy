# 04 — Generator adapters

**Scope:** each generator is driven through a Python **adapter**. The adapter turns a point into:
- native cards;
- zero or more *prepare* stages (integration, process build);
- one *generate* stage whose events reach `hep-run`.

Pythia is the exception: it runs inside `hep-run` itself.

## 1. Adapter interface

```python
class Adapter(Protocol):
    tool: str                                   # "pythia", "sherpa", ...
    def probe(self, env) -> Capabilities         # version, event output, native rivet, seed/threads support
    def validate(self, point) -> None            # key syntax, beam support, capability checks
    def render(self, point, workdir) -> Cards    # write point card(s); return paths + sha256
    def prepare(self, point, cache) -> list[Stage]   # cached, seed-independent steps
    def generate(self, point, sink_fifo) -> Stage    # argv, env, cwd, progress parser, expected outputs
```

A `Stage` is data:
- `name`, `argv`, `env`, `cwd`;
- `log` path;
- `parser` (06 §4);
- `timeout`;
- `produces`.

The supervisor (06) runs every stage the same way.

**Prepare cache.** Integration grids, Herwig `.run` files and MadGraph process directories are reusable across seeds and event counts.
- They are stored under `results/<project>/.cache/<tool>/<prep-hash>/`.
- `prep-hash` covers the rendered card *minus* `seed` and `events`, plus the tool version. The volatile
  keys are the tool's own spellings **plus** the generic `seed`/`events`/`nevents`/`n_events`: the hash
  is taken over the *rendered* card, and an adapter that writes `seed =` while its native language says
  `RANDOM_SEED` would otherwise give every replica its own grid.
- An entry is usable only once `prepared.json` is written — last, and only when the outputs the stage
  promised really exist. A directory without it is an interrupted prepare, not a usable grid (same rule
  as the store index, 11 §1).
- A seed-replica study therefore integrates once. **Whether a prepare stage is still needed is decided
  when the run reaches the point, not when the plan is built**: in a seed study the first point fills
  the cache and every later one skips it, which cannot be known in advance.

## 2. Capability matrix (this machine, 2026-09-17)

| | Pythia 8.317 | Sherpa 3.0.5 | Whizard 3.1.8 | Herwig 7.3.0 | MadGraph |
|---|---|---|---|---|---|
| Runs as | in `hep-run` | subprocess | subprocess | subprocess (`read` + `run`) | subprocess, then Pythia in `hep-run` |
| Base card | `.cmnd` | `Sherpa.yaml` | `.sin` | `.in` | `proc_card.dat` + run-card overrides |
| Events out | in-memory → sinks | HepMC3 ✓ | HepMC3 ✓ | **✗ needs ThePEG `--with-hepmc`** | LHE → Pythia |
| Native Rivet | (our sink) | ✓ `libSherpaRivetAnalysis` | ✗ | **✗ needs ThePEG `--with-rivet`** | via Pythia |
| Threads | `Parallelism:numThreads` | 1 per process (MPI for integration) | 1 (OpenMP for integration) | `-j N` forks N processes | `nb_core` for the ME |
| Prepare stage | — | integration (`Results/`) | integration (grids) | `Herwig read` → `.run` | process build + `launch` |
| Seed | `Parallelism:seeds` (identity block, 03 §5) | `RANDOM_SEED` | `seed` | `run -s` | `iseed` |
| σ source | merged `sigmaGen()` | HepMC `GenCrossSection` | HepMC `GenCrossSection` | HepMC `GenCrossSection` | Pythia (LHE-weighted) |
| Photoproduction (ep) | ✓ (current) | ✓ EPA beam spectra | ✓ EPA structure function | ✓ (budnev/WW photon PDFs) | with EPA; check the model |
| **Priority** | **1** | 2 | 3 | 4 (after rebuild) | 3 |
| **Step** | P2-S04 | P7-S03 | P7-S04 | P7-S06 → P7-S07 | P7-S05 |

**"Same physics" across generators (Q7).** Which EPA/WW parameters, Q²max, photon PDF, pTHatMin analogue and MPI settings count as equivalent to `photo_ep.cmnd` is decided in P7-S02, before the Sherpa and Whizard adapters are written. PhotoProduction is a test bed (D20), so the comparison is documented rather than gated.

**Store pseudo-generator.** `tool = "store"` replays a HepMC3 store ([11](11_EventStore.md)). It has no cards, no prepare stage, and no generation-side quantities; σ, beams and weights come from the store index (P5-S02).

## 3. Pythia

**Cards:**
- The base `.cmnd` is untouched.
- `point.cmnd` holds the header (base sha256, origin), run control and overrides.
- This is exactly the current base + point design.

**Beams and energies rendering:**
| Input | Rendered settings |
|---|---|
| `ids = [A, B]` | `Beams:idA = A`, `Beams:idB = B` |
| `energies = [E_A, E_B]` | `Beams:frameType = 2`, `Beams:eA`, `Beams:eB` |
| `energies = √s` | `Beams:frameType = 1`, `Beams:eCM` |
| LHE source | `Beams:frameType = 4`, `Beams:LHEF = <file>`. `ids` and `energies` must be unset, because the LHE header defines them; setting them is a planning error. |

- Ids pass through unchanged, since Pythia uses PDG codes natively.
- **Warning:** a scalar √s with ids that differ puts events in the CM frame, so η-dependent analyses shift (a known pitfall). Emit this warning.

**Rendered run control:**
- `Main:numberOfEvents`, `Parallelism:numThreads`;
- `Random:setSeed = on`, `Random:seed`, and `Parallelism:seeds` (a disjoint per-instance block derived from the point identity; 00/B1, 00/B2);
- `Next:numberCount = 0` (progress comes from the status stream);
- `Init:showChangedSettings = on` (goes to the log, not the terminal).
- `Print:quiet` is **not** forced: the banner and `stat()` go to `logs/generate.log`, and the dashboard extracts σ from them.

**`processAsync`:** set by the sink concurrency mode (05 §3), never by the user card. If the card sets it, that is a validation error.

**Preflight:** `hep-run --check <spec>` runs `readFile` for every card, then `init()`, then exits without generating: 0 = OK, 1 = card error, 3 = init failure (06 §3.3). This catches, for example, `ProcessType = 2` init failures in `hep plan --check`.

## 4. Sherpa

**Cards:**
- `point.yaml` = the base YAML deep-merged with overrides. Sherpa also accepts `'KEY: value'` on the CLI; the file is used instead so provenance is complete.

**Rendered settings:**
| Purpose | Setting |
|---|---|
| Beam ids | `BEAMS: [A, B]` (PDG codes, native) |
| Beam energies | `BEAM_ENERGIES: [E_A, E_B]`; a scalar √s becomes `[√s/2, √s/2]` |
| Seed | `RANDOM_SEED: n` |
| Events | `EVENTS: n` |
| Output | `EVENT_OUTPUT: HepMC3_GenEvent[<fifo stem>]` |

**Integration:**
- The prepare stage runs `Sherpa -f point.yaml -e 0` in the cache directory.
- The generate stage points `RESULT_DIRECTORY` at the cache.

**Modes:**
| `rivet.mode` | What happens |
|---|---|
| `inprocess` (default) | HepMC3 → FIFO → `hep-run` (`Source::Stream`). Same sinks, same σ and provenance policy. |
| `native` | `ANALYSIS: Rivet` with `RIVET: {ANALYSES: [...]}`. Faster for Rivet-only runs, but module, store and Delphes sinks are unavailable. The progress parser still works. |

**Weights:** on-the-fly scale/PDF variations arrive as HepMC weights. `rivet.weights = "all"` keeps them.

## 5. Whizard

**Cards:** `point.sin` = the override block (`seed = …`, `n_events = …`, beam settings) followed by the base `.sin`.
- The base must not hard-code `seed` or `n_events` *after* the insertion point. The adapter checks this with a simple parse and rejects it otherwise.

**Beams and energies:**
- Ids → `beams = <name A>, <name B>`. Whizard uses model particle names, so the adapter maps PDG → name from the active model file (e.g. 2212 → `p`, 11 → `e1`). An id with no name in the model is a planning error.
- An energy pair → `beams_momentum = E_A, E_B` (with `sqrts` derived for the log).
- A scalar → `sqrts = √s`.

**Output:**
- `sample_format = hepmc` with `$sample = "<stem>"`. Whizard appends `.hepmc`, so the FIFO is created as `<stem>.hepmc`.
- Whizard is parton-level unless its shower/hadronisation interface is enabled in the base card. The adapter reports which one is active (`?hadronization_active`).

**Prepare:** integration in the cache directory. The generate stage re-reads the grids (`?rebuild_grids = false`).

## 6. Herwig

**Prerequisite (decision P7-S06):** rebuild ThePEG with `--with-hepmc=$HEP_INSTALL/hepmc3 --with-rivet=$HEP_INSTALL/rivet`, then rebuild Herwig. The adapter (P7-S07) is written only after the rebuild. Until then `hep doctor` reports Herwig as "run-only (no event output)", and planning a Herwig point fails with that hint.

**Cards:** `point.in` = the base `.in` + `set` lines + an output handler insertion + `saverun <name> /Herwig/Generators/EventGenerator`.

**Beams and energies:**
- Ids → `set /Herwig/Generators/EventGenerator:EventHandler:BeamA /Herwig/Particles/<name>` (and `BeamB`). The PDG → ThePEG particle-name map is taken from Herwig's particle repository.
- Energies → the luminosity function's per-beam energies (`BeamEMaxA/B`). A scalar √s → `Energy`.
- The exact interface names are verified against Herwig 7.3 during implementation, with golden-file tests.

**Stages:**
1. Prepare: `Herwig read point.in` (cached `.run`).
2. Generate: `Herwig run <name>.run -N <events> -s <seed>`.

**Threads:** `-j N` forks N processes, each with its own output.
- Design: N FIFOs, and `hep-run` (`Source::Stream`) accepts several inputs and reads them in rotation.
- Seeds are offset per job by Herwig itself. The adapter records this.

## 7. MadGraph (+ Pythia shower)

**Stages:**
1. **Prepare:** `mg5_aMC proc_card.dat` → process directory (cached by the proc-card hash).
2. **Matrix element:** a `launch` script with `shower=OFF`, `set nevents` and `set iseed`, plus overrides (`run_card.<key>`) → `unweighted_events.lhe.gz`. Beam settings are rendered as:
   - **Ids:** mapped to `lpp1/2`, the beam type (±2212 → ±1 PDF beam; ±11 → 0 without, or with EPA, per the base card). An id with no `lpp` mapping is a planning error.
   - **Energies:** `ebeam1/2`. A scalar √s → `ebeam1 = ebeam2 = √s/2`.
3. **Shower:** decompress the LHE (Pythia gzip support is build-dependent, so do not rely on it). Then run `hep-run` (`Source::Pythia`) with the `[generator].shower` card, `Beams:frameType = 4` and `Beams:LHEF`.

**Matching/merging** settings are in the shower card. The adapter only warns if a multi-jet proc card has no merging settings.

## 8. Common rules

- **Beams:** every adapter consumes the same two inputs: `ids` (PDG codes, [A, B]) and `energies` (pair or scalar √s). The planner resolves them first, from `[beams]` and then `beams` / `energies` quantities. Ids are never taken from a native setting quantity.
  - A raw setting that writes beam keys (`Beams:id*`, `Beams:e*`, `BEAMS`, `BEAM_ENERGIES`, `lpp*`, `ebeam*`) is a clash error. Use the dedicated quantities instead.

- **Events:** external generators must emit exactly `run.events`. `hep-run` (`Source::Stream`) counts events and flags a mismatch.
- **σ:** for FIFO sources (`Source::Stream`), `Sink::Rivet` takes σ from the **last** event's `GenCrossSection` (the generator's final estimate, since there is one producer). A missing attribute is an error unless `rivet.xsec` is a number.
  - *"Since there is one producer" is load-bearing*, and P7-S01 measured it: streaming a **one**-worker store reproduces the generation's YODA exactly (39 objects, 1004 numbers), while streaming a **two**-worker store scales every histogram by the ratio between one worker's running estimate and the merged σ — 1.8 % on a 300-event test. Every external generator here is a single process, so the rule holds; a future multi-process one would have to carry its merged σ some other way.
- **Environment:** adapters locate executables through `tools.<name>.exe` (machine file), then `PATH`. They never use absolute paths from the repo.
- **Version:** `probe()` result goes into provenance. A version change invalidates the prepare cache.
