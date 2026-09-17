# ProbeStream — Event / Feed streaming model

Updated: 2026-05-20.

Phased plan to replace the single-`StreamType` model in `utils/Probe/` with a
two-bucket (Event / Feed) model, two stream classes, and a three-method
public API.

---

## Existing infrastructure (inventory)

Inventory of what's already in `utils/Probe/` and adjacent. The plan reuses
all of this — the rewrite is additive plus targeted renaming, not a fresh
build.

### Types (`Probe/Types.hh`)

| Symbol | Status | Action |
|---|---|---|
| `BranchType` (alias for `RootUtil::DataType`) | Full enum: Float, Double, Int32, UInt32, Int64, UInt64, Bool, Char, String, Other | **Reuse as-is** |
| `BranchSpec { name, type }` | Existing | **Reuse as-is** |
| `CoordSpec = variant<CartesianSpec, PtEtaPhiESpec, PtEtaPhiMSpec>` | Existing, holds `vector<BranchSpec> branches` | **Reuse as-is** |
| `AuxColumn` | Variant of `vector<int64_t>, vector<uint64_t>, vector<double>, vector<bool>` | **Extend** to cover `float`, `int32_t`, `uint32_t` (needed for NodeBranch breadth) |
| `EventKey { vector<Long64_t> components }` | Multi-component index keys | **Reuse** — keep multi-component capability |
| `Bounds { first, last }` | Existing | **Reuse** |
| `Event { index, particles, aux }` | `aux` is nested `map<label, map<col, AuxColumn>>` | **Rename** `particles→particle`, `aux→node`; semantics of `node` becomes "independent of particle labels" |
| `QueuedEvent { workerIndex, eventIndex, event }` | Queue payload | **Extend** to `QueuedFrame` carrying both `Event` and `Feed` for Mixed mode |
| `StreamType { Unset, Events, Vectors }` | Single discriminator | **Replace** with `StreamMode { Auto, Events, Feed }` + `ActiveMode { Events, Feed, Mixed }` |
| `CollectionSpec { label, tree, coords, indexBranches, auxBranches, indexSorted, indexAscending, indexMonotonic }` | Per-particle spec | **Split** into `EventParticleSpec`, `EventNodeSpec`, `FeedParticleSpec`, `FeedNodeSpec` |
| `CallbackMode { WorkerThread, CollectorThread }` | Existing | **Reuse** |

### Readers (`Probe/Readers.hh`, `Probe/Methods.hh`)

| Symbol | Status | Action |
|---|---|---|
| `FlatReader` | Row-indexed drain of 4 kinematic branches + aux | **Repurpose** as backing for `EventParticleReaderRowJoin` (rename or keep) |
| `VecReader` | Per-entry `TTreeReaderArray<float>` over 4 kinematic branches + aux | **Repurpose** as backing for `EventParticleReaderArray` |
| `EventStream` (with `nextFlat`/`nextVec`/`isVec_`) | Single-flavor stream | **Generalize** to polymorphic-reader loop; keep file ownership and tree caching |

### Branch control (`Probe/BranchControl.hh`)

All utilities are reusable as-is:

- `enableRootThreadSafety()` — must be called before any reader construction
- `requireBranch`, `requireType` — error-checked branch lookup
- `KinBuf` — float-or-double kinematic branch holder
- `coordNames(CoordSpec)`, `makeLorentz(CoordSpec, a, b, c, d)` — coord variant dispatch
- `partitionEvents(ids, n)` — event-range partitioning for workers
- `scanIndexBranch`, `probeFirstKey` — index-branch utilities

### Config (`Probe/ConfigAid.hh`)

- `parseCollectionsFromToml` — old `[probe].event_particles` parser. **Replace** with `parseProbeConfig`; keep old function as a transition shim in Phase 3 then delete in Phase 11.
- `applyIndexSpecsFromToml` — reads `[probe.index].sorted/ascending/monotonic` bool arrays. **Migrate** to per-section flags (move into each `EventParticleSpec`).
- `resolveEventCount` — reads `About/events/n_events_total`. **Reuse as-is**.

### ProbeParallel (`Probe/Parallel.hh` + `Probe/Administration.hh` + `Probe/Directives.hh`)

| Symbol | Status | Action |
|---|---|---|
| Queue (`std::deque<QueuedEvent>`, mutex, cvs, `produced_`/`consumed_`) | Working backpressured channel | **Reuse**; only payload changes |
| `pushQueuedEvent` / `popQueuedEvent` / `markWorkerFinished` | Working | **Reuse** with widened payload type |
| `prepareEventPartitions`, `prepareEntryBounds` | Event-range partitioning + per-row bounds | **Reuse** |
| `eventPartitions_`, `entryBoundsByWorker_` | Worker partition state | **Reuse** |
| `runWorkerThread`, `runCollectorThread` | Threading templates | **Generalize** to dispatch on Event/Feed/Mixed |
| `run(Callback&&)` | Single entry point | **Replace** with `streamEvents` / `streamFeed` / `stream(ce, cf)` |
| `streamType()`, `determineStreamType()` | Single-discriminator helpers | **Replace** with `activeMode()` and `determineActiveMode()` |
| `configureProbe(..., vector<CollectionSpec>, ...)` | Single-spec list | **Change** to take `ProbeConfig` |

### What stays untouched

- `Probe/ParallelIMT.hh` and `ProbeIMT` — independent IMT path; no changes needed.
- `Physics::Lorentz` — unchanged.
- `RootUtil::DataType`, `detectBranchType`, `typeName`, `leafListSuffix` — full coverage of the type codes we need; reuse for the dual-syntax branch parser.
- `BranchControl` utilities — reuse all.

