#!/usr/bin/env python3
"""Write hep-run-shaped status messages on a descriptor. `statusful.py FD [messages] [--quiet-for S]`

The supervisor tells a stage which descriptor to use, so this takes it as an argument rather than
assuming 3 — the same contract `[status].fd` gives hep-run.
"""
import json
import os
import sys
import time

fd = int(sys.argv[1])
messages = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 3
quiet_for = float(sys.argv[sys.argv.index("--quiet-for") + 1]) if "--quiet-for" in sys.argv else 0.0

def emit(payload):
    os.write(fd, (json.dumps({"t": time.time(), **payload}) + "\n").encode())

emit({"k": "phase", "phase": "init"})
emit({"k": "init", "beam_ids": [2212, 11], "beam_energies": [27.5, 920.0], "sqrt_s": 318.1,
      "threads": 2, "mode": "serial", "analyzers": ["rivet"]})
for index in range(messages):
    emit({"k": "progress", "done": (index + 1) * 100, "total": messages * 100,
          "rate": 100.0, "workers": [(index + 1) * 50, (index + 1) * 50]})
    time.sleep(0.02)
if quiet_for:
    time.sleep(quiet_for)              # alive, but saying nothing: the stall case
emit({"k": "summary", "events": messages * 100, "stopped": False})
os.close(fd)
