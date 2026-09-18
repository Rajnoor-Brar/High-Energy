#!/usr/bin/env python3
"""Read a FIFO, then end. `reader.py FIFO [code] [blocks_before_exit] [--signal N]`

With `blocks_before_exit` the reader stops early while the writer is still writing, which is how a
pipeline produces a SIGPIPE on the other side.
"""
import os
import signal
import sys

path = sys.argv[1]
code = int(sys.argv[2]) if len(sys.argv) > 2 else 0
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0
die_with = int(sys.argv[sys.argv.index("--signal") + 1]) if "--signal" in sys.argv else 0

read = 0
with open(path, "rb") as fifo:
    while True:
        chunk = fifo.read(4096)
        if not chunk:
            break
        read += len(chunk)
        if limit and read >= limit * 4096:
            break
print(f"read {read} bytes", flush=True)
if die_with:
    signal.signal(die_with, signal.SIG_DFL)
    os.kill(os.getpid(), die_with)   # die the way a crash does, not with an exit code
sys.exit(code)