---

## Concepts

### Two structs, two semantics

| Struct  | Per-label accessor returns | Semantic |
|---------|----------------------------|----------|
| `Event` | `event.particle[L]` → `vector<Lorentz>`<br>`event.node[L][branch]` → `AuxColumn` (a `vector<T>`-variant) | A collection of items belonging to one event. |
| `Feed`  | `feed.particle[L]` → `Lorentz`<br>`feed.node[L][branch]` → `AuxValue` (scalar or array variant) | One value per label per source entry (one entry = one event). |

The two `node` maps are **independent of the `particle` maps**: there is no
structural requirement that `event.node["muon"]` parallels `event.particle["muon"]`.
The existing nested `aux` field already has the two-level
`map<label, map<branch, AuxColumn>>` shape — the rename is mechanical, and the
"independent of particle" semantics is achieved by just not requiring the
outer label to match a particle label.

### Two streams

- `EventStream` — drains data into `Event` structs, one per event.
- `FeedStream` — drains data into `Feed` structs, one per source entry.

Both share the event-index identifier (entry number of per-entry trees ≡
`event_index` column of row-indexed trees), so they iterate in lockstep when
used together.

### Three call modes on `ProbeParallel`

```cpp
template <typename CB> void streamEvents(CB&& ce);
template <typename CB> void streamFeed  (CB&& cf);
template <typename CE, typename CF> void stream(CE&& ce, CF&& cf);
```

Callback signatures:

```cpp
ce: void(const Event&, int collectorId);
cf: void(const Feed&,  int collectorId);
```

- `streamEvents` throws if no event-bound data is configured.
- `streamFeed` throws if no feed-bound data is configured.
- `stream(ce, cf)` auto-routes:
  - Only event-bound data → only `ce` is invoked.
  - Only feed-bound data → only `cf` is invoked.
  - Both → both `ce(event)` and `cf(feed)` per event with synchronized data
    (the "pair<Event, Feed>" semantic is realized as two consecutive
    callbacks for the same event).
  - Neither → throws.

### Default stream selection

A top-level `stream = "events" | "feed" | "auto"` key in `[probe]` controls
default mode. Auto-detection rules:

| `[probe.events]` declared? | `[probe.feed]` declared? | Active mode |
|---|---|---|
| Yes | No  | `Events` |
| No  | Yes | `Feed` |
| Yes | Yes | `Mixed` |
| No  | No  | error at parse time |

`stream = "events"` is incompatible with an empty `[probe.events]` declaration
(throws). Symmetric for `stream = "feed"`. `stream = "auto"` is the default
and never throws on the discriminator alone.

---

## TOML schema

### Declaration / definition split

```toml
[probe]
stream  = "auto"                       # optional; default "auto"

[probe.events]                         # declaration block
particles = ["muon", "jet"]
nodes     = ["hits", "trig_obj"]

[probe.feed]
particles = ["leading_jet"]
nodes     = ["weights", "met"]

[probe.events.particles.muon]
tree     = "Events"
spec     = 2                           # 0 Cartesian, 1 PtEtaPhiE, 2 PtEtaPhiM
branches = ["Muon_pt", "Muon_eta", "Muon_phi", "Muon_mass"]

[probe.events.particles.jet]
tree     = "Events"
spec     = 2
branches = ["Jet_pt", "Jet_eta", "Jet_phi", "Jet_mass"]
aux      = [["Jet_btagDeepFlavB", "F"]]   # per-particle aux columns

[probe.events.nodes.hits]
tree     = "Hits"
index    = ["event_index", "L"]            # row-indexed source
branches = [["energy", "F"], ["time", "F"], ["channel", "I"]]

[probe.events.nodes.trig_obj]              # per-entry array source (no index)
tree     = "Events"
branches = [{ name = "TrigObj_pt", type = "F" },
            { name = "TrigObj_eta", type = "F" },
            { name = "TrigObj_filterBits", type = "I" }]

[probe.feed.particles.leading_jet]
tree     = "Events"
spec     = 2
branches = ["LeadingJet_pt", "LeadingJet_eta", "LeadingJet_phi", "LeadingJet_mass"]

[probe.feed.nodes.weights]
tree     = "Events"
branches = [["genWeight", "F"], ["pu_weight", "F"]]

[probe.feed.nodes.met]
tree     = "Events"
branches = [{ name = "MET_pt", type = "F" }, { name = "MET_phi", type = "F" }]
```

### Conventions inherited from existing schema

- The `spec` field on a `particles` block is the existing
  `0 = Cartesian | 1 = PtEtaPhiE | 2 = PtEtaPhiM` coding from
  `detail::makeCoordSpec`. Keep it.
- Index branches use the existing two-element pair form `["name", "type"]`
  matching `index_branch` in the current schema. The `index` key on
  event-node sections is the same format.
- Branch-list type codes use `RootUtil::detectBranchType(char)` (existing):
  `F` Float, `D` Double, `I` Int32, `i` UInt32, `L` Int64, `l` UInt64,
  `O` Bool, `B` Char, `C` String.

### Branch syntax — three forms supported

For a `branches` array element:

```toml
# Inline table  (toml++ inline-table syntax)
{ name = "MET_pt", type = "F" }

# Two-element array  (matches existing index_branch / branch_N format)
["MET_pt", "F"]

# Bare string  (only legal in particle 4-kinematic lists)
"MET_pt"
```

For `index` on event-nodes: two-element form `["event_index", "L"]`. Same as
the existing `index_branch` convention.

