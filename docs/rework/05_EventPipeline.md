# 05 — `hep-run`: sources, sinks, concurrency

`hep-run` is the one C++ executable. It:
- reads a resolved spec (03 §7);
- opens one **source**;
- fans events out to **sinks**;
- emits status (06);
- writes a run summary for provenance (07).

Namespaces follow the house style ([13](13_Namespaces.md)): `Core`, `Status`, `Events`, `Source`, `Store`, `Results`, `Sink`, `Module`, `ML`, `Phys`, `Run`.

```
hep-run SPEC.toml                   # run
hep-run SPEC.toml --check           # read cards + init only, no events (exit 0/1/3)
hep-run SPEC.toml --plain           # no status fd; human progress lines on stderr (standalone use)
hep-run SPEC.toml --list N          # generate N events, emit them as "event" status messages (06 §5), no sinks
hep-run --capabilities              # JSON: built components (rivet, hepmc, compression, onnx, delphes), versions
```

**ROOT.** `hep-run` does not link ROOT, except when in-process Delphes is built, which is deferred. ROOT work happens in `hep proc` ([12](12_Processing.md)).

## 1. Event view (`Events::View`)

The event view is the common currency. Each event is converted **at most once**, and only if a sink needs it.

```cpp
namespace Events {
struct View {
    std::uint64_t index;                       // global accepted-event counter
    int           worker;                      // Parallelism:index of the producing instance (replay: shard id)
    const Pythia8::Pythia* pythia = nullptr;   // live generation only; null for store/stream sources
    const HepMC3::GenEvent& hepmc() const;     // lazy: Pythia8ToHepMC (per worker), or the read event
    double weight(std::size_t i = 0) const;
};
}
```

- **Needs `hepmc()`:** Rivet, the store sink, the Delphes tee, and modules written for replay.
- **Can skip the conversion:** a module that only runs during generation may use `pythia->event`, but then it cannot run on a store. Modules declare this via `Needs` (§2).
- **Accessors carried over from Probe** (00b §4): labelled collections via `Phys` selectors, typed per-particle values, per-event scalars (weights, attributes), and coordinate conversions.

## 2. Sink interface

```cpp
namespace Sink {
enum class Needs       : unsigned { Pythia = 1, HepMC = 2 };
enum class Concurrency { Serial, Sharded, Locked };

class Base {
public:
    virtual ~Base() = default;
    virtual std::string_view kind() const = 0;
    virtual unsigned         needs() const = 0;
    virtual Concurrency      concurrency() const = 0;
    virtual void begin(const Run::Context&) = 0;         // after source init: beams, √s, seeds known
    virtual void consume(const Events::View&) = 0;
    virtual void checkpoint(const Run::Context&) {}      // every run.checkpoint events
    virtual void end(const Run::Result&) = 0;            // σ ± err, weight sum, n, stopped?
    virtual void summary(Status::Writer&) const {}       // fragment for the final report
};

// Sharded sinks are created per worker and merged at the end.
class Sharded : public Base {
public:
    virtual std::unique_ptr<Base> shard(int worker) = 0;
    virtual void merge(std::vector<std::unique_ptr<Base>>& shards) = 0;
};
}
```

**Creating sinks:**
- Sinks are created from `[[sink]]` entries by a small factory keyed by `kind`: `rivet`, `module`, `store`, `delphes`.
- Optional kinds are registered only when their CMake component is built.
- Asking for a missing kind is a spec error, which `hep plan` catches first using `hep-run --capabilities`.

## 3. Concurrency (`Run`)

| Mode | Pythia setting | Sink calls | When |
|---|---|---|---|
| `serial` | `processAsync = off` | all sinks on the callback thread | Simplest; today's behaviour |
| `sharded` | `processAsync = on` | `Sharded` sinks get a per-worker shard; `Locked` sinks go through one mutex | Analysis cost is comparable to generation (01 A4) |
| `auto` (default) | — | `sharded` if threads > 1 **and** every Rivet analysis is `Reentrant: true` **and** jet clustering is thread-safe in this build **and** at least one sink is shardable; otherwise `serial`, with a notice naming the reason | — |

Set with `[run].mode`, which is a machine key: it changes the wall clock, not the events, and is not
part of a point's identity.

