# 11 — Event store and replay (HepMC3)

Date: 2026-09-17 · Status: Proposed · Steps: P5-S01…S03

**Decision D13.** Stored events are **HepMC3 files**, not ROOT trees. A store replays into the same analyzers as fresh events. This replaces the old `Probe` layer, which read the project's own TTrees. Replay is secondary (guideline 4): the store exists mainly because external generators already deliver HepMC, and because "generate once, analyse many" is useful for analysis-only sweeps.

## 1. Layout

```
results/<project>/points/<group>/events/
  events.index.json          written last, atomically (tmp + rename)
  events.0.hepmc.gz          one shard per generator worker (Parallelism:index)
  events.1.hepmc.gz
  …
```

**Why one shard per worker:**
- HepMC3 ASCII has no random access, so a single file can only be read serially. `ReaderMT` still scans the whole text.
- Per-worker shards are written without a lock.
- Each shard is a valid sample on its own.
- Replay can read them in parallel, one reader per shard.

**Compression.** Header-only `HepMC3/WriterGZ.h` / `ReaderGZ.h`, with the codec as a template parameter (`-DHEPMC3_USE_COMPRESSION`, `-DHEPMC3_Z_SUPPORT` and `-lz`; `-DHEPMC3_ZSTD_SUPPORT` and `-lzstd` when zstd is found).

**The default is `zst`** (decision **D-STORE-COMP**, measured in P5-S01 on 10 000 real photoproduction events — the spike is `tests/cxx/spikes/store_compression.cc`):

| codec | bytes/event | ratio | write ev/s | read ev/s |
|---|---:|---:|---:|---:|
| none | 29 197 | 1.00 | 6 333 | 6 249 |
| gz | 10 223 | 2.86 | 1 086 | 4 461 |
| **zst** | **9 866** | **2.96** | **2 289** | **5 624** |

zstd is smaller, twice as fast to write and a quarter faster to read; nothing favours gz. `gz` remains the fallback for a build without zstd, the index records which codec was used, and a build that cannot read it says so instead of failing at the first event.

**Serial mode.** With `processAsync = off`, callbacks run one at a time on changing threads. Shards are still keyed by `Parallelism:index` of the instance that generated the event, so the shard layout does not depend on the concurrency mode.

## 2. Index schema (`events.index.json`, version 1)

Annotated example; the real file is plain JSON with no comments. A JSON Schema is committed in P5-S01.

```jsonc
{
  "version": 1,
  "format": "hepmc3-ascii",
  "compression": "gz",
  "point": "eic_5x41_em_NNLO",
  "hash": "sha256:…",                        // generation hash of the producing point (03 §5)
  "provenance": "../provenance.json",
  "generator": {"tool": "pythia", "version": "8.317"},
  "beams": {"ids": [2212, 11], "energies": [41, 5]},
  "threads": 20,
  "seeds": [ … per-instance seeds … ],
  "weights": ["Weight", "MUR0.5_MUF1", "…"],
  "xsec_pb": 18290.0, "xsec_err_pb": 55.0,  // merged, from the generator (not a per-event estimate)
  "events": 1000000,
  "stopped": false,
  "shards": [
    {"file": "events.0.hepmc.gz", "events": 50000, "bytes": 812345678, "sha256": "…"},
    …
  ]
}
```

**Rules:**
- The sum of `shards[].events` equals `events`.
- `stopped = true` marks a partial store. Replay is allowed, but the result is marked partial.
- The index is written only after every shard is closed and hashed. A directory without an index is incomplete, and `hep store verify` reports it.
- Shards are streamed to `events.<k>.hepmc.gz.part` and renamed when they close.

## 3. Writing (`Analyzer::Store`)