For per-particle `aux` on event-particles: same forms as `branches`.

### Per-section index monotonicity flags

The existing `applyIndexSpecsFromToml` reads three element-wise bool arrays
from `[probe.index]`. Migrate these into per-section optional fields:

```toml
[probe.events.particles.muon]
# ... above ...
index           = ["event_index", "L"]
index_sorted    = true                    # default true
index_ascending = true
index_monotonic = true
```

When set inside a section, they apply to that section's index. The legacy
`[probe.index]` block stays parseable as a transitional fallback until
Phase 11.

### Validation rules (config-parse time)

| # | Rule | Throw message |
|---|------|---------------|
| 1 | Event-bound section without `index` → branches must be array-typed leaves at runtime (only checked once trees are opened) | "scalar branch 'B' in [probe.events.X.Y] requires `index` key or array-typed source" |
| 2 | Event-bound section with `index` → branches must be scalar leaves (array-ness comes from drained rows) | "array-typed branch 'B' in [probe.events.X.Y] cannot coexist with `index` key" |
| 3 | Feed-bound section must not have `index` key | "[probe.feed.X.Y]: `index` not permitted in Feed" |
| 4 | Declared label has no matching definition | "[probe.events.particles]: label 'Y' declared but no [probe.events.particles.Y] block found" |
| 5 | Defined label not declared anywhere | silently ignored (supports library configs) |
| 6 | `stream = "events"` but `[probe.events]` declarations empty | "stream='events' but no event-bound labels declared" |
| 7 | Same label in both `[probe.events.particles]` and `[probe.feed.particles]` | "label 'Y' declared in both events and feed" |
| 8 | Particle section without exactly 4 kinematic branches | (existing rule from `parseCollectionsFromToml`) "'X' must have exactly 4 momenta branches, got N" |

```cpp
// ALTERNATIVE for rule 7: allow shared labels across buckets. Decision:
// forbid; ambiguity outweighs the rare convenience. Reconsider if a real use
// case emerges.
```

---

## Data structures

### `utils/Probe/Types.hh` — additions

```cpp
// AuxValue — single value (possibly array-typed), used by Feed.node.
// Mirrors the breadth of RootUtil::Value plus optional array forms.
using AuxValue = std::variant<
    double, float, int32_t, uint32_t, int64_t, uint64_t, bool,
    std::vector<double>, std::vector<float>,
    std::vector<int32_t>, std::vector<uint32_t>,
    std::vector<int64_t>, std::vector<uint64_t>,
    std::vector<bool>
>;

// AuxColumn — broaden to cover float/int32/uint32 in addition to existing
// alternatives. The current four-alternative form is too narrow once nodes
// accept all six numeric leaf types.
struct AuxColumn {
    std::variant<
        std::vector<double>, std::vector<float>,
        std::vector<int32_t>, std::vector<uint32_t>,
        std::vector<int64_t>, std::vector<uint64_t>,
        std::vector<bool>
    > data;

    template<typename T>
    const std::vector<T>& as() const {
        if (const auto* p = std::get_if<std::vector<T>>(&data)) return *p;
        throw std::runtime_error("[Probe] AuxColumn type mismatch");
    }
    void clear() { std::visit([](auto& v){ v.clear(); }, data); }
};

// ALTERNATIVE: collapse AuxValue and AuxColumn to a single variant of pointers
// or use type-erased holders. Decision: keep two named types — the variant
// alternatives differ (scalars in AuxValue, only vectors in AuxColumn), and
// the type system carrying the bucket distinction prevents misuse.

enum class StreamMode { Auto, Events, Feed };
enum class ActiveMode { Events, Feed, Mixed };
```

### `Event` and `Feed` structs

```cpp
struct Event {
    Long64_t                                                                index{-1};
    std::unordered_map<std::string, std::vector<Lorentz>>                   particle;
    std::unordered_map<std::string, std::unordered_map<std::string, AuxColumn>> node;

    // Convenience accessors — throw on missing key (analysis code shouldn't
    // silently use empty defaults).
    const std::vector<Lorentz>& particles(const std::string& label) const;
    const std::unordered_map<std::string, AuxColumn>& nodes(const std::string& label) const;
    std::size_t n(const std::string& label) const;   // existing helper

    template<typename T>
    const std::vector<T>& column(const std::string& label, const std::string& col) const;
};

struct Feed {
    Long64_t                                                                  index{-1};   // entry number
    std::unordered_map<std::string, Lorentz>                                  particle;
    std::unordered_map<std::string, std::unordered_map<std::string, AuxValue>> node;

    const Lorentz&                                              particles(const std::string& label) const;
    const std::unordered_map<std::string, AuxValue>&            nodes(const std::string& label) const;

    template<typename T>
    const T&                                                    value(const std::string& label, const std::string& col) const;
};

// ALTERNATIVE: collapse Feed.node to a single-level map<label, AuxValue> if
// each Feed-node section is restricted to one branch. Decision: nested map
// matches Event.node and preserves grouping (e.g. `met.MET_pt`, `met.MET_phi`
// under one logical "met" node). The user can still single-branch if they want.
```

### Config-side specs

