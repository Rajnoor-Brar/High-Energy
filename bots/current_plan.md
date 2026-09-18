# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P5-S01 (event store: writer, sink, CLI) — done

**D-STORE-COMP decided by measurement: `zst`.** On 10 000 real events, zstd is 9 866 B/event against
gz's 10 223, **2.1× faster to write** (2 289 vs 1 086 ev/s) and 1.26× faster to read. No axis favours
gz, so `zst` is the default and `gz` the fallback.

All three verification rows measured: shard counts add up and nothing is left in `.part`; a truncated
shard is caught by size alone and a single changed byte by `--deep`; a build without zstd works on gz
and refuses `zst` with a clear message. End to end, `hep run --set store.enabled=true` wrote two
stores and `hep store ls|verify --deep` read them.

The order is the design: shards stream into `.part` with no lock, are closed, hashed and renamed, and
only then is the index written atomically — so a directory with an index is a finished store.

Three defects found on the way, including two in my own spike (`Pythia8ToHepMC` reuses one `GenEvent`,
so holding its pointer would have measured one event 10 000 times) and an include that found itself.

## Next — P5-S02 (store and stream sources with parallel readers)

Read `docs/rework/steps/P5-S02_store-source-replay.md` and mirror it here before starting. It adds
`Source::Store` (one reader thread per shard into a bounded queue) and `Source::Stream` for FIFOs —
the replay side of what P5-S01 writes.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · **P4 6/6** · P5 1/3 · P6–P10 todo — 33 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
