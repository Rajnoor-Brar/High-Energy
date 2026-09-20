# P8-S03 — ML namespace (ONNX Runtime)

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P8 — Modules, YODA results, Phys, ML |
| Depends on | [P8-S01](P8-S01_module-sink-yoda.md) |
| Blocks | — |
| Effort | 0.75 d |
| Findings / decisions | R11; 05 §6; 00/B37 |
| Updated | 2026-09-20 |

## Goal

Modules can run ONNX models thread-safely; Rivet plugins that declare `Requires: ONNX` build with ONNX flags.

## Context

- Rivet is not linked to ONNX Runtime.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `$ONNXRUNTIME_DIR/include/onnxruntime_cxx_api.h`, `Rivet/Tools/RivetONNXrt.hh` | APIs | use |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `ML/{Types,OnnxModel,Features}`
- `HEKIT_WITH_ONNX`
- plugin flag convention
- tracked script that generates a toy model

**Out (non-goals)**

- Training

## Design notes

- One session per model; per-worker scratch buffers.

## Tasks

- [x] Implement
- [x] Tests

## Outputs

- `utils/ML.hh`, `utils/ML/{Types,OnnxModel,Features}.hh`
- `tests/cxx/test_ml.cc` (ctest `ml`), `tests/integration/test_ml.py` (ctest `ml_parity`)
- `tests/tools/toy_model.py` — the tracked script; the model itself is generated, never committed
- `tests/integration/test_onnx_plugin.py` (ctest `onnx_plugin`) — the `Requires: ONNX` convention
- `Module::Base::{provenance,threadSafe}`, `Sink::Sink::provenance`, `inputs` in `run.summary.json`
- `modules/Examples/ToyJets.cc` — an optional model, off unless `model = "..."` is given

## Verification

| Check | Command | Expected | Measured |
|---|---|---|---|
| Parity | toy model, 20 workers vs Python onnxruntime | same outputs | **bit-identical**: all 1 000 floats equal, max &#124;difference&#124; = 0 |
| Optional | build with ONNX off | green | configures, builds, 14/14 cxx tests pass; `test_ml` drops to its 18 schema checks and says so |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated (05 §6 rewritten; 07 §1 tree; 13 §2 row confirmed; 00/B37)
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-20 — **done.** ONNX Runtime 1.29.0 is installed here, so both rows were measured rather
  than reasoned about.

  **Parity is exact, not approximate.** 20 C++ workers sharing one `Ort::Session`, each with its own
  `ML::Scratch`, against a single-threaded Python `onnxruntime`: **all 1 000 output floats
  bit-identical**, max difference 0. That is only true because both sides pin
  `intra_op_num_threads = 1` — the same kernels then sum in the same order — and the test asserts
  equality rather than a tolerance, because a tolerance loose enough to survive a future kernel
  change would also be loose enough to hide the bug the row exists to catch. `tests/cxx/test_ml.cc`
  makes the same check in-process at 500 rows and finds zero differing floats.

  **The optional row.** `-DHEKIT_WITH_ONNX=OFF` configures, builds and passes 14/14 cxx tests.
  `ML/Types.hh` and `ML/Features.hh` contain no ONNX at all, so a module builds its feature row
  identically either way and only the call disappears; `test_ml` drops from 56 checks to its 18
  schema checks and prints why.

  **The plugin convention had never been run, and was wrong (00/B37).** `Requires: ONNX` in a
  plugin's `.info` has added `-I<onnx include>` to `rivet-build` since an earlier step, but no
  `.info` in the repository declares it, so nothing had ever compiled through that path.
  `Rivet/Tools/RivetONNXrt.hh:11` includes `"onnxruntime/onnxruntime_cxx_api.h"` — the spelling the
  Debian package installs — and a source build puts the headers straight into `<prefix>/include`
  with no `onnxruntime/` directory anywhere, here or in `/usr/include`. So the convention could not
  build a plugin that used Rivet's own ONNX helper. Fixed with `build/onnx-compat/`, a directory
  whose only entry is a symlink `onnxruntime` → the include directory; both paths are passed.
  `tests/integration/test_onnx_plugin.py` builds a probe plugin through the real `rivet-build`,
  loads it with `rivet --list-analyses`, **and** checks that the old flags still fail — without that
  second half the convention could rot again silently.

  **Named features, because of one specific bug.** A model trained on `[pt, eta, phi, m]` and fed
  `[pt, phi, eta, m]` throws nothing, evaluates happily, and is wrong in a way that looks like bad
  training. So `ML::Features` is an ordered list of names, `Row::set` takes one of them, and
  `Row::values()` refuses a row that is not completely filled — an unset feature is a zero meaning
  "no signal", indistinguishable from a real zero once it is in the tensor. `Features::matches(model)`
  checks the schema width against the file when the module starts.

  **Deviations from the step as written.** Four, all additions:

  - `ML::Floats` stands in for `std::span<const float>`, which 05 §6 writes and C++17 does not have.
    Same members, same name for them; the alias changes if the project moves to C++20.
  - **`ToyJets` gained an optional model**, off unless `model = "..."` is given, so the Goal
    ("modules can run ONNX models") is checked end to end through `hep-run` rather than inferred
    from the library compiling. The existing `modules` test is untouched and still passes (9).
  - **`sha256()` now goes somewhere.** 05 §6 said "into provenance" and nothing wrote it down, which
    is no better than not having it. `Module::Base::provenance()` and `Sink::Sink::provenance()`
    return `(key, value)` pairs, the loop collects them, and `run.summary.json` gained an `inputs`
    block: `ToyJets.model` and `ToyJets.model_sha256`, asserted against the file's own hash.
  - The toy model is generated by a tracked script at **build time** (a CMake custom command), so
    `tests/cxx/test_ml.cc` is self-contained and no binary enters git. Skipped cleanly when the
    `onnx` Python package is absent.

  **One cost worth knowing, and what was done about it.** `rivet-build` hardcodes `-O2`, and at
  `-O2` gcc spends **over twelve minutes** optimising ONNX Runtime's inline template headers for a
  twenty-line plugin — 12 m 43 s of CPU, measured. The same translation unit is **3.3 seconds** at
  `-O0`. A twelve-minute test in a suite whose every other test finishes inside five minutes is not
  a test anyone will run, so `onnx_plugin` compiles and links with the same flags `rivet-build` would
  pass on, at `-O0`, and takes 5 s for all five assertions. The one thing that cannot check — that
  `rivet-build` forwards the extra arguments at all — was verified directly instead, by reading the
  `cc1plus` command line of a real `rivet-build` run mid-compile: both `-I` paths were on it.