```cpp
struct EventParticleSpec {
    std::string                  label;
    std::string                  tree;
    CoordSpec                    coords;
    std::vector<BranchSpec>      indexBranches;   // empty → per-entry array source
    std::vector<BranchSpec>      auxBranches;     // per-particle aux (existing)
    bool indexSorted    = true;
    bool indexAscending = true;
    bool indexMonotonic = true;
};

struct EventNodeSpec {
    std::string                  label;
    std::string                  tree;
    std::vector<BranchSpec>      indexBranches;   // empty → per-entry array source
    std::vector<BranchSpec>      branches;        // the node's column set
    bool indexSorted    = true;
    bool indexAscending = true;
    bool indexMonotonic = true;
};

struct FeedParticleSpec {
    std::string                  label;
    std::string                  tree;
    CoordSpec                    coords;
    // No index, no aux — Feed is strictly per-entry scalar.
};

struct FeedNodeSpec {
    std::string                  label;
    std::string                  tree;
    std::vector<BranchSpec>      branches;
};

struct ProbeConfig {
    StreamMode                       requestedMode = StreamMode::Auto;
    std::vector<EventParticleSpec>   eventParticles;
    std::vector<EventNodeSpec>       eventNodes;
    std::vector<FeedParticleSpec>    feedParticles;
    std::vector<FeedNodeSpec>        feedNodes;

    bool hasEventData() const {
        return !eventParticles.empty() || !eventNodes.empty();
    }
    bool hasFeedData() const {
        return !feedParticles.empty() || !feedNodes.empty();
    }
};
```

`EventParticleSpec` is **identical** to the existing `CollectionSpec` minus
the redundancy with the renamed event-particle / event-node split. The
transition can keep `CollectionSpec` as a type alias for one phase to avoid
churn:

```cpp
// During transition (Phase 1–7):
using CollectionSpec [[deprecated]] = EventParticleSpec;
```

---

## ProbeParallel API surface

```cpp
class ProbeParallel {
public:
    void configureProbe(std::string inputFile,
                        ProbeConfig  config,
                        std::size_t  threadCount,
                        std::size_t  requestedEvents,
                        bool         userRequestedEvents);

    void setCallbackMode(CallbackMode mode);
    void setQueueCapacity(std::size_t capacity);
    void setAnalysisThreadCount(std::size_t n);

    template <typename CB>             void streamEvents(CB&& ce);
    template <typename CB>             void streamFeed  (CB&& cf);
    template <typename CE, typename CF> void stream(CE&& ce, CF&& cf);

    ActiveMode  activeMode() const;
    std::size_t eventCount() const;
    std::string stats() const;

private:
    ProbeConfig config_;
    ActiveMode  activeMode_ = ActiveMode::Events;
    // ... existing private members (queue, mutexes, partitions) ...
};
```

Behavior table:

| Method called   | Active mode (resolved) | Outcome |
|---|---|---|
| `streamEvents`  | Events | Calls `ce(event, tid)` per event |
| `streamEvents`  | Feed   | **Throws** "streamEvents called but no event-bound data configured" |
| `streamEvents`  | Mixed  | Calls `ce(event, tid)` per event; feed data still read but discarded |
| `streamFeed`    | Events | **Throws** "streamFeed called but no feed-bound data configured" |
| `streamFeed`    | Feed   | Calls `cf(feed, tid)` per entry |
| `streamFeed`    | Mixed  | Calls `cf(feed, tid)` per event; event data still read but discarded |
| `stream(ce,cf)` | Events | Calls only `ce` |
| `stream(ce,cf)` | Feed   | Calls only `cf` |
| `stream(ce,cf)` | Mixed  | Calls `ce(event, tid)` then `cf(feed, tid)` per event |

```cpp
// ALTERNATIVE for "Mixed + streamEvents": throw instead of discarding feed
// data. Decision: discard, because the user explicitly chose the event-only
// callback and may be running an event-only analysis on data that happens to
// have feed sections defined (e.g. shared library config). Add a warning at
// first call if this proves surprising.
```

---

## Reader hierarchy

Two parallel hierarchies, one per output struct. Each Event reader has two
"flavors" reflecting the storage layout. Most logic is **lifted from the
existing `FlatReader` and `VecReader` bodies** — the renames make explicit
what those classes already do.

```cpp
// Event-side readers populate slices of an Event for event index K.
class EventReader {
public:
    virtual ~EventReader() = default;
    virtual void seekToEvent(Long64_t K) = 0;
    virtual void readForEvent(Long64_t K, Event& out) = 0;
    virtual Bounds eventRange() const = 0;
    virtual std::string treeName() const = 0;        // for GetEntry dedup
};

class EventParticleReaderArray   : public EventReader { /* was VecReader,  outputs vector<Lorentz> */ };
class EventParticleReaderRowJoin : public EventReader { /* was FlatReader, outputs vector<Lorentz> */ };
class EventNodeReaderArray       : public EventReader { /* new but parallel to VecReader */ };
class EventNodeReaderRowJoin     : public EventReader { /* new but parallel to FlatReader, no Lorentz */ };

// Feed-side readers populate slices of a Feed for entry number N.
class FeedReader {
public:
    virtual ~FeedReader() = default;
    virtual void readEntry(Long64_t N, Feed& out) = 0;
    virtual Long64_t entryCount() const = 0;
    virtual std::string treeName() const = 0;
};

class FeedParticleReader : public FeedReader { /* 4 scalar branches → one Lorentz */ };
class FeedNodeReader     : public FeedReader { /* N scalar/array branches → AuxValue map */ };
```

### Mapping from existing reader code

