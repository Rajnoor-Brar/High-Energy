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

## Next — P7-S02 (decide cross-generator photoproduction set-ups)

A **decision** step: which EPA/WW parameters, Q²max, photon PDF, pTHatMin analogue and MPI settings
count as equivalent to `photo_ep.cmnd` across Sherpa, Whizard, Herwig and MadGraph. It blocks S03 and
S04. Read `docs/rework/steps/P7-S02_decide-photoproduction-equivalence.md` and mirror it here first;
a decision step also needs its **Decision record** filled and the register updated.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · **P4 6/6** · **P5 3/3 — P0–P5 all complete** · **P6 3/3 — P0–P6 all complete** · P7 1/8 · P8–P10 todo — 39 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
