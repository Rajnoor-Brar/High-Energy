"""The v2 runner (docs/02_Architecture.md §3).

One flat package. A module imports only from its own rank or a lower one, with no cycles;
tests/runner/test_imports.py holds the table and enforces both.

    rank 0   errors, paths, status_client
    rank 1   config, quantities, sweep
    rank 2   tools
    rank 3   execute, status, record
    rank 4   watch, plot
    rank 5   cli
"""
