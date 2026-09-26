#!/usr/bin/env python3
"""modules/PhotoProduction/delphes_jets.py — a custom tool over Delphes's output (04 §8.4).

    python3 delphes_jets.py DELPHES.root OUTPUT.json

Reads the Delphes tree and writes, per event, the reconstructed jet multiplicity and the leading
jet's pT: the smallest real analysis at detector level, and the end of the file chain
pythia → (file) → delphes → this.
"""

import json
import sys

import numpy as np
import uproot


def main(source: str, target: str) -> int:
    with uproot.open(source) as file:
        tree = file["Delphes"]
        pt = tree["Jet/Jet.PT"].array(library="np")
    counts = np.array([len(event) for event in pt])
    leading = np.array([event.max() for event in pt if len(event)])
    summary = {
        "events": int(len(counts)),
        "jets_per_event": float(counts.mean()) if len(counts) else 0.0,
        "events_with_a_jet": int((counts > 0).sum()),
        "leading_pt_mean_gev": float(leading.mean()) if len(leading) else 0.0,
        "multiplicity": {str(n): int((counts == n).sum()) for n in range(int(counts.max()) + 1)} if len(counts) else {},
    }
    with open(target, "w", encoding="utf-8") as out:
        json.dump(summary, out, indent=1)
    print(f"{summary['events']} events, {summary['jets_per_event']:.3f} jets per event")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: delphes_jets.py DELPHES.root OUTPUT.json")
    sys.exit(main(sys.argv[1], sys.argv[2]))
