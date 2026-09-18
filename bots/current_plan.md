# Current plan — P2-S03 core-status (done) → next P2-S04

> Source: `docs/rework/steps/P2-S03_core-status.md`. Index: `docs/rework/steps/README.md`.
> Status: **done** (2026-09-18). 18 of 55 steps.

## What P2-S03 delivered

`Core` (errors and exit codes, Sha256 with an idempotent digest, two clocks, sigaction signals, paths,
the spec reader with the D-SEEDS length check, provenance, types) and `Status` (fd-3 JSON writer with a
non-blocking drop policy, heartbeat with advanced deadlines, plain fallback, scope timers, the X11
guard), plus `hekit.run.status` and a cross-language round-trip test.

## Next: P2-S04 source-run-loop

`Source::Pythia` (checked `readFile` → exit 1; `init` → exit 3; chunked runs per D-Q2;
`Parallelism:index`; logger counts), `Events::View` (lazy HepMC), the `Sink` interface, `Run::loop`,
and `hep-run SPEC [--check/--plain/--capabilities/--list N]`. Plus the seed-length check before
`init()` (D-SEEDS) and σ combined from the instances (D-Q1).
