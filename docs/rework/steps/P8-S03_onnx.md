# P8-S03 — ML namespace (ONNX Runtime)

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P8 — Modules, YODA results, Phys, ML |
| Depends on | [P8-S01](P8-S01_module-sink-yoda.md) |
| Blocks | — |
| Effort | 0.75 d |
| Findings / decisions | R11; 05 §6 |
| Updated | 2026-09-17 |

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

- [ ] Implement
- [ ] Tests

## Outputs

- `utils/ML*`
- `tests/cpp/ml_*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Parity | toy model, 20 workers vs Python onnxruntime | same outputs |
| Optional | build with ONNX off | green |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
