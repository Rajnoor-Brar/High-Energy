#!/usr/bin/env python3
"""Exit immediately, before opening the FIFO. `early_exit.py [code] [message]`"""
import sys

code = int(sys.argv[1]) if len(sys.argv) > 1 else 1
if len(sys.argv) > 2:
    print(sys.argv[2], file=sys.stderr, flush=True)
sys.exit(code)
