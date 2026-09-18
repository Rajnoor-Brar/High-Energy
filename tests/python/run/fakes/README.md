# Fake stages

Small programs that behave like a pipeline stage in one specific way, so the supervisor's rarest paths
(a hang, a flood, a process that ignores SIGINT, a reader that dies mid-stream) can be tested in
seconds instead of waiting for a real generator to misbehave.

Each one is a plain script with no imports beyond the standard library, runnable by hand:

| Fake | Behaviour |
|---|---|
| `early_exit.py` | exits with a given code before touching the FIFO — the case that used to hang `rivpyth` |
| `writer.py` | writes to a FIFO until it is stopped, or for N blocks |
| `reader.py` | reads a FIFO, then exits with a given code (or dies by a signal) |
| `hang.py` | opens nothing, prints nothing, sleeps |
| `flood.py` | writes N MiB to stderr as fast as it can |
| `ignores_sigint.py` | sets SIGINT to ignore, then loops until SIGTERM |
| `statusful.py` | writes `hep-run`-shaped status JSON on the descriptor it is told to use |
