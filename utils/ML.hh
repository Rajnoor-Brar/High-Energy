#pragma once

// ── ML.hh ────────────────────────────────────────────────────────────────────
// Running a trained model from inside the event loop (05 §6, 13 §2).
//
// It sits beside `Phys` in the layering — above `Events`, below `Module` — so it knows about ONNX
// Runtime and nothing about sinks, sources or the run.
//
// **Two of the three headers have no ONNX in them.** `Types` and `Features` are buffers and names,
// so a module builds its feature row identically whether or not this build has ONNX Runtime, and
// only `OnnxModel` disappears. That is what keeps the "build with ONNX off" row green without a
// second code path to maintain, and `HEKIT_WITH_ONNX` is the one thing a module has to guard.
//
// **In a Rivet plugin, use Rivet's `RivetONNXrt` instead.** Rivet is not linked to ONNX Runtime, so
// a plugin that wants a model declares `Requires: ONNX` in its `.info` and the build adds the flags
// to `rivet-build` (09 §1). This namespace is for modules, which are ours to link.

#include "ML/Types.hh"
#include "ML/Features.hh"

#if defined(HEKIT_WITH_ONNX)
#include "ML/OnnxModel.hh"
#endif
