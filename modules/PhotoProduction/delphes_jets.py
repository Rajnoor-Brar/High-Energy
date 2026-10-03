#!/usr/bin/env python3
"""modules/PhotoProduction/delphes_jets.py — a custom tool over Delphes's output (03 §4.10).

    python3 delphes_jets.py DELPHES.root OUTPUT.json

Reads the Delphes tree and writes, per event, the reconstructed jet multiplicity and the leading
jet's pT: the smallest real analysis at detector level, and the end of the file chain
pythia → (file) → delphes → this. It speaks the standard status protocol and the exit codes through
utils/hepkit.py (V74), so its table may say status = "standard".
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "utils"))
import hepkit  # noqa: E402


def main(source: str, target: str) -> int:
    status = hepkit.Status()
    import numpy as np
    import uproot
    status.phase("reading", source)
    try:
        with uproot.open(source) as file:
            tree = file["Delphes"]
            pt = tree["Jet/Jet.PT"].array(library="np")
    except (OSError, KeyError, ValueError) as error:
        status.log("error", f"cannot read the Delphes tree of {source}: {error}")
        return hepkit.Exit.INPUT
    counts = np.array([len(event) for event in pt])
    status.progress(len(counts), len(counts), force=True)
    leading = np.array([event.max() for event in pt if len(event)])
    summary = {
        "events": int(len(counts)),
        "jets_per_event": float(counts.mean()) if len(counts) else 0.0,
        "events_with_a_jet": int((counts > 0).sum()),
        "leading_pt_mean_gev": float(leading.mean()) if len(leading) else 0.0,
        "multiplicity": {str(n): int((counts == n).sum()) for n in range(int(counts.max()) + 1)} if len(counts) else {},
    }
    try:
        with open(target, "w", encoding="utf-8") as out:
            json.dump(summary, out, indent=1)
    except OSError as error:
        status.log("error", f"cannot write {target}: {error}")
        return hepkit.Exit.OUTPUT
    status.summary(events=summary["events"], jets_per_event=summary["jets_per_event"])
    print(f"{summary['events']} events, {summary['jets_per_event']:.3f} jets per event")
    status.close()
    return hepkit.Exit.STOPPED if hepkit.stopping() else hepkit.Exit.OK


if __name__ == "__main__":
    if len(sys.argv) != 3:
        hepkit.usage("usage: delphes_jets.py DELPHES.root OUTPUT.json")
    sys.exit(main(sys.argv[1], sys.argv[2]))
