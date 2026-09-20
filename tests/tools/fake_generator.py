#!/usr/bin/env python3
"""A stand-in external generator, for exercising the adapter framework (P7-S01).

It behaves like Sherpa or Whizard in the two ways that matter to `hekit` and in no others:

* it has a **prepare** step that is expensive-looking, seed-independent and cacheable — here, writing
  a "grid" file into a directory the caller chooses;
* it **generates** by writing HepMC3 into a path that is usually a FIFO, printing progress lines a
  parser can read, and emitting exactly the number of events it was asked for.

The events come from an existing event store, so they are real events with real cross-sections and
the results can be compared with the run that produced them. That is the point: a framework test that
invents its own events can only check that processes started, whereas this one can check that the
right events came out of the far end.

Nothing in `hekit` imports this. The fake adapter that drives it lives in the test that uses it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

#: How a compressed shard is turned back into something `pyHepMC3` can read. Matches `Store`'s codecs.
DECOMPRESS = {".zst": ["zstd", "-dc"], ".zstd": ["zstd", "-dc"], ".gz": ["gzip", "-dc"]}


def shards(store: Path) -> list[Path]:
    """The store's shards, in index order when there is an index and by name when there is not."""
    index = store / "events.index.json"
    if index.is_file():
        document = json.loads(index.read_text(encoding="utf-8"))
        listed = [store / entry["file"] for entry in document.get("shards", [])]
        if listed:
            return listed
    return sorted(store.glob("events.*.hepmc*"))


def readable(path: Path, workdir: Path) -> Path:
    """A plain-ASCII copy of a shard, because `pyHepMC3` has no compressed reader."""
    command = DECOMPRESS.get(path.suffix.lower())
    if command is None:
        return path
    target = workdir / (path.stem + ".hepmc")
    with open(target, "wb") as handle:
        subprocess.run([*command, str(path)], stdout=handle, check=True)
    return target


def prepare(directory: Path) -> int:
    """The cacheable step: slow-looking, seed-independent, and it leaves something behind."""
    directory.mkdir(parents=True, exist_ok=True)
    print("fake: integrating", flush=True)
    time.sleep(0.05)
    (directory / "grid.dat").write_text("fake integration grid\n", encoding="utf-8")
    print("fake: integration done", flush=True)
    return 0


def generate(store: Path, out: Path, events: int) -> int:
    from pyHepMC3 import HepMC3

    written = 0
    with tempfile.TemporaryDirectory(prefix="fakegen-") as temporary:
        workdir = Path(temporary)
        # The writer is opened *last*: opening a FIFO for writing blocks until a reader arrives, and
        # doing it before the shards are decompressed would make `hep-run` wait for that too.
        sources = [readable(shard, workdir) for shard in shards(store)]
        writer = HepMC3.WriterAscii(str(out))
        try:
            for source in sources:
                if written >= events:
                    break
                reader = HepMC3.ReaderAscii(str(source))
                if reader.failed():
                    print(f"fake: cannot read {source}", file=sys.stderr, flush=True)
                    return 2
                try:
                    while written < events:
                        event = HepMC3.GenEvent()
                        reader.read_event(event)
                        if reader.failed():
                            break
                        writer.write_event(event)
                        written += 1
                        if written % 100 == 0:
                            # A progress line for the parser registry (06 §4) to pick up.
                            print(f"fake: event {written}", flush=True)
                finally:
                    reader.close()
        finally:
            writer.close()

    print(f"fake: wrote {written} events", flush=True)
    if written < events:
        # Deliberately not an error here: `hekit` is the one that decides a short stream is a
        # failure (04 §8), and the test that checks that needs this path to exist.
        print(f"fake: asked for {events}, had {written}", file=sys.stderr, flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="a stand-in external generator")
    parser.add_argument("--store", type=Path, help="event store to read events from")
    parser.add_argument("--out", type=Path, help="where to write HepMC3 (usually a FIFO)")
    parser.add_argument("--events", type=int, default=0)
    parser.add_argument("--prepare", type=Path, help="run the prepare step into this directory")
    parser.add_argument("--version", action="store_true")
    arguments = parser.parse_args(argv)

    if arguments.version:
        print("fake-generator 1.0")
        return 0
    if arguments.prepare is not None:
        return prepare(arguments.prepare)
    if arguments.store is None or arguments.out is None:
        parser.error("--store and --out are required to generate")
    return generate(arguments.store, arguments.out, arguments.events)


if __name__ == "__main__":
    raise SystemExit(main())
