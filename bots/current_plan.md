# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P3-S03 (results layout, skip rule, provenance) — done

`hekit/results/{layout,skip,manifest}.py` + `hekit/prov/{provenance,stamp}.py` (~720 lines), 33 tests.
Every verification row measured: a name collision with a different hash is refused with a `--rerun`
hint; a partial result reruns instead of being skipped (00/B3); `HekitPoint`/`HekitHash`/`HekitGit`
read back off `/_EVTCOUNT`; the layout is identical when run from `/` (00/B18).

D-Q3 is implemented: one serial series across studies, allocated by `mkdir` in a loop (scanning then
creating is a race), `[run].serial` default on, and a point path never carries a serial. `[run].serial`
is in the schema and `docs/rework/reference/config.md` is regenerated.

## Next — P3-S04 (live dashboard, plain mode, watch/runs/show)

Read `docs/rework/steps/P3-S04_terminal.md` and mirror it here before starting. It renders what the
supervisor already collects (06 §1–2, §5): the `rich` dashboard, `--plain` for logs and CI, and the
`hep watch` / `hep runs` / `hep show` commands over the layout and manifests written in P3-S03.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6 — phase complete** · P3 3/5 · P4–P10 todo — 24 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
