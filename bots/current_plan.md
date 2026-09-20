# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P5-S03 (replay equivalence, `hep events`) — done. **Phase P5 is complete.**

Both rows measured. The equivalence is **exact**, not "to rounding": a replayed store gives a YODA
identical to the generation's (1004 numbers, χ² = 0), because the same events go through the same
sinks in the same order.

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
- **00/B32 — a sink exception would have called `std::terminate`.** `PythiaParallel` runs the
  callback on its worker threads in *both* modes (`processAsync = off` only adds a mutex), so a
  Rivet error mid-run was unwinding through `std::thread`. Both sources now catch at that boundary.

Also settled: **`fill` merges, `set` does not** — `MC_XS` is re-entrant and still has one object it
`set()`s from the per-event running σ, which no merge can reconstruct. That is the rule P8-S01 has
to follow for module results.

## Just finished — P6-S02 (shared generation for analysis-only variants) — done

The planning half had worked since P1-S05; the **plotting half had not**, and testing the chain end
to end is what found it.

**A two-member page was drawing four curves.** `select.curves_for` expanded *every* variant it found
in a point's file. That is right when one point holds several radii, and wrong the moment several
points **share** one generation — the shared YODA then holds every variant and each point claimed
all of them. Nothing had ever asked what came out of the far end: the planner grouped correctly, the
sink booked both variants, and the page quietly doubled them.

Fixed by giving `PointFile` the point's own `analyses`; a point that declares one takes only that.
The legend stopped repeating itself too ("R = 0.4 (R=0.4)" → "R = 0.4").

Rows: `hep plan --study radius` → 1 group, 3 variants (and the `pdf` study is *not* grouped, as a
control); one point directory whose YODA carries both variant paths and one `/_EVTCOUNT`; `hep plot`
→ 2 curves.

## Just finished — P6-S03 (`hep bench`) — done. **Phase P6 is complete.**

Four legs — generation only, generation + sinks serially, the same sharded, and a replay — then a
recommendation. On PhotoProduction at 1 000 events:

```
  generation      0.18s        5523 ev/s
  serial          0.75s        1327 ev/s
  sharded     refused: photo_eic clusters jets, which cannot be done from several threads
  replay          0.52s        1916 ev/s

  the sinks are 76% of a serial run's wall clock
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

Both rows run against the real Whizard 3.1.8: a toy `e+e- → u ubar`, and the ep card D-Q7 settled on.
A two-seed study compiles and integrates **once** — for Whizard that means not rebuilding the
matrix-element library, the dominant cost.

**Two properties of Whizard that bite immediately, now pinned by tests.**

1. **It writes no cross-section into HepMC3** — no `C` record at all, verified by reading the file.
   The run had been quietly producing a YODA normalised by **zero**. 04 §8 already said that must be
   an error; nothing enforced it. `RunRecord` now carries `xsec_known` and `Sink::Rivet` refuses,
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
sink still ran on the same events — the tee is a tee — and `delphes.json` beside the ROOT file names
the card, its sha256 and the point's identity.

**The design assumed a FIFO and that cannot work.** `DelphesHepMC3` sizes its input and *skips
anything whose length is zero* (`readers/DelphesHepMC3.cpp:160-169`), which a FIFO always is —
so it opened the pipe, decided it was empty, exited, and `hep-run` died writing into a closed pipe.
The tee now writes a regular file and Delphes runs in the phase after, like MadGraph's LHE: a tool
that seeks cannot be streamed to.

**And the failure row found another**: Delphes creates the ROOT file *before* reading the card, so a
bad card left a `delphes.root` that opened, contained nothing and looked like a result. Written as
`.part` and renamed on success now (D22).

## Next — P8-S01 (module API, YODA results layer, module sink)

**Phase P8 — modules, YODA results, Phys, ML** (4 steps). Read `docs/rework/steps/README.md` for
P8's order, then `P8-S01_module-sink-yoda.md`, and mirror it here before starting. P6-S01 left it a
rule it has to follow: **`fill` merges, `set` does not** — a module's results must be filled.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · **P4 6/6** · **P5 3/3 — P0–P5 all complete** · **P6 3/3 — P0–P6 all complete** · **P7 7/8 — complete bar S07, blocked by D-Q6** · P8–P10 todo — 45 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
