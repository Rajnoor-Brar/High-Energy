#!/usr/bin/env python3
"""Say nothing, do nothing, for a long time. `hang.py [seconds] [--announce TEXT]`"""
import sys
import time

seconds = float(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else 3600.0
if "--announce" in sys.argv:
    print(sys.argv[sys.argv.index("--announce") + 1], flush=True)
time.sleep(seconds)
