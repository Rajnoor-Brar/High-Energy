# Current plan

## `"default"` for plot options — **DONE 2026-09-30** (ordered by the user 2026-09-30)

"In plot options, make "default" a valid value; that is skips any configuration and lets tool
decide, such as for min_entries."

- V37: `plot.DEFAULT`; `plot.page_settings` resolves each key to the tool's own behaviour
  (`pick(name, ours, native)`: an object-level "default" wins over `[plot]`); `formats_of`,
  `backends`, `run_style` (root_style), `pages` (objects); style layers skip "default" values
  (`check_style`, `merge_style`); config.py lets "default" past the type check; the yoda backend
  reads each page's resolved ratio. `[plot.object]` values type-checked (OBJECT_TYPES).
- Docs 04 §11 table of meanings; tests in `tests/runner/test_plot.py`.

## Points at once (`parallelism`) — **DONE 2026-09-30** (ordered by the user 2026-09-30)

"Make support for run.parallelism … run multiple points in parallel", with temp files prefixed
`P001_`. Decided with the user: no prefixes (each point has its own folder), `threads` per point.

- V36: `parallelism` in `[run]`/`[run.<cfg>]` (config.py); `execute.run_points` (a thread pool of
  `run_point`s, stop-aware) and `execute.cores` (the `--plan` estimate); `status.Journal` lock;
  `watch` views with a part per point and `for_point`; prepare cache entries locked
  (`_prepare_lock`: threading lock + flock on `<entry>.lock`, stamp re-checked).
- Found on the way: `test_fan_out_writes_the_same_events_everywhere` assumed byte-identical fan-out
  outputs, which V31 (per-output writers) no longer gives under load: it now compares the events.