| Existing | New | Notes |
|---|---|---|
| `VecReader::next() + fill()` | `EventParticleReaderArray::seekToEvent + readForEvent` | Split current single fill into seek (`reader_.SetEntry(K)`) + read (the existing fill body). |
| `FlatReader::currentKey() + drain()` | `EventParticleReaderRowJoin::seekToEvent + readForEvent` | Seek advances cursor to first row with `event_index >= K`; read drains all rows with `event_index == K`. |
| (none) | `EventNodeReaderArray` | New: parallel arrays per entry, but no Lorentz construction — values go straight into `node[label][branch]`. Reuse `TTreeReaderArray<T>` and `AuxColumn` machinery. |
| (none) | `EventNodeReaderRowJoin` | New: row-indexed drain pattern from `FlatReader`, but no `kinBuf_` — only branch buffers feeding `node[label][branch]`. |
| (none) | `FeedParticleReader` | New: 4 `TTreeReaderValue<float>` over kinematic branches → one Lorentz via `makeLorentz`. Smaller than `VecReader` because no array iteration. |
| (none) | `FeedNodeReader` | New: per-branch `TTreeReaderValue<T>` or `TTreeReaderArray<T>` based on type/leaf shape. Output is `AuxValue` (scalar or array). |

### Multi-flavor `Buf` helper

To support all six numeric types + bool across both `Value<T>` (scalar) and
`Array<T>` (per-entry array), introduce a single variant-backed handle in
`Probe/Readers.hh`:

```cpp
struct BranchHandle {
    enum class Shape { Scalar, Array };
    Shape    shape;
    BranchType type;
    std::variant<
        std::unique_ptr<TTreeReaderValue<float>>,
        std::unique_ptr<TTreeReaderValue<double>>,
        std::unique_ptr<TTreeReaderValue<int32_t>>,
        std::unique_ptr<TTreeReaderValue<uint32_t>>,
        std::unique_ptr<TTreeReaderValue<int64_t>>,
        std::unique_ptr<TTreeReaderValue<uint64_t>>,
        std::unique_ptr<TTreeReaderValue<bool>>,
        std::unique_ptr<TTreeReaderArray<float>>,
        std::unique_ptr<TTreeReaderArray<double>>,
        std::unique_ptr<TTreeReaderArray<int32_t>>,
        std::unique_ptr<TTreeReaderArray<uint32_t>>,
        std::unique_ptr<TTreeReaderArray<int64_t>>,
        std::unique_ptr<TTreeReaderArray<uint64_t>>,
        std::unique_ptr<TTreeReaderArray<bool>>
    > h;

    AuxValue  readScalar() const;       // for FeedNodeReader
    AuxColumn readArray()  const;       // for EventNodeReader*
    void      appendInto(AuxColumn& col) const;  // for row-indexed drain
};
```

Removes the parallel scaffolding currently duplicated in
`FlatReader::AuxBuf` / `appendAux` / `makeAuxCol` and `VecReader::auxArrays_`.

### Synchronization across readers (Event side)

`EventStream::next()` dedupes `GetEntry` calls across readers sharing a tree:

```cpp
bool EventStream::next() {
    if (nextEvent_ > lastEvent_) return false;
    const Long64_t K = nextEvent_++;
    current_.clear();
    current_.index = K;

    std::unordered_set<const TTree*> tickled;
    for (auto& r : readers_) {
        // Array-flavor readers' seek does GetEntry; RowJoin-flavor readers'
        // seek advances cursor (no shared-tree concern). Dedup is best-effort.
        if (tickled.insert(r->treePtr()).second) r->seekToEvent(K);
        r->readForEvent(K, current_);
    }
    return true;
}
```

```cpp
// ALTERNATIVE: skip dedup. Decision: dedup, because NanoAOD-style configs put
// many labels on one "Events" tree; calling GetEntry once vs N times matters
// for I/O throughput. (ROOT does internal caching but the saved virtual
// dispatches and cache hits still pay off.)
```

### Partition iteration (existing mechanism)

The existing `eventPartitions_` (vector of `BranchControl::Partition{
firstEvent, lastEvent }`) and `entryBoundsByWorker_` already partition the
event-index space and pre-compute per-row bounds per worker. Both
generalize without modification:

