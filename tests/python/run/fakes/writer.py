#!/usr/bin/env python3
"""Write to a FIFO until stopped. `writer.py FIFO [blocks]` (blocks of 4 KiB; 0 = forever).

Opening a FIFO for writing blocks until a reader arrives, which is exactly the behaviour that makes a
pipeline's failure modes interesting.
"""
import signal
import sys
import time

# Die on SIGPIPE like Pythia or Rivet would. Python's default is to ignore it and raise
# BrokenPipeError, which would make a knock-on death look like an error of our own.
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

path, blocks = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0
block = b"x" * 4096
written = 0
with open(path, "wb") as fifo:
    while blocks == 0 or written < blocks:
        fifo.write(block)            # SIGPIPE (or BrokenPipeError) when the reader goes away
        fifo.flush()
        written += 1
        time.sleep(0.001)
print(f"wrote {written} blocks", flush=True)
