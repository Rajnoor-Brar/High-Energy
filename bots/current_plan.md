# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P3-S02 (supervisor, FIFO transport, stall detection) — done

`hekit/run/{signals,transport,parsers,supervisor}.py` (~700 lines) with seven fake stages and 27 tests
(11.6 s; slowest test 4.65 s, under the step's 10 s budget). Every verification row measured: early
exit → 1 attributed to the generator while the reader was still blocked in `open()`; silent hang → 7;
1 GiB of stderr → whole log on disk, **RSS +0 MiB**; ignores SIGINT → SIGTERM (SIGKILL only for one
that ignores that too); reader dies → 4 with the message naming the crash; FIFO directory always gone.

The two old defects are fixed and tested: private per-run FIFO directories (00/B19) and ranked
attribution so a generator's SIGPIPE never masks Rivet's real error (00/B20).

Note for P3-S05: the status descriptor number cannot be fixed in advance (`pass_fds` keeps the number
it is given), so the supervisor allocates it and calls `on_status_fd(stage, fd)` before spawning — the
command writes that number into the spec's `[status].fd`.

## Next — P3-S03 (results layout, skip rule and provenance)

Read `docs/rework/steps/P3-S03_results-provenance.md` and mirror it here before starting. This is where
D-Q3's study serial (`studies/01_pdf/`, `[run].serial` default on) and the `legacy/` line of the layout
actually get implemented, together with the skip rule and `provenance.json`.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6 — phase complete** · P3 2/5 · P4–P10 todo — 23 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
