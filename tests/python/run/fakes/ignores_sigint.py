#!/usr/bin/env python3
"""Ignore SIGINT and keep going, until SIGTERM (or SIGKILL) arrives. `ignores_sigint.py [seconds]`"""
import signal
import sys
import time

signal.signal(signal.SIGINT, signal.SIG_IGN)
if "--also-term" in sys.argv:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)     # only SIGKILL will do
print("ignoring SIGINT", flush=True)
time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3600.0)