- Tests: `tests/runner/test_parallel.py`, `tests/integration/test_gates_parallel.py` (slow).
- Not yet: the timing measurement (the user's 100M-event zeus run held the machine).

## Seed sweeps, merged per curve (`combine`) — **DONE 2026-09-29** (ordered by the user 2026-09-29)

"Sweep at different seeds, and plot combined data against pdf, make zeus_seedSweep.toml."

- V35: `[run.<cfg>].combine = ["replica"]` (config.py, C14); `post.plan_combined` plans a stage per
  group of points differing only in the combined quantities (the merge folder, `rivet-merge -e`, into
  `<cfg>/<group>/<product>`); `post.run_combined` runs each once its points are complete; the plot
  stage draws the groups (`plot.pages` drops the combined axes). `Point.stage = "combined"` names the
  block in the views and the journal.
- `configs/PhotoProduction/zeus_seedSweep.toml`: 4 PDFs × 5 seeds at pT0Ref 3.2, `default` combined,
  `spread` one page per PDF with a curve per seed (the same seeds).
- Tests: `tests/runner/test_combine.py`, `tests/integration/test_gates_combine.py` (slow).

## Several Rivets in one process (option 2) — **DONE 2026-09-29** (ordered by the user 2026-09-29)

"Implement option two for PhotoProduction module": SISCone per thread, then Rivets on threads.

- `~/HEP` FastJet 3.5.0 patched (`utils/Env/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch`):
  SISCone's ranlux state and `Ceta_phi_range::eta_min/eta_max` are `thread_local` (L29). The second
  was found by the gate (FastJet internal error with only the generator patched). ABI unchanged, so
  Rivet/Herwig/Whizard were not rebuilt; backup `~/HEP/install/fastjet.bak.20260929`. Single-threaded
  Rivet byte-identical before/after (ZEUS + photo_eic, 20k events).
- V34: `Inproc/Analysis.hh` runs `rivet_threads` handlers, fed first-free, merged before one
  finalize; checks the patch and refuses without it (verified with the old library preloaded).
- Gate: 4 Rivets = 1 exactly (every raw sum and final bin, σ) for InProcEIC and InProcZeus
  (`test_modules_p4.py::test_rivet_threads_equal_one_rivet`). Speed, 200k photo_eic events: chain
  12 + 10 shards 29.0 s; in one process 12 + 12 Rivets 20.7 s, 10 + 14 19.3 s.
- Also: output paths with ',' or '+' are refused at plan time (they are App_Pythia's separators).

## InprocJets as App_Pythia runs Pythia — **DONE 2026-09-29** (ordered by the user 2026-09-29)

"Update the PhotoProduction module for integrated in-process rivet pythia, as per new norms and ways
to get standard configs; you can split the main program via headers into smaller chunks."

- V33: `modules/PhotoProduction/InprocJets.cc` is now `main()` only; `Inproc/Stamp.hh` (numbering,
  run info, σ: L1 L2 L28), `Inproc/Feed.hh` (bounded queue), `Inproc/Analysis.hh` (one Rivet on its
  own thread, L16; σ given at the end as a user σ), `Inproc/Engines.hh` (serial, parallel with
  processAsync = on and a converter per instance; no exit after Rivet's thread starts).
- Measured: 40k events at 12 threads, 31.3 s → 24.9 s, the same YODA to the last digit.
- Docs: 03 §4.14, 05 §15 (L28 row) and §18, 07 V33 and §8 rows. Tests: `test_modules_p4.py`
  (sidecar found when sharded), `text=True` subprocesses name utf-8 (L17).

## Sharded Rivet and a view that never blocks — **DONE, built and tested 2026-09-29** (ordered by the user 2026-09-29)

"Though pythia is configured to use 20 out of 24 threads, it uses 4% cpu" → measured (L27): one
Rivet core ~1,500 events/s, App_Pythia writer-capped ~2,200. The user said "do it" to three parts,
then "edit source … neither build now nor use a separate worktree, building and testing would be
done later".

- **App_Pythia** (`utils/App_Pythia.cc`): `processAsync = on`, HepMC formatting on the worker threads,
  one writer + lock per output; deal groups `A+B+C` (each event to the first free member); sidecar
  `written_per_output`. Old binaries treat `a+b` as a filename, so sharded runs need the rebuild.
- **`shards = K`** (V31): `config.Tool.shards`, `tools._shard` rewrites the chain (K copies, a
  `<tag>.merge` group from the folder's `[shard] merge`), the count check keyed per member, shard
  products skipped by plot/record/post. `pythia/tool.toml` `[outputs] deal = true`, `rivet/tool.toml`
  `[shard] merge = "merge"`.
- **Views** (V32): `watch._Screen` thread for every line and frame; `cli` says the verdict before `end()`.
- Tests written, not run: `tests/runner/test_shards.py`, `test_status.py` (a pipe nobody reads),
  `test_module.py`/`test_post.py` adjusted, `tests/integration/test_app_pythia.py` (deal groups),
  `tests/integration/test_gates_shards.py` (slow: sharded vs unsharded, RAW sumW and σ).
- Docs: 02 §6.1 and §10, 03 §4.17, 04 §9.1 `shards`, 05 §3.1 and App_Pythia, 06 folder keys and
  `_shard`, 07 V31, V32, L27; `bots/intent.md` T5.
- Built and tested on the user's order "edit configs, rebuild and test": eic and zeus_validation got
  `threads = 12`, rivet `shards = 10` (the user then set zeus to 20 + 20). Found and fixed on the
  way: a quantity aimed at the rivet table did not reach its shards (`tools._retarget`), and each
  shard normalised to its own last event's running σ (L28: App_Pythia writes each output one late
  and ends it on the latest σ). The user's 4 × 1M zeus run took ~8 min instead of ~43.

## The manual — **DONE** (ordered by the user 2026-09-27)

"Read docs, go over them … see if there are ideas worth implementing or taking inspiration from,
especially v1 docs, then eliminate the docs; then proper design docs … a detailed dev and user
manual."

- Read: v1's design set, GUIDE and MAP at `rework/v1-final` (docs/rework, post_rework, the step
  logs), `docs/rework_v1/`, and all of `docs/rework_v2/` with its phase logs.
- Ideas and loose ends → `bots/intent.md` (T1–T4 throughput, U1–U9 commands, C1–C4 config, P1–P2
  provenance, physics set-ups, F10–F14). None implemented.
- Removed: `docs/rework_v1/`, `docs/rework_v2/`, `docs/GUIDE.md` (V30; git keeps them).
- Written: `docs/README.md` and `docs/01_Philosophy` … `07_Record` (the record keeps the brief
  verbatim, V1–V30, L1–L26, F1–F14, v1's cited 00/Bn and Dn, R1–R7, the verified gates, the budget,
  the glossary). The code's citations were rewritten to the new pages; `tests/runner/test_docs.py`
  holds the manual to the code.
- Also on 2026-09-27, before it: the gutters (V29: `y_gutter = g` → (1 + g) × max; `0`/"default" →
  the tool's own range).

## rework v2 — **EXECUTED** (ordered by the user 2026-09-26; P0–P4 done 2026-09-27)

The plan was `docs/rework_v2/` (now in git history: `git log --all -- docs/rework_v2`); its
decisions, ledger and gates are in `docs/07_Record.md`.

- Revised on the user's order "do not be afraid to overhaul everything and scrapping entire utils":
  **P0 deletes all of `utils/`, CMake, `legacy/`, v1 tests and v1 design docs** (tag `rework/v1-final`
  first). Nothing is ported as code; v1 is consulted with `git show rework/v1-final:<path>`.
- The new C++ is `utils/Status.hh`, `utils/Module.hh`, App_Pythia, App_yd2rt and Paint. The Python
  runner is a flat package in `utils/Env/runner/`. Modules are plain programs. Identity is per
  point, with no shared generation. YODA plotting is `rivet-mkhtml`.
- V21 (user): custom or module tools may request standard tools' rendered configs with
  `<tool>_<export> = true` (`pythia_cmnd`, `rivet_analyses`, …). They get absolute paths under
  `[standard.<key>]` in their config, which is what makes integrated in-process runs possible.
  The mechanism lands in P1 S2; the other tools' exports come with each tool in P4.
- Execution protocol: 06_Roadmap.md §2.
- **P0 — Clean slate: done** (`8daff46` plan, tag `rework/v1-final`, `0c3df8f` S1, then S2).
  The v1 baseline is 1,455 events/s (50k events, 20 threads). The user's edits are in `stash@{0}`;
  untracked leftovers are in `output/_v1/`.
- **P1 — One chain: done.** App_Pythia passes both gates (reference byte-identical, σ at 4 threads
  to 1.3e-8). The runner core runs a point byte-identical to the hand chain, failure injection never
  hangs (SIGPIPE is never the cause), and the live view and `hep watch` work.
- **P2 — Sweeps: done.** The counts gate passes for all 12 legacy cases; C9/C10 are in; reruns
  spawn 0 processes; eic and zeus are fully translated; points.json lists every point.
- **P3 — Results and plots: done.** yd2rt, Paint (legacy ranges and voids 17/17), plot.py with
  `--only plot`, the yoda backend (mkhtml, same pages), `post` (replicas merged: 3 × the entries),
  `docs/GUIDE.md`. The style review (S2 task 3) became P5 S2: mkhtml's look. Runner size
  3,073 vs 2,000 budget (1.54×): a finding for P4 S3.
- **P4 — Modules and the other tools: done.** S1 module kit + Lambda + InprocJets (seeds follow
  the generator); S2 Delphes/Sherpa/Herwig with cached [prepare] steps; S3 Whizard, MadGraph, the
  @generator comparison (configs/Comparison), the budget (code 6,470 lines = 1.24× budget, 0.26×
  v1; runner, headers and tests over 1.5×, causes in 06 §3), Geant4 made buildable
  (`// requires: geant4`) after the user asked to check ~/HEP/install.
- **P5 — the user's additions (2026-09-27): done.** `.complete`/`provenance.json` in output/,
  plots/root and plots/yoda, one block per finished point, a `pre` stage, the sweep merged into
  plots/root/<cfg>.root (App_yd2rt --merge; the `plotmerge` post tool), `hep plot` (a
  configuration, or any YODA/ROOT files). S2: Paint's pages look like rivet-mkhtml's. S3: the style
  is TOML: utils/Apps/Paint/base.toml under [plot].root_style, [plot.style] and per-object style.
  S4: backend = "both" / ["root", "yoda"] draws both page sets in one run.
- **Rework v2 is executed.** Open with the user: whether to write a Geant4 simulation module.
---

# v1 (finished) — the working plan as it stood at `rework/v1`

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P5-S03 (replay equivalence, `hep events`) — done. **Phase P5 is complete.**

Both rows measured. The equivalence is **exact**, not "to rounding": a replayed store gives a YODA
identical to the generation's (1004 numbers, χ² = 0), because the same events go through the same
analyzers in the same order.

`hep events` shows a store, any HepMC3 file, or a config (which generates a few events into a scratch
store first — one renderer, one data path). Tables with particle names, `--tree`, `--final`, `--hard`,
role colours, and a compressed shard is streamed through `zstd -dc` and cut off one event past the
last one asked for, so looking at three events never costs more.

## Just finished — P6-S01 (sharded Rivet and the concurrency modes) — done

Serial and sharded analyse the **same 50 000 events** and write YODAs that are **identical to the
precision YODA writes** — 53 of 55 objects, `rtol = 0`. σ and sumW are exactly equal. Sharded is
**1.67x faster on four threads**.

**Two findings, both recorded in the audit.**

- **00/B31 — jet clustering cannot be sharded.** SISCone keeps its clustering cache
  (`stored_siscone`, `stored_plugin`, `stored_particles`) and its RNG (`local_ranlux_state`) in
  process-wide statics in *every* FastJet build, and this FastJet is built without
  `FASTJET_HAVE_LIMITED_THREAD_SAFETY` besides. A race changes the jets rather than crashing.
  `photo_eic` runs kT, anti-kT and SISCone, so it always runs serially; `auto` refuses before the
  first event and says why, and an explicit `sharded` stops right after `init()` if a `FastJets`
  turns up. The equivalence had to be measured with a jet-free analysis instead.
- **00/B32 — an analyzer exception would have called `std::terminate`.** `PythiaParallel` runs the
  callback on its worker threads in *both* modes (`processAsync = off` only adds a mutex), so a
  Rivet error mid-run was unwinding through `std::thread`. Both sources now catch at that boundary.

Also static: **`fill` merges, `set` does not** — `MC_XS` is re-entrant and still has one object it
`set()`s from the per-event running σ, which no merge can reconstruct. That is the rule P8-S01 has
to follow for module results.

## Just finished — P6-S02 (shared generation for analysis-only variants) — done

The planning half had worked since P1-S05; the **plotting half had not**, and testing the chain end
to end is what found it.

**A two-member page was drawing four curves.** `select.curves_for` expanded *every* variant it found
in a point's file. That is right when one point holds several radii, and wrong the moment several
points **share** one generation — the shared YODA then holds every variant and each point claimed
all of them. Nothing had ever asked what came out of the far end: the planner grouped correctly, the
analyzer booked both variants, and the page quietly doubled them.

Fixed by giving `PointFile` the point's own `analyses`; a point that declares one takes only that.
The legend stopped repeating itself too ("R = 0.4 (R=0.4)" → "R = 0.4").

Rows: `hep plan --study radius` → 1 group, 3 variants (and the `pdf` study is *not* grouped, as a
control); one point directory whose YODA carries both variant paths and one `/_EVTCOUNT`; `hep plot`
→ 2 curves.

## Just finished — P6-S03 (`hep bench`) — done. **Phase P6 is complete.**

Four legs — generation only, generation + analyzers serially, the same sharded, and a replay — then a
recommendation. On PhotoProduction at 1 000 events:

```
  generation      0.18s        5523 ev/s
  serial          0.75s        1327 ev/s
  sharded     refused: photo_eic clusters jets, which cannot be done from several threads
  replay          0.52s        1916 ev/s

  the analyzers are 76% of a serial run's wall clock
  recommended: [run].mode = "serial"
```

**Assumption 01 A4 is now answered with a number**: Rivet's cost is not merely comparable to
Pythia's, it is about **three times** it. The assumption was right, and P6-S01's finding is what
makes it moot here — the analysis that costs the most is the one that cannot be shared out.

`recommend()` asks *is it allowed?* before *is it faster?*, and is a pure function of three timings
so the whole table is 15 unit tests. Verified in the positive direction too: `MC_FSPARTICLES` on
four threads measures 1.91x and recommends `sharded`.

## Just finished — P7-S01 (external adapter framework and prepare cache) — done

A stand-in generator now goes through the whole pipeline: prepare → generate into a FIFO → `hep-run`
reading it as `Source::Stream`. Its events come from a real store, so the YODA out of the FIFO is
**identical** to the Pythia run that wrote it (39 objects, 1004 numbers). A two-seed study prepares
**once**.

**Two defects, both found by running it.**

1. **00/B33 — `hep-run --check` on a stream hung forever.** Opening a FIFO for reading blocks until a
   writer appears, and a preflight never starts one. Every external-generator run would have hung
   before generating anything. `initialise()` now validates inputs without opening them; the readers
   start in `run()`.
2. **A seed study prepared once per point.** The chain is built at plan time, when the cache is empty
   for every point; whether a prepare step is still needed is a question about *now*. Nothing marked
   the cache ready either.

Also: streaming a **two**-worker store scales every histogram by 1.8 %, because a stream takes σ from
the last event and that is one worker's running estimate. 04 §8's "since there is one producer" is
load-bearing, and now says so.

## Just finished — P7-S02 (cross-generator photoproduction) — done. **Decision D-Q7 recorded.**

Sherpa 3.0.5 is installed here, so the cards were **run**, not just written.

**Decision.** Sherpa: match every knob that has an equivalent. The photon PDF matches *exactly* —
Pythia has only one (`PDF:GammaSet` is `min=max=1`, CJKL) and Sherpa's CJK library has CJKLLO. Two
knobs have no counterpart and are written into the card: the pT regulator (pT-hat vs clustered jet)
and `pT0Ref = 3.2` (Amisic is a different model). **Whizard: deferred** — its manual says there is no
photon structure function and `pdf_builtin_photon` throws, so it can only do *direct*
photoproduction, and 00/B30 showed the reference's direct part is empty.

**Measured**, 18×275, matched LO, resolved, MPI off, same proton PDF, 6 GeV cut:
Pythia **11 950 ± 34 pb** vs Sherpa **9 636 ± 782 pb** — ratio **0.81 ± 0.07**, residue dominated by
the cut-definition row.

**Three findings handed to P7-S03/S04**

1. Sherpa needs `MPI_PDF_SET` as well as `PDF_SET`; the MPI model reads its own key and otherwise
   falls back to `PDF4LHC21_40_pdfas`, which is not installed — the run then dies naming a PDF the
   card never mentions.
2. `MI_HANDLER: Amisic` produced **0 events in 768 s** for this process; `None` produced 2 000 in 4 s.
3. Beam order is proton-first in both cards: Sherpa's own example puts the lepton on beam 1, which
   mirrors every η distribution (the 00/B26 trap, harder to spot across generators).

## Just finished — P7-S03 (Sherpa adapter) — done

Sherpa is installed here, so every row was measured against the real binary.

- **Point**: a 200-event Sherpa point runs end to end — integrate (75 s, cached), generate into the
  FIFO, `hep-run` reads it as `Source::Stream`, `photo_eic` writes a YODA. σ = 9 452 pb, consistent
  with P7-S02's standalone 9 636 ± 782 pb.
- **Cache**: two seeds → **one** integration, one entry, one `prepared.json`.
- **Modes**: `native` and `inprocess` agree on σ **to 1e-6** — different code on both sides of the
  seam, the same events.

**Four defects, all found by running it.** The prepare stage looked for a card nothing wrote; the
runner overrode every stage's `cwd`, so the integration filled the point directory (`Stage` now
carries `cwd` and `env` — `env` earned its keep at once, for native mode's `RIVET_ANALYSIS_PATH`);
`EVENT_OUTPUT` must be *relative* and takes the whole filename, so the generator wrote 3.2 MB to the
wrong name and exited 0; and the planner and runner computed the cache key with different versions,
so the grid and the marker went to different directories and every run re-integrated.

**And one that fell out of the third: a chain could hang for ever.** `hep-run` sat in `open()` on a
FIFO no one would write to. New rule: when every producer has exited **successfully** and an
`analyse` stage is still running and idle past the grace period, stop — it can never receive
anything. Only for *successful* producers, because a failed one already gives a better answer.

## Just finished — P7-S04 (Whizard adapter) — done

Both rows run against the real Whizard 3.1.8: a toy `e+e- → u ubar`, and the ep card D-Q7 static on.
A two-seed study compiles and integrates **once** — for Whizard that means not rebuilding the
matrix-element library, the dominant cost.

**Two properties of Whizard that bite immediately, now pinned by tests.**

1. **It writes no cross-section into HepMC3** — no `C` record at all, verified by reading the file.
   The run had been quietly producing a YODA normalised by **zero**. 04 §8 already said that must be
   an error; nothing enforced it. `RunRecord` now carries `xsec_known` and `Analyzer::Rivet` refuses,
   naming the remedy.
2. **Its EPA record has no scattered lepton**, so `photo_eic`'s `DISKinematics` aborts on it. Pythia's
   and Sherpa's EPA records keep the lepton — this is Whizard's alone.

**The card itself had to be taught four things**, each found by a failed run: `epa_mass` defaults to
zero and that is fatal; a flavour alias may not mix masses (`ms = 0.095`, u and d massless); the
process's incoming order must match the beam order; and the base may not assign what the plan owns,
because SINDARIN runs it *after* the point card.

`Stage` gained `writes` — the integration needs a card without the generation lines, and Whizard's
`--execute` runs before the card rather than after.

## Just finished — P7-S05 (MadGraph adapter) — done

`e+ e- → mu+ mu-` runs end to end against the real MadGraph 3.7.3: build the process directory,
launch to an LHE, unpack it, and Pythia showers it **inside `hep-run`**. 100 events, σ = 2 016 pb
from the LHE header. A second run reuses the process directory, and the *planner* drops the build
stage once the cache entry is ready.

**This is the adapter that hands over a matrix element, not events**, so there is no FIFO and the
spec's `source.kind` is `pythia`. Everything else follows: four phases instead of two, because a
file must be finished before anything reads it (`base.Stage` gained a `phase`, and `STREAMS = False`
puts `hep-run` in a later one).

**Three defects, all found by running it.** The prepare stage wrote `group.card` — the *Pythia*
shower card — so MadGraph got a file with no `generate` line and said "No model found"; the spec
claimed `source.kind = "madgraph"`, which `hep-run` rightly refused; and the preflight ran
`hep-run --check` before the LHE existed, so Pythia failed to initialise on every MadGraph point.

## Just finished — P7-S06 (decide the Herwig rebuild) — done. **D-Q6: later**, user sign-off.

The useful part was the diagnosis. 01 §4 recorded the symptom as a missing dependency; it is not.
HepMC3 and Rivet are installed and in daily use. **ThePEG was configured `--with-hepmc3=`, an option
it does not recognise** — it wants `--with-hepmc=` — and `--with-rivet` was never passed, so its own
config.log says both supports are *disabled* while the headers sit installed.

So "can Herwig work here?" became "a rebuild with two corrected flags", and those commands are in
the decision record. The user chose **later**: Herwig is priority 4 of 5 and nothing depends on it.

**P7-S07 is `blocked`, not `todo`** — it is ready except for the rebuild, and a reader should not
pick it up expecting to start.

## Just finished — P7-S08 (external Delphes) — done. **Phase P7 is complete** bar the blocked S07.

200 events → `delphes.root`, read back with uproot: 200 entries and the `Jet` branches. The Rivet
analyzer still ran on the same events — the tee is a tee — and `delphes.json` beside the ROOT file names
the card, its sha256 and the point's identity.

**The design assumed a FIFO and that cannot work.** `DelphesHepMC3` sizes its input and *skips
anything whose length is zero* (`readers/DelphesHepMC3.cpp:160-169`), which a FIFO always is —
so it opened the pipe, decided it was empty, exited, and `hep-run` died writing into a closed pipe.
The tee now writes a regular file and Delphes runs in the phase after, like MadGraph's LHE: a tool
that seeks cannot be streamed to.

**And the failure row found another**: Delphes creates the ROOT file *before* reading the card, so a
bad card left a `delphes.root` that opened, contained nothing and looked like a result. Written as
`.part` and renamed on success now (D22).

## Just finished — P8-S01 (module API, YODA results layer, module analyzer) — done

A user C++ module is `dlopen`'d, books YODA per worker, and its objects land in the **same**
`analysis.yoda` as Rivet's. All four rows measured:

- **Exact totals**: serial and sharded give identical objects (every `sumW` equal to 1e-12). Read as
  *the merge is exact* — 1 vs 4 vs 20 threads are different **event sets** at a fixed seed, so equal
  integrals there would mean something was wrong.
- **Scaling**: the normalised histogram integrates to 71 632.737 pb against σ = 71 632.735 pb —
  3 × 10⁻⁸, which is floating-point summation.
- **Dumps**: non-empty, and deliberately without module objects (they are unscaled mid-run).
- **Plotting**: `hep plot --points` renders them.

**The scaling contract is a type.** `Results::Worker` has `fill` and no `scale`; `Results::Final` has
`scale` and no `fill` and is only reachable from `finalize`. So the three mistakes `legacy/Record`
made — scaled during the run, scaled twice, scaled by a σ that was not final — are not expressible.

## Just finished — P8-S02 (Phys namespace) — done

`Phys` replaces `legacy/utils/Physics/` on `HepMC3::FourVector`, so nothing in the physics layer
links ROOT or converts a particle out of the event it is already holding. Five headers, a facade,
and 167 checks in the new ctest test `phys`.

**Both rows measured.** The PDG table is checked against Pythia's own `ParticleData` — 13/13 rows
agree on mass, charge and name — and perturbing one mass by 1e-4 fails the row, so it is a live
comparison rather than a tautology. `jetDefinition("antikt:0.4")` matches a hand-written
`fastjet::JetDefinition` through FastJet's own `description()`.

**Three defects, 00/B34-B36.**

- **B34** — `Physics::particle(-211).charge3` was **+3**: the lookup resolved an antiparticle to its
  particle's row and handed back that row's charge, so every negative code came out positive.
- **B35** — the Δφ guard the step asked for, and it is **not legacy-only**: `while (d > π) d -= 2π`
  never terminates for ±∞, and `HepMC3::FourVector::delta_phi` has the same loop, guarding NaN but
  not ∞. `std::remainder` wraps over the same range in one step. The test times the call, so the
  loop coming back hangs a 0.05 s test rather than a run.
- **B36** — this step hands modules `Phys::cluster`, and `Analyzer::Modules` is the one analyzer that
  shards, so 00/B31 applied to modules with nothing to detect it. `Module::Base::threadSafe()` (true
  by default) lets a module opt out and the analyzer reports `Locked` rather than `Sharded`.

**And a throughput bug B36's fix exposed.** With the module locked, `auto` dropped the *whole run*
to serial: `decideMode` asked "can any analyzer be sharded?" when the question is "is there anything to
gain?" — a `Locked` analyzer still lets the generator run on k threads. Measured **124 µs/event serial
against 92 µs/event with the lock**, so the rule now counts anything that is not `Serial`. Only the
new case changes: Rivet-with-jets and `Count` both report `Serial`.

**`Phys` has a real user.** `ToyJets` carried its own final-state loop, its own pT and a hand-written
pseudorapidity with a beam-axis guard; all three are one `Phys::Acceptance`, and it finally clusters
the jets it is named after. `test_modules.py` re-measures the physics unchanged.

Suite: **28 ctest tests** (was 27) and **706 Python tests**, all passing.

## Just finished — P8-S03 (ML namespace, ONNX Runtime) — done

ONNX Runtime 1.29.0 is installed here, so both rows were measured rather than reasoned about.

**Parity is exact.** 20 C++ workers sharing one `Ort::Session`, each with its own `ML::Scratch`,
against single-threaded Python `onnxruntime`: **all 1 000 output floats bit-identical**, max
difference 0. Only true because both sides pin `intra_op_num_threads = 1`; the test asserts equality
rather than a tolerance, because a tolerance loose enough to survive a kernel change would hide the
bug the row exists to catch.

**Optional row.** `-DHEKIT_WITH_ONNX=OFF` builds green, 14/14 cxx tests. `ML/Types.hh` and
`ML/Features.hh` have no ONNX in them, so a module builds features identically either way.

**00/B37 — the plugin convention had never been run, and was wrong.** `Requires: ONNX` has added
`-I<onnx include>` to `rivet-build` since an earlier step, but no `.info` declares it, so nothing
had ever compiled through that path. `Rivet/Tools/RivetONNXrt.hh:11` includes
`"onnxruntime/onnxruntime_cxx_api.h"` — the Debian spelling — and a source build puts the headers
straight into `<prefix>/include`, with no `onnxruntime/` directory here or in `/usr/include`. Fixed
with `build/onnx-compat/`, one symlink; the test builds a probe plugin through the real
`rivet-build`, loads it, **and** checks the old flags still fail.

**Named features, because of one bug.** A model trained on `[pt, eta, phi, m]` fed
`[pt, phi, eta, m]` throws nothing and is wrong in a way that looks like bad training. `Row::set`
takes a name and `Row::values()` refuses an incompletely filled row.

**`sha256()` now goes somewhere.** 05 §6 said "into provenance" and nothing wrote it down.
`Module::Base::provenance()` and `Analyzer::Analyzer::provenance()` feed a new `inputs` block in
`run.summary.json` — `ToyJets.model` and `ToyJets.model_sha256`, asserted against the file's hash.

`ToyJets` gained an **optional** model (off unless `model = "..."`), so the Goal is checked end to
end through `hep-run`; the existing `modules` test is untouched and still passes.

**One cost, and what was done about it.** `rivet-build` hardcodes `-O2`, and at `-O2` gcc spends
**12 m 43 s** of CPU optimising ONNX's inline templates for a twenty-line plugin — the same
translation unit is **3.3 s** at `-O0`. So `onnx_plugin` compiles and links with the same flags at
`-O0` and takes 5 s; that `rivet-build` forwards the flags at all was checked separately, by reading
the `cc1plus` command line of a real invocation mid-compile.

## Just finished — P8-S04 (derived-tables format) — done. **Phase P8 is complete.**

A decision step. The decision is unchanged and was not mine to revisit: **deferred**, trigger the
first ML training dataset. What this step added is the half that was a placeholder — the
**Evidence**, which P5-S03, P8-S01 and P8-S03 have since made answerable.

- **Parquet cannot be written here at all.** No pyarrow, no fastparquet; `pandas.to_parquet` raises
  `ImportError: Unable to find a usable engine`. Arrow C++ absent too. So *both* Parquet options
  carry a new dependency, which 01 N5 makes a real cost.
- **RNTuple is free.** ROOT 6.40.04 ships `RNTupleWriter/Reader/Model.hxx` and uproot 5.7.6 reads
  RNTuple — the only option that works today with nothing new installed, from both languages.
- **Deferring is cheap, and now demonstrably so.** P5-S03 measured replay as exact, so any offline
  table can be built later from stores that already exist, without touching `hep-run`.

Also recorded: **D15 is the sharpest criterion** — a derived table is neither an event (D13) nor a
result (D14), but writing one *from the event loop* would contradict "`hep-run` doesn't link ROOT",
which rules on the C++/Arrow option without waiting for the trigger. And `ML::Features` already
fixes the column names and their order, so what is open is the container, not the schema.

No code, no new dependency, nothing to roll back.

## Just finished — P9-S01 (`hep proc`: fits) — done

All four rows measured. 17 unit tests, 10 integration tests, ctest `proc`.

**The backends really do fit the same function.** The obvious design — a `TF1` formula for ROOT, a
NumPy callable for scipy — makes "do the backends agree" a question about transcription. So Minuit2
drives `ROOT::Math::Minimizer` with a `Functor` wrapping **the model's own callable**. They agree to
**3.9 × 10⁻⁶** against a 1e-3 requirement.

**A χ² is not a general minimisation.** The first scipy backend used `L-BFGS-B`; on a Gaussian with
amplitude ~1e5 and width ~2e-3 it stopped at **χ²/ndf = 12.5** with background parameters **4.9σ**
from truth, where Minuit2 reached 0.835. Scaling, not tolerance — `least_squares` on the residual
vector matches Minuit2 to six figures. Poisson still goes through `minimize`; it is not a sum of
squares.

**The recovery row as written is a flaky test** — "within 1σ" for five parameters and one seed fails
~30 % of the time whatever the code does. Asserted as |pull| < 3 on a fixed seed (the broken
minimiser gave 4.9σ, so it discriminates) **plus** the pull distribution over 20 seeds: RMS in
[0.5, 1.8]. That second one is what a single fit cannot check — errors uniformly half their true
size give perfect parameters and an RMS of 2.

**Two traps, both found by running it against real results.**

- **A finalized Rivet object is a `BinnedEstimate1D`, not a `Histo1D`** — `val()` not `sumW()`, and
  already finished. Dividing by the bin width (right for a histogram) would scale the amplitude by
  1/width; on a uniform binning that is a constant, so the fit still converges and is quietly wrong.
- **A colon in a YODA title is unparseable YAML**, so the file writes cleanly and the *next* command
  fails on reading it.

**The overlay needed a rename, then a way to keep several apart.** A plotter overlays objects whose
paths match, so `show_fits` copies each curve onto its target. Several points fitted on one page
then collide — so each carries an analysis option (`/photo_eic:fit=<point>/…`) that `io.plot_key`
strips, which is the mechanism two option variants already use.

Suite: **723 Python tests** (was 706).

## Just finished — P9-S02 (derived histograms on Delphes output) — done. **Phase P9 is complete.**

Both rows measured. 22 unit tests, 14 integration tests.

**The difficulty is not histogramming, it is that the engines speak different languages.** RDF
compiles C++; uproot evaluates Python over awkward arrays. The trap: Python's `&` binds **tighter**
than a comparison, so a textual rewrite turns `a > 5 && b < 3` into `a > (5 & b) < 3` — valid,
different, silent. The translation goes through Python's own parser and rewrites `and`/`or`/`not` as
**tree nodes**, where precedence is structural. A test fits that exact case.

**Identical, not close.** A real `delphes.root` (`Tower.ET`, 785 entries after cuts): every bin
equal. A jagged tree, eight expressions — plain, cut, `&&`, `||`, `!`, a derived `sqrt(x*x)`,
arithmetic, and the precedence case — all identical.

**The selection cuts elements, not events** — `Jet.PT > 5` on a jagged branch is a boolean per jet,
and filtering whole events would give a different, plausible answer.

**Two findings.**

- **`BinnedEstimate1D`, not `Histo1D`.** YODA 2 splits a fillable accumulator from a finished value,
  and the plot pipeline recognises only the latter. A derived histogram is finished when filled, so
  writing a `Histo1D` gave a file that was correct, summed correctly, and was **silently skipped by
  every plotting path** — the opposite of "treat it like any other result". The Plots row caught it.
- **`hep proc --only` was destructive**: it rewrote the whole `fits.json` with just the entry it
  ran, so retuning one fit of five threw the other four away. Found by a *test-ordering* failure,
  which is the only way it shows up. `--only` now merges; a full run still replaces.

Suite: **745 Python tests** (was 723).

## Just finished — P10-S01 (shims, `hep clean`, `hep new`) — done

17 new tests. **The command tree of 08 §2 is complete** — no entry in `COMMANDS` is a placeholder,
and a test asserts that rather than skipping once it becomes true.

**The grep row cannot pass, and making it pass would be a mistake.** As written it finds 345 hits;
in *code*, 24, and every one is either (a) the 7 lines in `config/migrate.py` that read `[rivpyth]`
out of a v1 file — precisely what the Goal permits — (b) one line in `validate.py` that *detects* a
v1 file to say "run `hep config migrate`" instead of a wall of key errors, or (c) a docstring
recording where a function was ported from. Deleting (c) to satisfy a grep would destroy the record
of why some code is shaped as it is and remove no transitional behaviour.

So the row was replaced with the question it means: **is there executable code outside `migrate`
that still speaks v1?** An AST check parses every module and inspects literals and identifiers with
docstrings excluded *by parsing*. Answer: **zero** — and proved to discriminate by reintroducing a
`raw.get("rivpyth", …)` elsewhere and watching it fail. `sources/` is gone; `NtupleAnalyzer`/`RNTuple`
appear nowhere in code.

**`hep clean` is shaped by its second column.** 07 §6 says YODA files, `fits.json` and provenance
are never touched, so no category is on by default, removals confirm, and `--older-than` makes
`--events` safe on a live tree. Removing a store **keeps `events.index.json`** as a tombstone, and
`--dry-run` ends with the largest directories *regardless of category* — "what is taking the space"
is the real question and the answer is often something the tool will never remove.

**The scaffolds build, and that was checked.** The analysis compiles against `rivet-config`, the
module against the `hekit` headers, and the project config plans to one point. The module scaffold
already obeys the scaling contract and carries the `threadSafe()` note, because those are the two
things a first module gets wrong. Nothing is ever overwritten.

Suite: **761 Python tests** (was 745).

## Just finished — P10-S02 (final documentation pass) — done

Two new documents, three rewritten, and **both rows turned into tests** so the docs cannot rot
silently.

- **`docs/GUIDE.md`** — how to get work done, in the order a session happens (plan → run → proc →
  plot), with the surprising things given their own sections: why threads are sometimes not used,
  what a seed is derived from, what `hep clean` refuses to touch. Ends with a symptom→command table
  and the exit codes.
- **`docs/MAP.md`** — where things live: the two halves and the narrow contract between them, the
  C++ layering, the `hekit` packages, a results directory, and a "finding your way in" table. It
  names the two invariants to know before opening the code (the scaling contract; concurrency is a
  property of the analyzer).
- **The design is a record now, not a proposal.** `rework/README.md` says so and carries a table of
  the **eleven places building it changed it** — so a reader does not have to find them one at a
  time.

**Links:** 0 broken over **504 relative links in 76 documents**, anchors checked against the target's
headings (a link to a renamed section is as broken as one to a missing file, and much harder to
spot). **Commands:** all 19 documented, *and* the converse — no document mentions a `hep <word>`
that does not exist, which is what protects a reader from typing something that fails. Both proved
to discriminate against a deliberate break.

`bots/BOT.md`'s layout table was stale — it still listed `sources/` and `tools/`, both gone —
refreshed under the standing `bots/` approval.

Suite: **769 Python tests** (was 762).

## Just finished — P10-S03 — done. **The rework is complete.**

54 of 55 steps; P7-S07 stays blocked by D-Q6 (the Herwig rebuild, deferred by the user). Tagged
`rework/v1` with approval.

**N5 holds.** With `RIVET`, `HEPMC` and `ONNX` all `OFF` the build configures, `hep-run` and eight
test binaries link, and `ctest -L cxx` passes **11/11**. `hep-run --capabilities` answers
`"components": []` — it degrades to a working Pythia-and-YODA binary that still speaks the same
spec schema, not to one that cannot start.

**N6 holds.** `hep doctor` with the toolchain hidden exits **0**, names each missing module *and
what to check*, and marks each generator `—`. A diagnostic that fails when things are broken is the
one tool that must not.

**The size report, and one budget missed.**

| | Budget | Measured | |
|---|---|---|---|
| C++ | 3 150 | 4 659 | 1.48x |
| Python | ~4 000 | 13 261 | **3.32x — missed** |

The C++ replaced **10 404 lines with 4 659**, covering more tools. The Python budget was missed in
every area by 2-5x, and the reason is how it was set: "port `rivpyth_common`" (1 147 lines) plus
glue, estimated before the four external-generator adapters, the phased supervisor, three fit
backends, two histogram engines and the live terminal existed as designs. Recorded as a miss rather
than revised, so the next estimate starts from a known error.

**And the degradation check found a defect of its own (00/B38).** `hep doctor --refresh` in the
stripped shell wrote its findings to a cache keyed on the install root alone, so the *next* `hep
doctor` in a good shell was told "herwig: not installed" for a day. It surfaced as an unrelated test
failing. `PATH` and `PYTHONPATH` are part of the key now — every check resolves through them — and a
report is reused only in the environment that produced it.

## What is left

- **P7-S07 (Herwig adapter)** — blocked, not forgotten. D-Q6 deferred the ThePEG rebuild; the two
  corrected configure flags are in P7-S06's Log. Unblocking is a rebuild, then the adapter.
- **00/B39 — the MadGraph stage opens a browser.** `automatic_html_opening` defaults to `True` and
  our launch script never turns it off, so every MadGraph point spawns a GUI from a batch stage.
  Found after `rework/v1` was tagged; **recorded, not applied**, by user decision, so the tag points
  at what was measured. One line in `launch_script()`: `set automatic_html_opening False`.
- **`[plot].merge = "yodamerge"`** — declared in the schema, implemented as `results/merge.py`, but
  the *command* that drives it has no owning step (noted in P8-S01's Log).

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · **P4 6/6** · **P5 3/3 — P0–P5 all complete** · **P6 3/3 — P0–P6 all complete** · **P7 7/8 — complete bar S07, blocked by D-Q6** · **P8 4/4 — P8 complete** · **P9 2/2 — P9 complete** · **P10 3/3 — every phase complete** — 54 of 55 steps done (P7-S07 blocked by D-Q6).

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