**Jet clustering is the binding constraint** (00/B31, measured in P6-S01). SISCone keeps its
clustering cache and its RNG in process-wide statics in *every* FastJet build, and this installation's
FastJet is built without `FASTJET_HAVE_LIMITED_THREAD_SAFETY` besides. Two threads clustering at once
do not crash; they change each other's jets. Whether an analysis clusters is only knowable after
`Analysis::init()`, which Rivet calls on the first event, so the question is answered twice:

- **before any event**, which is what `auto` uses — without a thread-safe FastJet *no* analysis may be
  sharded, because any of them might cluster and there is no way to ask yet;
- **immediately after `init()`**, which is what an explicit `sharded` runs into — if a `FastJets`
  turns up, the run stops. A jet race produces a plausible histogram with the wrong numbers in it,
  which is worse than no histogram.

`photo_eic` runs kT, anti-kT and SISCone, so it is always serial. The sharded path is exercised by the
event store (one shard per worker, no lock) and by jet-free analyses.

**A merge is not enough to make every object mergeable.** `Reentrant: true` says an analysis'
`finalize` can be re-run; it does not say every object it books *adds*. `MC_XS` is re-entrant and
still has one object, `XS`, which it `set()`s from the per-event running σ — a snapshot, which four
handlers cannot reconstruct and `AnalysisHandler::merge` falls back to copying. The rule for modules
(P8-S01) follows: **`fill` merges, `set` does not.** A run's σ is not affected: it comes from the
generator, is applied once to the merged total (D-Q1), and lands in `/_XSEC` and `run.summary.json`.

**Decision rule.** Measure, don't guess: `hep bench` (P6-S03) times generation only, generation with
sinks serially, the same sharded, and a replay, then recommends a mode. It recommends `sharded` only
when it was *allowed* and measured at least 1.15x faster — a refused leg is reported as its reason,
which is the more useful answer. Measured on PhotoProduction: the sinks are **~75 % of a serial run's
wall clock** (assumption 01 A4, answered), a replay reads back ~1.5x faster than generating, and
sharding is refused outright because the analysis clusters jets.

**Reproducibility** (corrected; the earlier "timing-dependent" note was wrong):
- `Parallelism:balanceLoad` is **on** by default. Events are split evenly between instances, and each instance has its own seed (`Parallelism:seeds`, or `Random:seed + i`).
- So a fixed seed and thread count give the **same event set**; only the processing order differs.
- Order-sensitive outputs are bit-identical only with `threads = 1`: text files, and possibly floating-point sums in a different order.
- Histogram contents are equal up to floating-point summation order.
- Provenance records the mode, thread count and instance seeds.

