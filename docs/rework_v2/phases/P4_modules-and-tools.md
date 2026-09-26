# P4 — Modules and the other tools

| Status | Steps | Depends on | Ends with | Updated |
|---|---|---|---|---|
| **in progress** | 3 | P1 (S1), P3 (S2–S3) | Lambda as a plain program next to its Rivet twin; Delphes, Herwig, Sherpa, Whizard and MadGraph as tool folders; the generator comparison; the budget measured | 2026-09-26 |

## Goal

Breadth, now that the contract is proven:

- project programs through the module kit;
- every other installed tool, as a folder;
- a generator comparison written as a configuration (the user's own `generator_comparison.cc` stays untouched).

It closes with the measurement against the budget.

Design: [05_Tools.md](../05_Tools.md) §§1–2, 5, 8; [04 §7.2, §8.2–8.4](../04_Config.md#8-worked-translations).
Ledger: **L11–L16, L21, L24, L26**. Each tool's rows are read **before** its plugin is written.

---

## S1 — The module kit and Lambda

**Tasks**

1. **`utils/Module.hh`**, as in [05 §5](../05_Tools.md#5-the-module-kit-utilsmodulehh):
   - `Module::Job` (argv; the config TOML with a `[quantities]` table; status);
   - `job.events()` through `HepMC3::deduce_reader` (file, FIFO, gz, zst), with weights, ΣW and
     count;
   - σ from the sidecar, or else the last event (L2);
   - `RootOut`/`YodaOut`, atomic with `.partial`;
   - `job.finish()` for the exit code;
   - `job.standard()`, `job.standardParts()` and `job.standardValues()` for requested standard
     configurations (V21), plus `job.hasInput()`, `job.progress()` and `job.fail()` for integrated
     programs that make their own events.
2. **`utils/Env/module/tool.toml`**: `streamable = true`, `status = "standard"`, and argv from the
   kit's CLI. Config extraction for `module` and `custom` ([04 §7.2](../04_Config.md#72-custom-tools)):
   the consumed quantities go under `[quantities]`, and `target = "<tag>"` with `key = "…"` sets a
   key directly.
3. **Rewrite Lambda** from `modules/Lambda/_v1/`:
   - `Reconstruction.hh` uses HepMC3 directly, with no `Phys`. Carry over the `charge3` sign rule
     and the `deltaPhi` wrap if they are used (01 §4).
   - `Lambda.cc` becomes a plain program writing `lambda.root`, with densities divided by the bin
     width (L21).
   - `Rivet/Lamriv.cc` shares `Reconstruction.hh`.
   - Delete `_v1/`.
4. Translate `configs/Lambda/lambda.toml` ([04 §8.2](../04_Config.md#82-configslambdalambdatoml-two-analysis-paths-and-a-module-option-sweep))
   (**approval**: `configs/`).
5. **An integrated run**: `modules/PhotoProduction/InprocJets.cc` runs Pythia and Rivet in one
   process from `pythia_cmnd` and `rivet_analyses` ([05 §5](../05_Tools.md#5-the-module-kit-utilsmodulehh)),
   with the configuration `inproc` in `eic.toml` ([04 §7.3](../04_Config.md#73-standard-configurations-for-custom-tools)).
   It applies L1–L3 itself.
6. **`tests/cxx/test_module_kit.cc`**:
   - a ten-event HepMC file;
   - the scaling rule (fill raw, scale once): exact totals;
   - `.partial` on a truncated stream.

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | `hep run Lambda/lambda single` | `lambda.root` and `lamriv.yoda` → `lamriv.root` from **the same events** (fan-out) |
| 2 | the shared histograms of the two paths | agree to floating-point tolerance: one sample, one reconstruction, two frameworks (v1's `lambda_paths` idea) |
| 3 | `hep run Lambda/lambda masswindow` | 4 points; `masstol` reaches both the Rivet option and the module config; the selected-candidate yield rises monotonically with `masstol`. `00/B40` is gone by construction. |
| 4 | `test_module_kit` | pass |
| 5 | `wc -l modules/Lambda/*` against v1's 385 lines | recorded |
| 6 | `hep run PhotoProduction/eic inproc` against the chain's `single` point, threads = 1, same point | the same card and seeds (from `provenance.json`); `photo.yoda` equal bin for bin, or the difference explained in the Log (an in-memory event vs a HepMC text round trip) |
| 7 | a `PythiaParallel` variant of the program at threads = 4 | the same seeds as the chain's point, so σ (combined over instances as in L1) equals App_Pythia's sidecar for that point to 1e-6 |
| 8 | a serial `Pythia8::Pythia` variant, run twice | identical YODAs: it read `Random:seed` from the card, not the base card's time-based `0` |

---

## S2 — File chains and event generators: Delphes, Herwig, Sherpa

**Tasks**

1. **`utils/Env/delphes/`** (L11):
   - `streamable = false`;
   - write to `.part`, then rename;
   - `filters.toml`;
   - a count check on the `Delphes` tree entries.

   A custom ROOT analysis program over `delphes.root` is the worked example
   ([04 §8.4](../04_Config.md#84-a-file-based-chain-madgraph-pythia-delphes-module); its MadGraph
   head lands in S3).
2. **`utils/Env/herwig/`** (L15):
   - `Herwig read` as a `[prepare]` step, cached by card sha256, then `Herwig run -N -s`;
   - `HepMCFile` into the FIFO;
   - `filters.toml` (`event> <n>`).
3. **`utils/Env/sherpa/`** (L12):
   - `render.py` for the YAML deep merge, written whole, and `mirror_mpi_pdf`;
   - integration as a cached `[prepare]`;
   - a relative FIFO name;
   - `filters.toml`.
4. Master mappings for both (energies, pdf, events, seed).
5. **Exports:** `delphes_tcl`, `herwig_in`, `herwig_run` (prepare on demand), `sherpa_yaml`, and
   `sherpa_results` (prepare on demand).

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | pythia → `showered.hepmc` (a file) → delphes → custom | the Delphes tree's entries equal the sidecar's `written` |
| 2 | the same chain with a FIFO into delphes | refused at plan time |
| 3 | an eic 18×275 LO MPI-off point with `tool = "sherpa"` | σ consistent with v1's measurement, 9,636 ± 782 pb (L24) |
| 4 | a `pdf` sweep for sherpa | runs; `render.py` is tested with the runner's real `Override` type (L26) |
| 5 | a Herwig point → rivet | count check passes; σ from its last event equals Herwig's reported σ |
| 6 | a rerun of rows 3–5 | the prepare caches are hit: 0 integration time |
| 7 | a custom tool with `herwig_run = true` and no herwig in `tools` | `Herwig read` runs once (cached), and the tool gets the `.run` path |

---

## S3 — Process generators, the comparison, and the budget

**Tasks**

1. **`utils/Env/whizard/`** (L13):
   - `render.py` writes the point card first, then includes the base;
   - a separate integration card;
   - `beam_structure`;
   - direct photoproduction only.
2. **`utils/Env/madgraph/`** (L14):
   - the launch script and the build/launch/unpack steps as `[prepare]` plus run;
   - the shower is a separate `pythia` tool reading the LHE (`Beams:frameType = 4`);
   - **the browser fix** (`00/B39`).
3. **Exports:** `whizard_sin`, `madgraph_proc`, and `madgraph_process` (prepare on demand).
4. **`"@generator"`** tool selection (V19). Write `configs/Comparison/generators.toml` with
   `modules/Comparison/Rivet/particle_spectra.cc` (pT, E, η, N_ch). The root-level
   `generator_comparison.*` is the user's scratch file and is not touched.
5. **Measure the budget** ([06 §3](../06_Roadmap.md#3-budgets)). Any row over 1.5× is a finding with
   its cause.
6. `bots/BOT.md` and `docs/README.md` final pass. Mark `docs/rework_v2/` as *executed* in its
   README.

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | madgraph → `unweighted.lhe` → pythia shower → rivet | runs; the count check passes |
| 2 | a whizard direct-photoproduction point | runs; σ recorded |
| 3 | `hep run Comparison/generators` | 3 points (pythia, herwig, sherpa); one Paint page per spectrum with 3 curves |
| 4 | the budget table | every row measured; the ratios recorded |
| 5 | a fresh clone + `load_hep && hep build && hep run PhotoProduction/eic single` | works end to end |

**Done when** every row of S1–S3 passes. **That is the end of rework v2.**

---

## Rollback

Each tool folder is independent: remove it and its master entries.

## Log

### S1 — 2026-09-27 — done

| Row | Result |
|---|---|
| 1 | `hep run Lambda/lambda single` (2k events, 4 threads, 90 s): `lambda.root`, and `lamriv.yoda` → `lamriv.root`, from **the same events** (App_Pythia fans out to two FIFOs); both count checks pass (2,000 = the sidecar's written) |
| 2 | The 21 histograms, 3,906 values and errors: **equal to YODA's written precision** (at most half a unit in the 7th significant digit, which is all `%.6e` keeps), with the same empty bins. Rivet's own σ and ΣW read back as 7 digits for the same reason. |
| 3 | `masswindow`: 4 points; `masstol` reaches both paths (`mass_tolerance` in the module's config, `Lamriv:MASSTOL=…` for Rivet), which agree to 1e-7 at every point. **The validated yield rises monotonically, 277 → 463 → 770 → 1,309 per event. The selected yield does not: it stays at 25–27 per event.** On Ne–Ne events the one-to-one matching is bounded by the protons (`reserved_protons` = 2), not by the window. The row was written with pp in mind; the validated set is what measures the cut here. |
| 4 | `test_module_kit`: pass (the config view, events, ΣW, σ from the last event or a sidecar, scale once as a density, the report, a truncated stream) |
| 5 | `modules/Lambda`: **252 lines** (Lambda.cc 103, Reconstruction.hh 149) against v1's 385 (225 + 160); Lamriv 149 |
| 6 | `eic inproc` against `single`, 1 thread, 5k events: the same card and seed (794,907,795), and **all 17 objects equal bin for bin**. The only text differences are 14 `ScaledBy` lines, at 6e-10: σ/ΣW, the chain's σ having gone through the HepMC text. |
| 7 | At 4 threads, 20k events: the same four seeds; InprocJets' σ **equals the sidecar's exactly** (73,127.656495 pb, relative difference 0), with 19,998 events written by both |
| 8 | The serial engine, run twice: **byte-identical YODAs**. The point card's `Random:seed = 794907795` overrides the base card's time-based `0`. |

**Deviations and findings:**
- **Seeds follow the generator, not the whole point** (02 §7). Row 6 needs the chain and the
  integrated program to share events, but a point's identity includes every tool, so `inproc`'s
  seeds differed from `single`'s. The basis is now the seeded steps' identity: card lines without
  comments, base cards, binary, replicas, threads and events. Within a plan a clash still moves up
  (V9); across configurations the same generator setup gives the same events. The identity carries
  the rule, so every point reran once. `test_sweeps.py`'s disjointness test now checks each plan,
  and that `single`, `pdf`'s NNPDF23lo point and `inproc` share seeds.
- **Found by the masswindow run: a swept analysis option broke the plot stage.** `plot.py` took
  the object paths from the first point's YODA, and every other point has its own variant
  (`/Lamriv:MASSTOL=0.1:…/x`). Pages are now keyed by the option-free path, and each point's
  variant is a curve, as in v1. The yoda backend voids per variant. Regression test added.
- **The module kit** (05 §5, "as built"): the CLI takes `--x=v`; `RootOut` is compiled when ROOT's
  headers are on the path; there is no `YodaOut`; the report `<output>.json` travels with its product
  and is the count check (`json:events`); `{input_sidecar}` is passed only for a file chain, because
  App_Pythia writes its sidecar after closing the FIFO.
- **`utils/Env/module/`** is the fifth standard tool folder. Every kit program always gets a config.
- **The Makefile** ignores a trailing `(…)` note on the `// requires:` line, as the 05 §5
  examples write it (`// requires: root   (Module.hh adds hepmc3 toml)`).
- **Lamriv's `.info` has no `Beams` line.** The Lambda card is Angantyr Ne-20 on Ne-20, which
  `[[p+, p+]]` would refuse. v1's `RESERVED = 2` (pp's 2 × Z) is kept as v1 had it.
- `lambda.toml` also carries v1's other studies (costheta, cuts_grid, sets, energy, replicas). The
  pages come from `lamriv.yoda`; `lambda.root` is for ROOT users.
- **The Lambda chain runs at about 22 events/s** at 4 threads (Angantyr Ne–Ne; both analyses pair
  O(p × π⁻)), so the default 20k events at 16 threads is minutes, not seconds.
- TLatex: a sign after `^`/`_` is grouped (`\pi^-` → `#pi^{-}`).
- Tests: `test_module_kit` (C++), `test_module.py` 4, `test_plot_stage.py` +1, `test_plot.py` +1,
  and the slow `test_modules_p4.py` 4 (rows 1–2, 6–8). `make test` 142; `make test-slow` 12.