- `EventParticleReaderArray::seekToEvent(part.firstEvent)` → `reader_.SetEntry(part.firstEvent)` (existing `VecReader` constructor's `SetEntriesRange` becomes redundant if seek does it; merge).
- `EventParticleReaderRowJoin::seekToEvent(part.firstEvent)` → consume the precomputed `entryBoundsByWorker_[t]` and scan to first row in range (existing `FlatReader` already does this through `entryBounds` ctor param).
- `EventNodeReader*` reuse the same seek logic.
- `FeedReader`s use `GetEntry(N)` directly with N ∈ [partition.firstEvent, partition.lastEvent].

---

## Stream classes

```cpp
class EventStream {
public:
    EventStream(const std::string&     filepath,
                const ProbeConfig&     cfg,
                Long64_t               firstEvent,
                Long64_t               lastEvent,
                std::size_t            nEventsHint,
                const std::vector<Bounds>& entryBounds = {});
    ~EventStream();

    bool next();
    const Event& current() const { return current_; }
    Event takeCurrent() { return std::move(current_); }
    std::size_t nEvents() const;

private:
    std::string filepath_;
    TFile*      file_ = nullptr;
    Event       current_;
    Long64_t    firstEvent_, lastEvent_, nextEvent_;
    std::vector<std::unique_ptr<EventReader>> readers_;
};

class FeedStream {
public:
    FeedStream(const std::string&     filepath,
               const ProbeConfig&     cfg,
               Long64_t               firstEntry,
               Long64_t               lastEntry);
    ~FeedStream();

    bool next();
    const Feed& current() const { return current_; }
    Feed takeCurrent() { return std::move(current_); }

private:
    std::string filepath_;
    TFile*      file_ = nullptr;
    Feed        current_;
    Long64_t    firstEntry_, lastEntry_, nextEntry_;
    std::vector<std::unique_ptr<FeedReader>> readers_;
};
```

The constructor signature for `EventStream` mirrors the existing one (filepath
+ partition bounds + entry-bounds hint). `FeedStream` is simpler — per-entry
iteration, no row-join machinery.

In Mixed mode both streams are constructed over the same partition;
`EventStream::next()` and `FeedStream::next()` are called in lockstep.

---

## Implementation phases

Each phase ends with `make test` green.

### Phase 1 · Type substrate

**Scope:** XS · **No deps**

In `utils/Probe/Types.hh`:

- Add `AuxValue`.
- Broaden `AuxColumn` variant to cover `float`, `int32_t`, `uint32_t`.
- Add `StreamMode`, `ActiveMode` enums.
- Add `EventParticleSpec`, `EventNodeSpec`, `FeedParticleSpec`,
  `FeedNodeSpec`, `ProbeConfig`.
- Add type alias `using CollectionSpec [[deprecated]] = EventParticleSpec;`
  (transition shim).
- Keep `Event` struct unchanged this phase (rename done in Phase 7).
- Keep `StreamType` enum unchanged this phase (replaced in Phase 7).

**Files:** `utils/Probe/Types.hh`.

---

### Phase 2 · Dual-syntax branch parser

**Scope:** S · **No deps**

In `utils/Probe/ConfigAid.hh::detail`, add:

```cpp
inline BranchSpec parseBranchEntry(const toml::node& node,
                                   bool allowBareString,
                                   const std::string& context);
inline std::vector<BranchSpec> parseBranchList(const toml::array& arr,
                                                bool allowBareString,
                                                const std::string& context);
```

Accepts the three syntaxes (inline-table, two-element array, bare string).
Rejects malformed entries with context-tagged error messages. Reuses
`RootUtil::detectBranchType(std::string)` for the type code.

Unit tests in `tests/test_probe_parallel.cc` for each form and for error
paths (mixed-form arrays, unknown type code, missing field).

**Files:** `utils/Probe/ConfigAid.hh`, `tests/test_probe_parallel.cc`.

---

### Phase 3 · `parseProbeConfig`

**Scope:** M · **Depends on:** Phase 1, Phase 2

In `utils/Probe/ConfigAid.hh`:

```cpp
inline ProbeConfig parseProbeConfig(const toml::table& cfg);
```

Implements:

1. Parse `[probe].stream` → `requestedMode`.
2. Parse `[probe.events]` declaration block → label lists.
3. Parse `[probe.feed]` declaration block → label lists.
4. For each declared label, parse the matching definition block into the
   appropriate spec type.
5. Per-section index monotonicity flags override the legacy `[probe.index]`
   element-wise arrays.
6. Apply validation rules 1–8 above.

Keep `parseCollectionsFromToml` as a thin shim that builds a `ProbeConfig`
with only `eventParticles` and translates index-spec flags from
`applyIndexSpecsFromToml`. Mark the shim `[[deprecated]]`.

**Files:** `utils/Probe/ConfigAid.hh`, `tests/test_probe_parallel.cc`,
`tests/fixtures/lambda_fixture.toml` (extend for both events/feed coverage).

---

### Phase 4 · `BranchHandle` and Event readers

**Scope:** M · **Depends on:** Phase 1

In `utils/Probe/Readers.hh`:

1. Add `BranchHandle` (variant of `TTreeReaderValue<T>` / `TTreeReaderArray<T>`)
   and its `readScalar` / `readArray` / `appendInto` helpers.
2. Refactor `VecReader` → `EventParticleReaderArray` (rename file-internal
   class; keep `VecReader` as `using VecReader = EventParticleReaderArray;`
   for one phase).
3. Refactor `FlatReader` → `EventParticleReaderRowJoin` (same pattern).
4. Add `EventNodeReaderArray` (new): per-entry array reader that writes into
   `Event.node[label][branch]` without Lorentz construction.
5. Add `EventNodeReaderRowJoin` (new): row-indexed drain that writes into
   `Event.node[label][branch]`.
6. Define the `EventReader` abstract interface and have all four classes
   implement it.

The two refactored classes preserve their existing public API for one phase
to allow the old `EventStream` to compile alongside the new one.

**Files:** `utils/Probe/Readers.hh`, `utils/Probe/Methods.hh`,
`tests/test_probe_parallel.cc`.

---

### Phase 5 · Feed readers

**Scope:** S · **Depends on:** Phase 1, Phase 4 (for `BranchHandle`)

Add `FeedParticleReader` and `FeedNodeReader` to `Probe/Readers.hh` /
`Probe/Methods.hh`. Reuse `BranchHandle` and `BranchControl::makeLorentz`.

`FeedNodeReader::readEntry(N, feed)` calls `GetEntry(N)` once, then writes
each branch's value into `feed.node[label][branch]` (as `AuxValue`).
Variable-length arrays land as the `vector<T>` alternative of `AuxValue`.

**Files:** `utils/Probe/Readers.hh`, `utils/Probe/Methods.hh`,
`tests/test_probe_parallel.cc`.

---

### Phase 6 · `EventStream` rewrite and `FeedStream`

**Scope:** M · **Depends on:** Phase 4, Phase 5

1. Rewrite `EventStream::next()` to be reader-polymorphic (the dedup-aware
   loop above). Remove the `isVec_` discriminator and the `nextFlat`/`nextVec`
   private methods.
2. The constructor accepts `ProbeConfig` and instantiates the right
   `EventReader` subclass per event-spec.
3. Add `FeedStream` (new class) with the simpler per-entry iteration loop.
4. Both classes keep file ownership (`TFile*` member + RAII close).

`EventStream`'s old public surface (`event()`, `takeEvent()`, `index()`,
`nEvents()`) is preserved.