**Chunking** (measured in P2-S02, D-Q2). `Run::loop` calls `run(chunk)` repeatedly after one `init()`,
because `PythiaParallel::run` cannot be interrupted from its callback, and a chunk boundary is the only
place to stop, dump or checkpoint. Measured properties:
- counts and σ are correct and **cumulative** across chunks (σ after the last chunk equals a single run's);
- the event set is **bit-identical** to one `run(N)` when every chunk's per-thread split matches, which
  holds when the chunk size is a multiple of the thread count. `chunk = threads · ceil(target / threads)`,
  remainder in the last chunk; the effective chunk size goes into provenance.

**Merged σ** (D-Q1). `PythiaParallel` exposes `sigmaGen()` and `weightSum()` but **no error**, so `Run`
combines the instances with `foreach`: σ = Σwᵢσᵢ / Σwᵢ and error = √(Σ(wᵢ·errᵢ)²) / Σwᵢ. The σ reproduces
`sigmaGen()` exactly, and the error tracks a serial `stat()` to within the statistical difference.

**Seeds.** The planner renders `Parallelism:seeds` as a disjoint block per point (03 §5, 00/B2). `Run`
records the effective per-instance seeds, read back with `foreach`, and **checks the list length against
the thread count before `init()`**: Pythia indexes the list without bounds checking, so a short list is
undefined behaviour rather than the documented error (D-SEEDS). With `threads = 0` the list is omitted and
Pythia derives `Random:seed + i`, which is the same block.

**Replay and stream sources parallelise too:**
- one reader thread per shard (or per FIFO) fills a bounded queue;
- N consumer workers pop from it, each owning sink shards.

## 4. Sources

### `Source::Pythia`
- **Set-up** (`PythiaParallel`):
  1. `readFile` for each card in spec order; any `false` → exit 1;
  2. force the run control from the spec (events, threads, seeds, `processAsync` per mode, `Next:numberCount = 0`);
  3. `init()`; failure → exit 3.
- **Output only after `init()`.** No output is opened before init succeeds, which is a `generator.cc` behaviour to keep.
- **Chunked run:** `run(chunk, callback)` is called repeatedly, with
  `chunk = threads · ceil(min(checkpoint, remaining) / threads)` and the remainder in the last chunk
  (**D-Q2, measured in P2-S02**).
  - This gives clean stop points (SIGINT) and checkpoints, since `PythiaParallel` has no abort API.
  - `run()` returns per-thread counts, which feed the per-worker status.
  - Counts and σ accumulate correctly across chunks, and a chunk size that is a multiple of the thread
    count reproduces the unchunked event set exactly. A chunk size that is *not* gives a different
    (statistically equivalent) sample, which is why the rule above rounds up to the thread count.
- **σ at the end:** merged `sigmaGen()` [mb → pb].
  - **D-Q1 (measured in P2-S02):** the error comes from `foreach` over the instances (`info.sigmaErr()`
    weighted by `info.weightSum()`), because `PythiaParallel` exposes no error of its own. The combined σ
    reproduces `sigmaGen()` exactly and agrees with a serial `stat()` within statistics.
- **Warnings:** the Pythia `Logger` counts are read at checkpoints and at the end, and emitted as `log` messages (06 §3).
- **LHE:** the same class. The cards set `Beams:frameType = 4` and `Beams:LHEF`.

### `Source::StoreReplay`
Replays a HepMC3 store ([11](11_EventStore.md)):
- one reader per shard → bounded queue (ported from `legacy/utils/Probe/Lifecycle.hh:229-267`) → consumers;
- σ, beams and weight names come from `events.index.json`;
- `events` / `shards` options for partial replay.

### `Source::Stream`
- HepMC3 ASCII from one or more FIFOs or files: external generators, or ad-hoc files. Several inputs are read in rotation (Herwig `-j N`).
- The same reader code as `StoreReplay`, without an index.
- σ comes from the **last** event's `GenCrossSection` (04 §8). The event count is checked against the spec.
- Compressed files use `ReaderGZ` (compile-time flags, 09 §1).

## 5. Sinks

### `Sink::Rivet` (Sharded)
- **Per shard:** an `AnalysisHandler`, the analyses with options, `setCheckBeams`, and the weight policy (`nominal` → skip multi-weights; `all`).
- **Initialisation:** Rivet initialises from the first event. Construction and first-event init run under a global lock (Rivet is not thread-safe there).
- **End of run:**
  1. merge the shards into shard 0 (`AnalysisHandler::merge`);
  2. `setCrossSection(σ, err, true)` from `Run::Result`;
  3. `finalize()`;
  4. hand `getYodaAOs()` to `Results::Writer`, which writes `analysis.yoda` together with the module objects.
- **Not used:** `Pythia8Plugins/RivetHooks.h`, whose `onStat` may double-merge.
- **Periodic dumps** (`dump_every`):
  - only for re-entrant analyses (Rivet 4.1.3 skips `finalize` in dumps otherwise, `AnalysisHandler.cc:700-705`);
  - written to `analysis.dump.yoda`;
  - in sharded mode they need a merge of copies, so they are off by default there.
- **Equivalence gates:**
  - serial vs FIFO legacy (P2-S06);
  - serial vs sharded (P6-S01).

### `Sink::Store` (Sharded)
- **Per-worker writer:** a `WriterGZ<WriterAscii>` into `events/events.<k>.hepmc.gz.part`, renamed on close.
- **Index:** written last ([11](11_EventStore.md) §2–3).
- **Tee mode:** pointed at a FIFO, with no index. It feeds external Delphes.

### `Sink::Modules` (Sharded) — user C++ analysis, results in YODA
```cpp
namespace Module {
class Base {                                           // modules/<project>/<Name>.cc → libhekit_<name>.so
public:
    virtual ~Base() = default;
    virtual void configure(const Core::Options&) = 0;         // from [[sinks.module]].options
    virtual void book(Results::Booker&) = 0;                  // declare YODA objects (Histo1D/2D, Profile1D, Counter, Estimate)
    virtual void process(const Events::View&, Results::Worker&) = 0;   // fill this worker's clones
    virtual void finalize(Results::Final&, const Run::Result&) {}      // scale/derive after the merge (σ, ΣW known)
    virtual unsigned needs() const { return unsigned(Sink::Needs::HepMC); }
};
}
HEKIT_MODULE("mymodule", MyModule);
```

- **`Results` owns the objects:**
  - declare-time validation (names, binning, duplicates);
  - one clone per worker;
  - merge by adding;
  - an explicit **scaling contract**: fills are raw weights, and scaling happens only in `finalize`.
  - These ideas come from `legacy/utils/Record/{Cloning,Declaration}.hh`, and they avoid Record's "unscaled finals" and "empty checkpoints" defects.
- **One output file:** module objects are written into the **same** `analysis.yoda` as Rivet, under `/<module>[:opts]/<name>`, so `rivet-mkhtml` and `hep plot` treat them alike.
- **Merge caveat.** `rivet-merge` re-runs `finalize` only for loadable Rivet analyses, so `hekit` merges module objects itself for seed replicas (07 §3).
- **Loading:** modules are loaded with `dlopen` from the configured paths, like Rivet plugins, so `hep-run` is not rebuilt per project.
- **ML:** a module may hold an `ML::OnnxModel`.
- **Derived per-candidate tables** (ML features) are **deferred** (decision D-DERIVED, P8-S04). Modules produce YODA only.

### `Sink::Delphes` (optional)
| Mode | How |
|---|---|
| `external` (the only mode for now) | A `Sink::Store` tee on a FIFO feeds `DelphesHepMC3 <card> delphes.root <fifo>` as a supervised stage. This keeps Delphes' ROOT/`TObject` global state out of our process. |
| `inprocess` (deferred) | `DelphesFactory` fed from `Events::View`, like `DelphesPythia8`. Serial only. It would link ROOT, and Delphes' global `class Event` clashes are the reason the namespace is called `Events` (13 §3). |

**Detector-level analysis:** RDataFrame/uproot on `delphes.root` via `hep proc` ([12](12_Processing.md)), with results written as YODA. Rivet 4's built-in smearing projections are an alternative for quick studies.

## 6. ML: ONNX Runtime (`ML`)

```cpp
namespace ML {
class OnnxModel {
public:
    explicit OnnxModel(const std::filesystem::path&, Options = {});   // checks input/output names and shapes
    std::span<const float> run(std::span<const float> in, Scratch&) const;   // thread-safe; Scratch is per worker
    const std::string& sha256() const;                                   // into provenance
};
}
```

- **Sessions:** one `Ort::Env` and one session per model. `Session::Run` is thread-safe, so shards share the session and own their scratch buffers.
- **Optional component:** `HEKIT_WITH_ONNX`.
- **In Rivet plugins:** use Rivet's `RivetONNXrt`. The build adds ONNX flags to `rivet-build` when a plugin's `.info` lists `ONNX` under `Requires:` (a project convention).
- **Training data export** is deferred with the derived-tables decision (P8-S04).

## 7. FastJet and LHAPDF

**FastJet:**
- linked through Rivet for plugins;
- modules use it through `Phys` (`Phys/Jets.hh`: `jetDefinition("antikt:0.4")`).

**LHAPDF:**
- used by Pythia (`LHAPDF6:` sets), Sherpa and Herwig through their own interfaces; never called in our event loop;
- `hep pdf check` lists the sets a plan needs, and `hep pdf install` fetches missing ones.

## 8. Size budget

| Namespace(s) | Estimated lines |
|---|---|
| `Core` + `Status` | 750 |
| `Events` + `Source` (Pythia, StoreReplay, Stream) | 550 |
| `Store` | 350 |
| `Results` + `Module` | 450 |
| `Sink` (Rivet, Store, Modules, Delphes tee) | 350 |
| `Run` | 250 |
| `ML` + `Phys` | 300 |
| `apps/hep-run.cc` | 150 |
| **Total** | **≈ 3,150** |

For comparison, the current `utils/` is about 10,600 lines. The increase over the first estimate (≈ 2,450) comes from the store and the YODA results layer.
