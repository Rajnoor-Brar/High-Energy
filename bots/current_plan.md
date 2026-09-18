# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P3-S04 (dashboard, plain mode, watch/runs/show) — done

`hekit/term/{theme,model,plain,dashboard,cli}.py` + `hekit/run/journal.py` + `hekit/results/cli.py`
(~1060 lines), 52 tests. All three verification rows measured: the dashboard frame asserted line by
line against 06 §1's mock-up; `hep watch` through a real pipe gives plain clock-stamped lines; a pty
test proves the cursor and echo come back after an exception mid-render.

One view model feeds the live dashboard, the plain lines and `hep watch`, which replays
`status.jsonl` — so watching from another terminal is the same code, not a second implementation.
The legacy bar-interval defect is fixed: the progress interval is computed once the totals are known.

Found while running under ctest: without `LANG`, a single `σ` was enough to kill the output, so the
whole vocabulary now degrades to ASCII when the stream cannot encode it.

## Next — P3-S05 (wire the hep run command end to end)

Read `docs/rework/steps/P3-S05_hep-run-command.md` and mirror it here before starting. It joins what
P3-S02..S04 built: plan → per-point spec → supervisor (with `on_status_fd` writing `[status].fd`) →
journal + dashboard → results layout, skip rule and provenance. **P3 finishes with it.**

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6 — phase complete** · P3 4/5 · P4–P10 todo — 25 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
