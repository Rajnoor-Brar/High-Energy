#!/usr/bin/env python3
"""Generate the toy ONNX model the ML tests run (P8-S03, 05 §6).

A model is a binary, and a binary in git is a thing nobody can read a diff of. So the model is
**generated** from this script instead: the weights come from a seeded RNG, so every checkout builds
byte-identical inputs and the test can say what the answer should be without shipping one.

The network is deliberately small and deliberately not linear:

    input [N, 4]  →  Gemm(W1, b1)  →  Tanh  →  Gemm(W2, b2)  →  Sigmoid  →  output [N, 2]

Two layers rather than one because a single matrix multiply would agree between two implementations
even if one of them transposed it; a `Tanh` in the middle means a wrong weight, a wrong order or a
wrong stride gives a visibly different number rather than a plausible one. Four inputs because that
is a four-vector's worth of features, which is what a module would actually feed it.

    python3 tests/tools/toy_model.py output/scratch/ml/toy.onnx

Writing it is one thing this script does; the other is being importable, so the parity test can ask
for the same model and the same reference outputs without duplicating the recipe.
"""

from __future__ import annotations

import sys
from pathlib import Path

FEATURES = 4
HIDDEN = 8
OUTPUTS = 2
SEED = 20260920

INPUT_NAME = "features"
OUTPUT_NAME = "score"


def weights():
    """The fixed weights, from a seeded RNG so every checkout gets the same model."""
    import numpy as np

    rng = np.random.default_rng(SEED)
    return {
        "W1": rng.normal(0.0, 0.7, size=(FEATURES, HIDDEN)).astype("float32"),
        "b1": rng.normal(0.0, 0.2, size=(HIDDEN,)).astype("float32"),
        "W2": rng.normal(0.0, 0.7, size=(HIDDEN, OUTPUTS)).astype("float32"),
        "b2": rng.normal(0.0, 0.2, size=(OUTPUTS,)).astype("float32"),
    }


def build(path: Path) -> Path:
    """Write the model to `path` and return it. Overwrites, so it is safe to call every run."""
    import numpy as np
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    made = weights()
    initialisers = [numpy_helper.from_array(value, name) for name, value in made.items()]

    nodes = [
        helper.make_node("Gemm", [INPUT_NAME, "W1", "b1"], ["hidden"], name="layer1"),
        helper.make_node("Tanh", ["hidden"], ["activated"], name="activation"),
        helper.make_node("Gemm", ["activated", "W2", "b2"], ["logits"], name="layer2"),
        helper.make_node("Sigmoid", ["logits"], [OUTPUT_NAME], name="squash"),
    ]

    # A dynamic batch dimension, because that is what a real model has and it is the thing a fixed
    # [1, 4] assumption would hide.
    graph = helper.make_graph(
        nodes,
        "hekit_toy",
        [helper.make_tensor_value_info(INPUT_NAME, TensorProto.FLOAT, ["batch", FEATURES])],
        [helper.make_tensor_value_info(OUTPUT_NAME, TensorProto.FLOAT, ["batch", OUTPUTS])],
        initialisers,
    )
    model = helper.make_model(graph, producer_name="hekit/tests/tools/toy_model.py",
                              opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 9          # onnxruntime 1.29 reads 10, but 9 is what every 1.x reads
    onnx.checker.check_model(model)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(model.SerializeToString())
    return path


def sample_inputs(rows: int):
    """The inputs the parity test uses, so both sides ask the same question."""
    import numpy as np

    rng = np.random.default_rng(SEED + 1)
    return rng.normal(0.0, 1.5, size=(rows, FEATURES)).astype("float32")


def reference(path: Path, values):
    """What Python's onnxruntime says — the other half of the parity row."""
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 1
    session = onnxruntime.InferenceSession(str(path), options,
                                           providers=["CPUExecutionProvider"])
    return session.run([OUTPUT_NAME], {INPUT_NAME: values})[0]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <out.onnx>", file=sys.stderr)
        return 2
    written = build(Path(argv[1]))
    print(f"{written}  ({written.stat().st_size} bytes, "
          f"{FEATURES} in -> {OUTPUTS} out)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
