#!/usr/bin/env python3
"""Write N MiB to stderr as fast as possible. `flood.py [mib]`"""
import sys

mib = int(sys.argv[1]) if len(sys.argv) > 1 else 1024
# Lines, not one blob: a supervisor that keeps "the last line" must stay bounded either way.
line = ("flood " + "y" * 121 + "\n").encode()       # exactly 128 bytes, so a MiB is a whole number
assert len(line) == 128
per_mib = (1024 * 1024) // len(line)
stream = sys.stderr.buffer
for _ in range(mib):
    stream.write(line * per_mib)
stream.flush()
print(f"flooded {mib} MiB", flush=True)
