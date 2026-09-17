# Current plan — P0-S07 makefile-hygiene

> Mirror of the step being executed (per bots/BOT.md). Source: `docs/rework/steps/P0-S07_makefile-hygiene.md`.
> Step index: `docs/rework/steps/README.md`. Status: **in-progress** (2026-09-18). Last P0 step.
> Approved by the user for P0: tags, `~/HEP` edits, local per-step commits (no push), `bots/` layout edits.

## Goal

The interim Makefile builds only `generator.exe` and Rivet plugins, with per-target libraries, lazy flag
evaluation and visible errors (plans 0.3 reduced, 00 §4.4, F11).

## Changes

- Recursive `=` for every `*-config` / `pkg-config` call, so nothing runs until a build actually needs it.
- Per-target link flags: `LIBS_<target>`; `generator.exe` gets Pythia + HepMC3 only.
- Drop ROOT, toml++, ONNX, Delphes, FastJet, YODA and LHAPDF from the generic rule, and the stale
  `-I./utils -I./modules` (both directories are gone after P0-S06).
- `.so`: `rivet-build` only; a failing metadata copy now fails the rule (was `; true`).
- `make test` prints where the tests live; `make help` lists the targets.
- `clean` removes build products only and keeps `output/scratch/` (the golden-fixture scratch) —
  `distclean` still removes the whole output tree.

## Verification

| Check | Expected |
|---|---|
| `make -n PhotoProduction/generator.exe \| grep -c onnx` | 0 |
| `env -u ONNXRUNTIME_DIR make PhotoProduction/generator.exe` | builds |
| `make PhotoProduction/photo_eic.so && ls output/PhotoProduction/photo_eic.info` | exists |
| unreadable `.plot` in scratch | the rule exits non-zero |

## Next

P0 exit checks, then P1-S01 `package-skeleton` (first step of the Python core).