- **Mode:** a Sharded analyzer (05 §2). Each worker owns a `WriterGZ<WriterAscii>` and writes `Events::View::hepmc()`.
- **Run info:** written once per shard, carrying the weight names and tool list.
- **At the end:** close the shards, then hash them, then write the index from `RunResult` (merged σ ± err, counts, seeds).
- **As a tee:** a `Analyzer::Store` pointed at a FIFO (no index) feeds external Delphes (04 / 07).

## 4. Replay (`Source::Store`)

```
shard k ──► reader thread k ──┐
shard …  ──► reader thread …  ├─► bounded queue ─► consumer workers (analyzers; sharded if allowed)
shard n ──► reader thread n ──┘
```

- **Queue:** the bounded queue with backpressure, stop flag and "all readers finished" condition is ported from `legacy/utils/Probe/Lifecycle.hh:229-267`.
- **Sources of truth:** σ, beams and weight names come from the **index**. Per-event `GenCrossSection` is ignored for stores.
- **Beam check:** beams are checked against the analyses, and the planner rejects any quantity that would change them.
- **Partial replay:** `events = N` reads shards in order until N events. `shards = [0, 3]` selects a subset. Skipping inside a shard is possible but still parses the events.
- **FIFO sources share the reader code.** `Source::Stream` is the same reader with no index; σ comes from the last event (04 §8).

**Replay hash.** A replay is a new point whose hash is `sha256(store hash + analysis configuration)`. Replaying the same store with the same analyses is skipped like any other point.

## 5. Configuration

```toml
[store]                       # write events of this run
enabled     = true
compression = "gz"            # gz | zst (after D-STORE-COMP) | none

[generator]                   # replay instead of generating
tool  = "store"
input = "eic_5x41_em_NNLO"    # point name, "sha256:…", or a path to an events/ directory
# events = 100000             # optional: first N events
```

- **Quantities:** on a store generator, only analysis-side quantities (`analysis`, `option`) are allowed. Any generation-side quantity is a planning error with a hint.
- **Event groups:** analysis-only sweeps (03 §4) can either share a live generation or replay a store. Both give the same result (tested in P5-S03).

## 6. CLI

| Command | Does |
|---|---|
| `hep store ls [PROJECT]` | Stores with events, size, compression, stopped flag, age |
| `hep store verify STORE` | Index present; shard hashes and counts match; files readable (`ReaderGZ` smoke test on the first and last event) |
| `hep store info STORE` | Pretty-prints the index and its provenance |
| `hep events STORE -n 3 [--tree/--final/--hard]` | Event tables and trees (06 §5) via `pyHepMC3` |
| `hep clean --events AGE` | Deletes old stores; YODA outputs and provenance are never touched |

## 7. Performance notes

- **Expected cost:** ASCII parsing dominates replay. Photoproduction events at EIC energies are small; heavy-ion events would feel it. Measure with `hep bench` (P6-S03).
- **Parallelism:** it scales with the number of shards, so a 20-thread generation replays with up to 20 readers.
- **Size:** gzip typically cuts ASCII 5–10×. zstd decompresses faster at similar size. Static by D-STORE-COMP.
- **Later, if replay becomes central:** HepMC3-ROOT or Protobuf I/O (neither is built here, and ROOT storage conflicts with D13), or a binary format per shard. See 10 §4.

## 8. What the old Probe offered, and where it went

| Probe feature | Store / module equivalent |
|---|---|
| Labelled particle collections joined per event | `Phys` selectors on `GenEvent` (by pid, status, ancestry) |
| Typed per-particle columns | `GenParticle` accessors plus `Phys` kinematics |
| Per-event scalars | HepMC weights and attributes (`GenCrossSection`, `GenPdfInfo`, custom) |
| Coordinate conversions | `Phys` kinematics (`Phys/Kinematics.hh`) |
| Callback on the reader thread or a collector pool | Consumer workers behind the bounded queue |
| Event-count resolution (user → metadata → scan) | `events` option → index → full read |
| First error stops everything, joins and rethrows | Same rule in `Run` |