**Files:** `utils/Probe/Methods.hh` (rewrite), `utils/Probe/Readers.hh`,
`tests/test_probe_parallel.cc`.

---

### Phase 7 · `ProbeParallel` three-method dispatch

**Scope:** M · **Depends on:** Phase 3, Phase 6

1. Rename `Event::particles` → `Event::particle`, `Event::aux` →
   `Event::node`. Update `operator[]`, `n()`, `column()` accordingly.
   Provide deprecated aliases (`auto& aux() const { return node; }`) for one
   phase.
2. Replace `configureProbe(..., vector<CollectionSpec>, ...)` with
   `configureProbe(..., ProbeConfig, ...)`.
3. Add `activeMode_` field; resolve it in `configureProbe` based on
   `config_.requestedMode` and which buckets are populated.
4. Replace `streamType()` with `activeMode()`. Keep `streamType()` as a
   deprecated wrapper that maps `Events` → `StreamType::Events`,
   `Feed`/`Mixed` → `StreamType::Vectors` (legacy semantics) — purely for
   external code that still reads the old getter.
5. Add `streamEvents`, `streamFeed`, `stream` template methods.
6. Generalize `runWorkerThread` / `runCollectorThread`:
   - Event-only path → identical to today, just constructs `EventStream` from
     `ProbeConfig`.
   - Feed-only path → analogous, using `FeedStream`.
   - Mixed path → constructs both streams per worker, advances in lockstep,
     pushes `QueuedFrame { workerIndex, eventIndex, Event, Feed }` per event.
7. Replace `QueuedEvent` with `QueuedFrame` (Event field, optional Feed). The
   queue type becomes `std::deque<QueuedFrame>`. In single-mode paths the
   Feed field is default-constructed (empty maps; near-zero cost).
8. The collector loop invokes `ce(frame.event, tid)` and/or `cf(frame.feed, tid)`
   based on `activeMode_`.

```cpp
// ALTERNATIVE for queue payload: separate Event and Feed queues, or a
// std::variant<QueuedEvent, QueuedFeed, QueuedFrame> payload. Decision:
// single QueuedFrame with optional fields. Reasons: (a) Mixed mode requires
// Event ↔ Feed pairing on the consumer side, which is easier if they travel
// together; (b) empty `Feed` is cheap.
```

**Files:** `utils/Probe/Types.hh` (Event field rename, QueuedFrame),
`utils/Probe/Parallel.hh`, `utils/Probe/Administration.hh`,
`utils/Probe/Directives.hh`, `tests/test_probe_parallel.cc`.

---

### Phase 8 · Validation tests

**Scope:** S · **Depends on:** Phase 7

One test per validation rule (1–8). Plus:

- `streamEvents` on feed-only config throws.
- `streamFeed` on events-only config throws.
- `stream(ce, cf)` on Events-only invokes only `ce`.
- `stream(ce, cf)` on Feed-only invokes only `cf`.
- `stream(ce, cf)` on Mixed invokes both per event, in order.
- Mixed-mode synchronization: `assert(e.index == f.index)` inside the
  callback.
- Tree-handle dedup: with two `EventParticleReaderArray`s on the same
  tree, `GetEntry` is called once per event (instrument a counting wrapper).

**Files:** `tests/test_probe_parallel.cc`, `tests/fixtures/*.toml`.

---

### Phase 9 · NanoAOD-shaped fixture

**Scope:** S · **Depends on:** Phase 7

Build a synthetic NanoAOD-shaped fixture (one `Events` tree with
`nMuon`/`Muon_pt[]`/`Muon_eta[]`/`Muon_phi[]`/`Muon_mass[]` arrays plus
scalar branches `genWeight`, `Pileup_nPU`, `MET_pt`). Write a Mixed-mode
test that runs end-to-end and checks per-event pairing.

This is the canonical use case and deserves a dedicated test fixture.

**Files:** `tests/fixtures/nanoaod_fixture.cc` (new),
`tests/test_probe_parallel.cc`.

---

### Phase 10 · Driver migration

**Scope:** S · **Depends on:** Phase 7

Migrate every `Probe` user to the new API:

1. `_Lambda_Reconstruction.cc` and any other Probe-using driver: replace
   `probe.run(cb)` with `probe.streamEvents(cb)` (current usage is event-only).
2. `configs/Lambda_Reconstruction.toml`: rewrite
   `[probe].event_particles = [...]` + `[probe.particle.<L>]` into
   `[probe.events].particles = [...]` + `[probe.events.particles.<L>]`.
   The translation is mechanical because the old layout maps onto the new
   `EventParticleSpec` directly.
3. `docs/DataFlow.md` and `docs/Architecture.md` § Probe: update prose
   references.

**Files:** `_Lambda_Reconstruction.cc`,
`configs/Lambda_Reconstruction.toml`, `docs/Architecture.md`,
`docs/DataFlow.md`.

---

### Phase 11 · Remove deprecated symbols

**Scope:** XS · **Depends on:** Phase 10

Delete:

