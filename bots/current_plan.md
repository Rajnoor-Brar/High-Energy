# Current plan — P1 complete → next P2-S01

> Index: `docs/rework/steps/README.md`. P0 (8 steps) and P1 (7 steps) are done; 15 of 55.

## P1 outcome (2026-09-18)

`hekit` is the Python half of the toolkit: schema-2 configuration with layering and origins, the sweep
engine, identity hashing and disjoint seed blocks, plan building with the Pythia and Rivet adapters, the
resolved spec (`spec_v2.json`), migration and the generated reference, and `hep doctor` / `hep pdf`.
Commands that work today: `hep plan`, `hep studies`, `hep config migrate|validate|reference|init`,
`hep doctor`, `hep pdf list|check|install`. 318 tests, ~5 s.

## Next: P2 — C++ core, CMake, hep-run v1

P2-S01 `cmake-skeleton`: CMake + `cmake/Find*.cmake` (via `*-config`), AUTO
`HEKIT_WITH_{RIVET,HEPMC,ONNX,DELPHES}`, HepMC compression defines, one interface library per facade,
`git mv` `photo_eic` → `analyses/PhotoProduction/` with `rivet_<project>` targets (the legacy make also
searches `analyses/`), ctest + pytest registration, compile DB.