- `StreamType` enum, `streamType()` deprecated wrapper, `determineStreamType()`.
- `CollectionSpec` deprecated alias.
- `Event::aux` deprecated accessor (renamed to `node` in Phase 7).
- `parseCollectionsFromToml` shim.
- `EventStream::nextFlat` / `nextVec` (replaced in Phase 6).
- `probe.run` (replaced by three explicit modes in Phase 7).
- `applyIndexSpecsFromToml` (per-section flags supersede it).

Pure deletion phase. No new logic.

**Files:** `utils/Probe/Types.hh`, `utils/Probe/Parallel.hh`,
`utils/Probe/Methods.hh`, `utils/Probe/ConfigAid.hh`,
`utils/Probe/Administration.hh`, `utils/Probe/Directives.hh`.

---

### Phase 12 · Documentation pass

**Scope:** S · **Depends on:** Phase 11

- `docs/Architecture.md` § Probe — rewrite for Event/Feed and the three
  call methods.
- `docs/DataFlow.md` § `[probe]` — replace the old single-stream reference
  with the bucket-split schema.
- `docs/MAP.md` — list `Probe/EventStream.hh` (if split out),
  `Probe/Readers.hh` additions.
- `utils/Probe/Parallel.hh` class doc — keep one-line summary pointing to
  this document.

**Files:** as listed.

---

## Dependency graph

```
Phase 1 (Types)
   ├─► Phase 2 (Branch syntax)
   │       └─► Phase 3 (parseProbeConfig)
   │               └─► Phase 7 (ProbeParallel surface)
   ├─► Phase 4 (Event readers + BranchHandle)
   │       └─► Phase 5 (Feed readers)
   │               └─► Phase 6 (Streams) ───► Phase 7
   └─►            (Phase 4 also feeds Phase 6 directly)

Phase 7
   ├─► Phase 8 (Validation tests)
   ├─► Phase 9 (NanoAOD fixture)
   └─► Phase 10 (Driver migration)
           └─► Phase 11 (Deletion)
                   └─► Phase 12 (Docs)
```

Phases 4 and 5 can be merged into a single PR; Phase 5 depends on Phase 4
only for the `BranchHandle` helper. Phases 8 and 9 can run in parallel after
Phase 7.

---

## Open decisions (deferred — flag and proceed)

1. **Mixed-mode callback ordering.** Spec'd as `ce` then `cf` per event.
   Alternative: `cf` first (feed semantically gates the event analysis in
   many real cases). Decision: ce-first because Event is the larger payload
   and feed-driven gating can be done by capturing state in `cf`'s closure.

2. **Per-tree `GetEntry` dedup mechanism.** Centralized in
   `EventStream::next` via `treePtr()` set. Alternative: each reader
   self-tracks. Decision: centralize.

3. **Multi-tree configs.** Different `tree =` values across labels.
   Decision: support from day one; synthetic Phase 8 test covers it.

4. **Feed reader handling of variable-length array branches.** Spec'd: a
   Feed-node branch with array-typed leaf yields an `AuxValue` holding a
   `vector<T>`. Decision: confirmed.

5. **`CallbackMode::WorkerThread` in Mixed mode.** Worker invokes `ce` then
   `cf` per event on its own thread. No queue.

6. **`CallbackMode::CollectorThread` payload in Mixed mode.** Single
   `QueuedFrame { Event, Feed }` per event. Single payload rather than two
   separate queues; the pair travels together so the collector receives them
   atomically.

7. **`Event::node` flat vs nested.** Kept nested
   `map<label, map<branch, AuxColumn>>` (matches existing `aux` shape).
   Alternative: flat `map<label, AuxColumn>` with one column per label.
   Decision: nested, because Phase 7 then has no schema change for the
   `aux→node` rename, only field-name change.

8. **`AuxColumn` breadth.** Broaden to include float/int32/uint32 alongside
   the existing four alternatives. Decision: yes (Phase 1). The narrow
   variant would force every node-reader to up-cast (float→double, int32→int64)
   on every read, which both wastes memory and loses faithfulness for users
   who want native types.

9. **`EventParticleSpec.auxBranches` survives.** Per-particle aux is
   preserved as a `vector<BranchSpec>` field on the particle spec. The
   reader populates `event.node[particle_label][branch] = AuxColumn`. The
   user can choose to use shared labels (`particle["muon"]` + `node["muon"]`)
   or distinct (`node["muon_iso"]`).

10. **`[probe.index]` legacy block.** Element-wise bool arrays from the
    existing schema. Kept parseable as a transitional fallback through
    Phase 10; per-section flags take precedence when both are present.
    Removed in Phase 11.

---

## Out of scope

- Changes to `ParallelIMT.hh` and `ProbeIMT` — independent path; unaffected.
- New ROOT branch type codes beyond what `RootUtil::DataType` already
  supports. (`Short_t`, `Byte_t` etc. can be added later if real input data
  needs them.)
- Performance optimization. Wait for the timer-instrumentation phases from
  `docs/Plan.md` (Phases 2 / 3) to point at hot spots.

---

## Acceptance criteria

1. All current `test_probe_parallel`, `test_reconstructCandidates`, and
   `test_rootAnalysis_smoke` cases pass after Phase 10.
2. The synthetic NanoAOD fixture (Phase 9) runs end-to-end in Mixed mode
   with verified per-event Event ↔ Feed pairing.
3. `grep -r "StreamType\|nextFlat\|nextVec\|parseCollectionsFromToml\|aux\b" utils/Probe/`
   returns nothing in headers after Phase 11.
4. `docs/Architecture.md` and `docs/DataFlow.md` describe only the new
   model.
5. Public API surface on `ProbeParallel`: `streamEvents` / `streamFeed` /
   `stream` only; no `run`.
