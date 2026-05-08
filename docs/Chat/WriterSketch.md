# Writer Overhaul Sketch

## Purpose

`Record::Writer` should become the only actor that owns, mutates, writes, and
closes ROOT output objects.

Current code splits responsibility:

- Lambda declares `Record::RootArray<Lambda::HistogramSet>` outside `Writer`.
- Lambda mutates histograms, candidate counts, and optional trees directly.
- `Record::Writer` owns the `TFile`, metadata, shutdown/checkpoint lifecycle,
  and a mutex, but it does not own the recorded objects.

The target design reverses that. Modules may declare desired records into
`Writer`, and may submit fill requests to `Writer`, but they should not own
`TFile`, `TDirectory`, `TH1`, `TH2`, `TGraph`, `TProfile`, `TTree`, or `TBranch`
objects.

The core invariant:

```cpp
// Outside Record::Writer, no code mutates ROOT output objects.
```

The public fill methods are producer-facing methods. They convert module data
into request payloads and push those payloads into Writer-owned queues. A
Writer-owned scribe thread drains queues and performs the actual ROOT calls.

## Ownership Model

`Record::Writer` owns:

- output file: `TFile*`;
- directories: `TDirectory*`;
- particle-derived grouped objects;
- independent histograms, graphs, profiles, and trees;
- branch buffers used as stable ROOT branch addresses;
- fill queues;
- checkpoint/final/fatal write execution;
- metadata and output paths.

Modules own:

- physics parameters;
- reconstruction logic;
- basis enums used as record identifiers;
- high-level declaration recipes;
- event-level fill calls.

Modules should not own:

- ROOT output object containers;
- branch value storage;
- per-object candidate counters;
- tree branch addresses;
- output-file close/write logic.

## Shared Data Types

`Probe::BranchType` and the proposed Writer `DataType` represent the same
concept. They should be unified into a small shared ROOT utility header, for
example `utils/Utility/RootTypes.hh` or `utils/Utility/Rootility.hh`.

Sketch:

```cpp
namespace RootUtil {

enum class DataType {
    Float,
    Double,
    Int32,
    UInt32,
    Int64,
    UInt64,
    Bool,
    Char,
    String,
    Other
};

using Value = std::variant<
    float,
    double,
    std::int32_t,
    std::uint32_t,
    std::int64_t,
    std::uint64_t,
    bool,
    char,
    std::string
>;

std::string leafListSuffix(DataType type);
std::string typeName(DataType type);
DataType detectBranchType(TBranch* branch);

} // namespace RootUtil
```

`Record` and `Probe` can alias this if the shorter local names are convenient:

```cpp
namespace Record {
    using DataType = RootUtil::DataType;
    using Value    = RootUtil::Value;
}

namespace Probe {
    using BranchType = RootUtil::DataType;
}
```

## Record Identity

The public API should keep typed enum basis identifiers, such as
`Lambda::HistogramSet`. Internally, Writer converts each basis value into a
generic key.

```cpp
namespace Record {

struct NoBasis {};

struct RecordKey {
    std::type_index domain{typeid(void)};
    std::int64_t value = 0;
};

struct RecordKeyHash {
    std::size_t operator()(const RecordKey& key) const;
};

bool operator==(const RecordKey& a, const RecordKey& b);

template <typename Basis>
RecordKey keyOf(Basis basis) {
    static_assert(std::is_enum_v<Basis>, "Record basis must be an enum");
    using Raw = std::underlying_type_t<Basis>;
    return {std::type_index(typeid(Basis)), static_cast<std::int64_t>(static_cast<Raw>(basis))};
}

} // namespace Record
```

This avoids stringly typed record lookup while allowing a non-templated
`Record::Writer` to store records from multiple modules.

## Branch Buffers

ROOT branches need stable addresses to typed C++ storage. A generic Writer
needs mixed branch types without exposing those buffers to modules.

```cpp
namespace Record {

struct BranchBufferBase {
    virtual ~BranchBufferBase() = default;
    virtual void* address() = 0;
    virtual void set(const Value& value) = 0;
    virtual DataType type() const = 0;
};

template <typename T>
struct BranchBuffer final : BranchBufferBase {
    T value{};

    void* address() override { return &value; }

    void set(const Value& v) override {
        value = std::get<T>(v);
    }

    DataType type() const override {
        return dataTypeOf<T>();
    }
};

struct BranchRecord {
    TBranch* branch{};
    std::string name;
    DataType type = DataType::Other;
    std::unique_ptr<BranchBufferBase> buffer;
};

} // namespace Record
```

For current Lambda candidate trees, all candidate branches are `Double_t`, so
this is not strictly necessary yet. It becomes necessary once Writer also owns
raw data trees with mixed `event_index/I` and kinematic `/D` branches, or any
future explicit tree with mixed branch types.

## Particle-Derived Objects

Particle objects are filled from `Physics::Lorentz` values by extracting
configured particle properties.

They are grouped under one basis key because one logical event fill usually
resets a candidate counter, fills several particle-derived objects, and then
fills a count histogram.

```cpp
namespace Record {

struct ParticleTH1 {
    TH1* hist{};
    Physics::ParticleProperty property{};
};

struct ParticleTH2 {
    TH2* hist{};
    Physics::ParticleProperty propertyX{};
    Physics::ParticleProperty propertyY{};
};

struct ParticleGraph {
    TGraph* graph{};
    Physics::ParticleProperty propertyX{};
    Physics::ParticleProperty propertyY{};
    std::int32_t nextPoint = 0;
};

struct ParticleProfile {
    TProfile* profile{};
    Physics::ParticleProperty propertyX{};
    Physics::ParticleProperty propertyY{};
};

struct ParticleTree {
    TTree* tree{};
    std::vector<Physics::ParticleProperty> properties;
    std::vector<BranchRecord> branches;
};

struct ParticleObjects {
    RecordKey basis{};
    std::string name;
    TDirectory* dir{};
    TH1* count{};
    std::int32_t candidateCount = 0;

    std::vector<ParticleTH1> hists1D;
    std::vector<ParticleTH2> hists2D;
    std::vector<ParticleGraph> graphs;
    std::vector<ParticleProfile> profiles;
    ParticleTree tree;
};

} // namespace Record
```

Particle object fill behavior:

- `ParticleTH1`: fill one value from one particle property.
- `ParticleTH2`: fill `(propertyX, propertyY)` from the same particle.
- `ParticleGraph`: append one point per particle.
- `ParticleProfile`: fill `(propertyX, propertyY)` from the same particle.
- `ParticleTree`: set branch buffers from the configured properties, then call
  `TTree::Fill()`.
- `count`: fill once per event group with the final candidate count.

## Independent Objects

Independent records are not tied to `Physics::Lorentz`. They are filled with
explicit values.

```cpp
namespace Record {

struct Hist1DRecord {
    TH1* hist{};
    DataType type = DataType::Double;
};

struct Hist2DRecord {
    TH2* hist{};
    DataType typeX = DataType::Double;
    DataType typeY = DataType::Double;
};

struct GraphRecord {
    TGraph* graph{};
    DataType typeX = DataType::Double;
    DataType typeY = DataType::Double;
    std::int32_t nextPoint = 0;
};

struct ProfileRecord {
    TProfile* profile{};
    DataType typeX = DataType::Double;
    DataType typeY = DataType::Double;
};

struct TreeRecord {
    TTree* tree{};
    std::unordered_map<RecordKey, BranchRecord, RecordKeyHash> branches;
    std::vector<RecordKey> branchOrder;
};

} // namespace Record
```

Writer therefore needs registries for both particle groups and independent
objects:

```cpp
std::unordered_map<RecordKey, ParticleObjects, RecordKeyHash> particleObjects_;

std::unordered_map<RecordKey, Hist1DRecord,  RecordKeyHash> hists1D_;
std::unordered_map<RecordKey, Hist2DRecord,  RecordKeyHash> hists2D_;
std::unordered_map<RecordKey, GraphRecord,   RecordKeyHash> graphs_;
std::unordered_map<RecordKey, ProfileRecord, RecordKeyHash> profiles_;
std::unordered_map<RecordKey, TreeRecord,    RecordKeyHash> trees_;
```

`ParticleObjects` is not a replacement for these independent registries. It is
only the registry for particle-derived grouped output.

## Declaration API

Declaration methods are called during setup, before the scribe thread starts.
They create ROOT objects inside the output file and store them in Writer-owned
registries.

Particle declarations:

```cpp
class Writer {
  public:
    template <typename Basis>
    void declareParticleGroup(Basis basis,
                              std::string directoryName,
                              std::string displayName);

    template <typename Basis>
    void declareParticleCount(Basis basis,
                              std::string histName,
                              std::string title,
                              int bins,
                              double low,
                              double high);

    template <typename Basis>
    void declareParticleHist1D(Basis basis,
                               Physics::ParticleProperty property,
                               std::string histName,
                               std::string title,
                               int bins,
                               double low,
                               double high);

    template <typename Basis>
    void declareParticleHist2D(Basis basis,
                               Physics::ParticleProperty propertyX,
                               Physics::ParticleProperty propertyY,
                               std::string histName,
                               std::string title,
                               int binsX,
                               double lowX,
                               double highX,
                               int binsY,
                               double lowY,
                               double highY);

    template <typename Basis>
    void declareParticleGraph(Basis basis,
                              Physics::ParticleProperty propertyX,
                              Physics::ParticleProperty propertyY,
                              std::string graphName,
                              std::string title);

    template <typename Basis>
    void declareParticleProfile(Basis basis,
                                Physics::ParticleProperty propertyX,
                                Physics::ParticleProperty propertyY,
                                std::string profileName,
                                std::string title,
                                int binsX,
                                double lowX,
                                double highX);

    template <typename Basis>
    void declareParticleTree(Basis basis,
                             std::string treeName,
                             std::string title,
                             std::vector<Physics::ParticleProperty> properties);
};
```

Independent declarations:

```cpp
class Writer {
  public:
    template <typename Basis>
    void declareHist1D(Basis basis,
                       std::string histName,
                       std::string title,
                       int bins,
                       double low,
                       double high,
                       DataType type = DataType::Double);

    template <typename Basis>
    void declareHist2D(Basis basis,
                       std::string histName,
                       std::string title,
                       int binsX,
                       double lowX,
                       double highX,
                       int binsY,
                       double lowY,
                       double highY,
                       DataType typeX = DataType::Double,
                       DataType typeY = DataType::Double);

    template <typename Basis>
    void declareGraph(Basis basis,
                      std::string graphName,
                      std::string title,
                      DataType typeX = DataType::Double,
                      DataType typeY = DataType::Double);

    template <typename Basis>
    void declareProfile(Basis basis,
                        std::string profileName,
                        std::string title,
                        int binsX,
                        double lowX,
                        double highX,
                        DataType typeX = DataType::Double,
                        DataType typeY = DataType::Double);

    template <typename TreeBasis, typename BranchBasis>
    void declareTree(TreeBasis treeBasis,
                     std::string treeName,
                     std::string title,
                     std::vector<std::tuple<BranchBasis, std::string, DataType>> branches);
};
```

Declaration rules:

- duplicate basis keys throw;
- missing particle group before declaring particle children throws;
- declarations after `Writer::start()` throw;
- all ROOT object creation happens on the setup thread before queued filling;
- if ROOT object creation must be moved onto the scribe later, add a setup
  request phase, but do not mix setup requests with fill requests in v1.

## Fill API

The fill API converts input into queue payloads. It should not mutate ROOT
objects directly.

Particle event fill:

```cpp
template <typename Basis>
struct ParticleFill {
    Basis basis;
    std::span<const Physics::Lorentz> particles;
};

class Writer {
  public:
    template <typename Basis>
    void fillParticleEvent(std::initializer_list<ParticleFill<Basis>> fills);
};
```

Lambda usage:

```cpp
ctx.writer.fillParticleEvent<Lambda::HistogramSet>({
    {Lambda::HistogramSet::Unvalidated, candidates.unvalidated},
    {Lambda::HistogramSet::Validated,   candidates.validated},
    {Lambda::HistogramSet::Selected,    candidates.selected}
});
```

This one call represents one logical event. It must enqueue a single particle
request that preserves:

- reset counts for all included particle groups;
- fill particles for each group;
- fill count histograms after particles are processed.

Independent fills:

```cpp
class Writer {
  public:
    template <typename Basis>
    void fillHist1D(Basis basis, Value value);

    template <typename Basis>
    void fillHist2D(Basis basis, Value x, Value y);

    template <typename Basis>
    void fillGraph(Basis basis, Value x, Value y);

    template <typename Basis>
    void fillProfile(Basis basis, Value x, Value y);

    template <typename TreeBasis, typename BranchBasis>
    void fillTree(TreeBasis tree,
                  std::initializer_list<std::pair<BranchBasis, Value>> values);
};
```

The tree fill API may later gain an ordered fast path:

```cpp
template <typename TreeBasis>
void fillTreeOrdered(TreeBasis tree, std::span<const Value> values);
```

The initializer-list form is safer for early use because it validates branch
identity. The ordered form is faster but requires strict branch order discipline.

## Request Types

Particle requests are separate from independent object requests.

```cpp
enum class ParticleRequestKind {
    FillEvent
};

struct ParticleGroupFillRequest {
    RecordKey basis{};
    std::vector<Physics::Lorentz> particles;
};

struct ParticleRequest {
    ParticleRequestKind kind = ParticleRequestKind::FillEvent;
    std::vector<ParticleGroupFillRequest> groups;
};
```

Independent requests:

```cpp
struct Hist1DRequest {
    RecordKey basis{};
    Value value;
};

struct Hist2DRequest {
    RecordKey basis{};
    Value x;
    Value y;
};

struct GraphRequest {
    RecordKey basis{};
    Value x;
    Value y;
};

struct ProfileRequest {
    RecordKey basis{};
    Value x;
    Value y;
};

struct TreeRowRequest {
    RecordKey tree{};
    std::vector<std::pair<RecordKey, Value>> values;
};

struct CheckpointRequest {
    std::size_t eventIndex = 0;
    std::shared_ptr<BarrierState> barrier;
};

struct FinishRequest {
    std::size_t eventCount = 0;
    std::shared_ptr<BarrierState> barrier;
};

struct FatalWriteRequest {
    std::size_t eventCount = 0;
    std::shared_ptr<BarrierState> barrier;
};
```

`BarrierState` is used by producer threads that must wait until the scribe has
completed a checkpoint, finish, or fatal write request.

```cpp
struct BarrierState {
    std::mutex mutex;
    std::condition_variable cv;
    bool done = false;
    std::exception_ptr exception;
};
```

## Queue Model

Use separate payload queues plus a grand queue that preserves global request
order.

```cpp
enum class QueueLane {
    Particle,
    Hist1D,
    Hist2D,
    Graph,
    Profile,
    Tree,
    Checkpoint,
    Finish,
    FatalWrite,
    Stop
};

struct QueueTicket {
    QueueLane lane = QueueLane::Stop;
};
```

Private Writer queues:

```cpp
std::deque<QueueTicket> grandQueue_;

std::deque<ParticleRequest> particleQueue_;
std::deque<Hist1DRequest> hist1DQueue_;
std::deque<Hist2DRequest> hist2DQueue_;
std::deque<GraphRequest> graphQueue_;
std::deque<ProfileRequest> profileQueue_;
std::deque<TreeRowRequest> treeQueue_;
std::deque<CheckpointRequest> checkpointQueue_;
std::deque<FinishRequest> finishQueue_;
std::deque<FatalWriteRequest> fatalQueue_;
```

Queue synchronization:

```cpp
std::mutex queueMutex_;
std::condition_variable queueNotEmpty_;
std::condition_variable queueNotFull_;
std::size_t queueCapacity_ = 1024;

std::thread scribe_;
std::atomic<bool> started_{false};
std::atomic<bool> accepting_{false};
std::atomic<bool> stopRequested_{false};
std::exception_ptr scribeException_;
```

The capacity should apply to `grandQueue_`, not to each payload queue
independently. That makes total backlog predictable.

Push invariant:

```cpp
// Under queueMutex_:
payloadQueue.push_back(payload);
grandQueue_.push_back({lane});
queueNotEmpty_.notify_one();
```

Pop invariant:

```cpp
// Under queueMutex_:
QueueTicket ticket = grandQueue_.front();
grandQueue_.pop_front();
payload = matchingPayloadQueue.front();
matchingPayloadQueue.pop_front();
queueNotFull_.notify_one();
```

The grand queue and payload queues must always be mutated under the same mutex.
Never push a ticket without its payload. Never pop a payload without its ticket.

## Scribe Thread

`Writer::start()` starts the scribe after all declarations are complete.

```cpp
class Writer {
  public:
    void start();
    void finish(std::size_t eventCount);
    void checkpoint(std::size_t eventIndex);
    void fatalWrite(std::size_t eventCount);

  private:
    void scribeLoop();
    void applyParticleRequest(const ParticleRequest& request);
    void applyHist1DRequest(const Hist1DRequest& request);
    void applyHist2DRequest(const Hist2DRequest& request);
    void applyGraphRequest(const GraphRequest& request);
    void applyProfileRequest(const ProfileRequest& request);
    void applyTreeRowRequest(const TreeRowRequest& request);
    void applyCheckpointRequest(const CheckpointRequest& request);
    void applyFinishRequest(const FinishRequest& request);
    void applyFatalWriteRequest(const FatalWriteRequest& request);
};
```

Scribe loop sketch:

```cpp
void Writer::scribeLoop() {
    try {
        while (true) {
            QueueTicket ticket = popTicket();
            switch (ticket.lane) {
                case QueueLane::Particle:   applyParticleRequest(popParticleRequest()); break;
                case QueueLane::Hist1D:     applyHist1DRequest(popHist1DRequest()); break;
                case QueueLane::Hist2D:     applyHist2DRequest(popHist2DRequest()); break;
                case QueueLane::Graph:      applyGraphRequest(popGraphRequest()); break;
                case QueueLane::Profile:    applyProfileRequest(popProfileRequest()); break;
                case QueueLane::Tree:       applyTreeRowRequest(popTreeRowRequest()); break;
                case QueueLane::Checkpoint: applyCheckpointRequest(popCheckpointRequest()); break;
                case QueueLane::Finish:     applyFinishRequest(popFinishRequest()); return;
                case QueueLane::FatalWrite: applyFatalWriteRequest(popFatalWriteRequest()); return;
                case QueueLane::Stop:       return;
            }
        }
    } catch (...) {
        scribeException_ = std::current_exception();
        accepting_.store(false);
        queueNotFull_.notify_all();
        queueNotEmpty_.notify_all();
    }
}
```

`finish()` enqueues a `FinishRequest`, waits for its barrier, then joins the
scribe thread. After `finish()`, no fill API may accept new requests.

`checkpoint()` enqueues a `CheckpointRequest` and waits for its barrier. Since
the checkpoint request is ordered through `grandQueue_`, all earlier fill
requests are applied before the checkpoint file is written.

`fatalWrite()` must avoid waiting for room in a saturated normal queue. It
should set `accepting_ = false`, wake producers, and either:

1. push a fatal request through a separate emergency path protected by
   `queueMutex_`; or
2. have the scribe check `fatalRequested_` between normal requests and execute
   fatal write ahead of remaining normal backlog.

The first version is simpler if implemented carefully: fatal request insertion
does not obey normal capacity limits.

## Applying Requests

Particle request application:

```cpp
void Writer::applyParticleRequest(const ParticleRequest& request) {
    for (const auto& group : request.groups) {
        ParticleObjects& object = requireParticleObjects(group.basis);
        object.candidateCount = 0;

        for (const Physics::Lorentz& particle : group.particles) {
            ++object.candidateCount;

            for (ParticleTH1& h : object.hists1D)
                h.hist->Fill(Physics::valueOf(particle, h.property));

            for (ParticleTH2& h : object.hists2D)
                h.hist->Fill(Physics::valueOf(particle, h.propertyX),
                             Physics::valueOf(particle, h.propertyY));

            for (ParticleGraph& g : object.graphs)
                g.graph->SetPoint(g.nextPoint++,
                                  Physics::valueOf(particle, g.propertyX),
                                  Physics::valueOf(particle, g.propertyY));

            for (ParticleProfile& p : object.profiles)
                p.profile->Fill(Physics::valueOf(particle, p.propertyX),
                                Physics::valueOf(particle, p.propertyY));

            fillParticleTree(object.tree, particle);
        }

        if (object.count != nullptr)
            object.count->Fill(object.candidateCount);
    }
}
```

Independent request application:

- `Hist1DRequest`: convert `Value` to double-compatible scalar and call
  `TH1::Fill`.
- `Hist2DRequest`: convert two values and call `TH2::Fill`.
- `GraphRequest`: append `SetPoint(nextPoint++, x, y)`.
- `ProfileRequest`: call `TProfile::Fill(x, y)`.
- `TreeRowRequest`: set branch buffers by branch key, then call `TTree::Fill`.

All conversion errors should throw with the record key and expected type.
Scribe exceptions are stored and propagated to `finish()`, `checkpoint()`, and
future producer calls.

## Write, Checkpoint, Finish

`Writer` should have one internal write path over its registries:

```cpp
void writeAllToCurrentFile(std::size_t nEvents, bool checkpoint);
void writeParticleObjects(ParticleObjects& object, std::size_t nEvents, bool checkpoint);
void writeIndependentObjects(std::size_t nEvents, bool checkpoint);
```

Write rules:

- Histograms are cloned before scaling, as current `Record::scaleAndWrite`
  already does.
- `TH1`-like objects use `histScale / nEvents` when `nEvents > 0`.
- Width scaling remains only for 1D histograms where desired.
- Trees are skipped in checkpoint mode unless explicitly enabled later.
- Final write writes all objects plus `About/` metadata.
- `TFile::Write`, `TFile::Close`, and deletion happen only in the scribe.

Lifecycle:

```cpp
writer.open(...);
Lambda::declareObjects(writer, parameters);
writer.start();

// event loop calls writer.fill...

writer.meta().dataset.parent_files = ...;
writer.finish(logger.watch().nEvents);
```

Metadata mutation should happen before `finish()`. Once `FinishRequest` reaches
the scribe, metadata is written and the output file is closed.

## Logger And Fatal Stall

Normal checkpointing and logging should be explicit:

```cpp
writer.checkpoint(eventIndex);
logger.checkpoint(...);
```

For fatal stalls, the logger can own orchestration:

1. logger detects fatal stall;
2. logger writes fatal log;
3. logger calls `writer.fatalWrite(snapshot.nEvents)`;
4. logger waits for Writer's fatal barrier with a timeout;
5. logger writes final terminal/log output and exits.

This removes the current `Writer::installFatalStallHandler(sets)` pattern where
Writer captures an external `RootArray&`.

Writer should expose a fatal result primitive, not logger internals:

```cpp
bool fatalWrite(std::size_t eventCount, std::chrono::milliseconds timeout);
```

or:

```cpp
std::shared_ptr<BarrierState> requestFatalWrite(std::size_t eventCount);
```

The logger decides how long to wait and how to exit.

## Threading Rules

Producer threads:

- may call fill APIs concurrently;
- only allocate/copy request payloads and push queues;
- never touch ROOT output objects;
- block on `queueNotFull_` when the grand queue reaches capacity;
- wake and throw if Writer stops accepting requests.

Scribe thread:

- is the only normal thread that mutates ROOT output objects;
- processes requests in grand-queue order;
- writes checkpoints and final files;
- stores exceptions for propagation.

Setup thread:

- calls declaration APIs before `start()`;
- may create ROOT output objects directly because no scribe is running yet;
- may mutate metadata before `finish()`.

No `recordingScope()` should be required in user analysis code after this
overhaul.

## Lambda Shape After Writer Overhaul

Current:

```cpp
Lambda::RootArray histogramSets;
Lambda::configure(physParams, histogramSets, writer, configPath);
Lambda::AnalysisContext ctx{histogramSets, physParams, watch, logger, writer};
```

Target:

```cpp
Lambda::Parameters physParams;
Lambda::configure(physParams, writer, configPath);
writer.start();

Lambda::AnalysisContext ctx{physParams, watch, logger, writer};
```

`Lambda::configure` should load parameters and declare records into Writer.

`Lambda::fillCandidates` should become a Writer adapter:

```cpp
inline void fillCandidates(Record::Writer& writer, const Candidates& candidates) {
    writer.fillParticleEvent<HistogramSet>({
        {HistogramSet::Unvalidated, candidates.unvalidated},
        {HistogramSet::Validated,   candidates.validated},
        {HistogramSet::Selected,    candidates.selected}
    });
}
```

`Lambda::rootAnalysis` and `Lambda::pythiaAnalysis` should reconstruct
candidates, then submit a single particle event request. They should not hold a
Writer lock and should not see `RootArray`.

`Lambda::dataGenerator` should eventually submit tree rows into Writer instead
of filling `DataObjects` directly under `treeMutex`.

## Migration Route

Recommended implementation order:

1. Add shared `RootUtil::DataType` / `RootUtil::Value` and bridge Probe's
   existing `BranchType` to it.
2. Add Writer-owned registries and declaration methods while keeping old
   `RootArray` code temporarily available.
3. Add queue infrastructure, scribe thread, `start()`, `finish()`,
   `checkpoint()`, and fatal write primitives.
4. Move Lambda reconstruction histograms from external `RootArray` to
   Writer-owned particle declarations and `fillParticleEvent`.
5. Remove `recordingScope()` from Lambda analysis paths.
6. Move Lambda data-generation trees into Writer-owned tree declarations and
   queued tree-row fills.
7. Delete or demote old `Record::RootObjects`, `RootArray`, free `Record::fill`,
   and `Record::writeAll` once all call sites have moved.

During migration, temporary compatibility wrappers are acceptable if they keep
tests passing, but new code should use Writer-owned records only.

## Problems This Solves

- Direct multi-threaded `TH1::Fill` and `TTree::Fill` calls disappear from
  analysis callbacks.
- Candidate count reset/fill/count becomes one ordered event request instead of
  caller-managed shared state.
- Checkpoints become queue barriers and no longer race with in-flight fills.
- Fatal write no longer captures external object containers by reference.
- Writer's name matches its responsibility: it owns what it writes.
- Modules describe output intent rather than handling ROOT object lifetime.

## Risks And Decisions

- The scribe thread serializes all output mutation. If histogram filling is the
  dominant cost, this intentionally trades parallel fill calls for deterministic
  single-threaded ROOT mutation.
- Queue payloads copy particles or extracted values. For Lambda candidate
  counts this should be acceptable, but very large per-event payloads may need
  move-based APIs later.
- Declaration currently creates ROOT objects before `start()`. If ROOT object
  creation itself must be moved to a single ROOT thread, declaration requests can
  be added later.
- `TGraph::SetPoint` needs an owned `nextPoint` counter per graph.
- `TTree` branch buffers must remain stable for the lifetime of the tree.
- Fatal write cannot guarantee recovery if the scribe is already stuck inside a
  ROOT call; it can only avoid adding queue-level deadlock.

## Changes Required In Other Utils And Modules

### `utils/Utility`

- Add a shared ROOT type utility header for `DataType`, `Value`, ROOT leaf-list
  suffixes, type names, value conversion, and branch type detection.
- Keep this utility independent of `Record` and `Probe` so both can include it.

### `utils/Probe`

- Replace or alias `Probe::BranchType` with the shared `RootUtil::DataType`.
- Move duplicated branch type string/detection logic out of
  `Probe::BranchControl`.
- Keep Probe input reading separate from Writer output writing. Probe should not
  know about Writer queues.

### `utils/Record`

- Split current `Record::Types.hh` into clearer owned-record and request
  headers if the file becomes too large.
- Move free fill/write helpers behind Writer methods.
- Replace `Writer::recordingScope()` with internal queue synchronization.
- Replace templated `shutdown(RootArrayT&)`, `checkpoint(RootArrayT&)`, and
  `installFatalStallHandler(RootArrayT&)` with non-template Writer-owned
  lifecycle methods.
- Keep `Record::Meta`, `Record::Paths`, and `Record::HistConfig` mostly as-is.
- Update `Record.hh` umbrella comments and includes after the old `RootArray`
  path is removed.

### `utils/Monitor`

- `Monitor::AsyncLogger::initialise(const Record::Writer&)` can keep using
  `writer.paths()` and `writer.histConfig()`.
- Fatal-stall handling should move from "Writer installs a lambda on Logger" to
  "Logger owns fatal orchestration and calls `writer.fatalWrite(...)`".
- Checkpoint logging should be explicit and not hidden inside
  `Writer::checkpoint()` unless a narrow helper is intentionally kept.
- Monitor should not need access to ROOT objects.

### `utils/Config`

- `Config::configureWriter` can still populate paths, histogram config, metadata,
  and call `writer.open(...)`.
- Config does not need to know the record registry internals.
- Module-specific config loading should declare objects through module
  declaration functions after `configureWriter`.

### `modules/Lambda`

- Remove `Lambda::RootArray` and `Lambda::RootObjects` from the analysis path.
- Change `Lambda::declareObjects` to declare into `Record::Writer`.
- Change `Lambda::AnalysisContext` to drop `RootArray& histograms`.
- Change `Lambda::fillCandidates` to call `writer.fillParticleEvent`.
- Change `Lambda::rootAnalysis` and `Lambda::pythiaAnalysis` to submit Writer
  requests without `recordingScope()`.
- Move `Lambda::DataObjects` / `treeMutex` data-generation output into
  Writer-owned explicit trees or particle/raw tree declarations.

### Drivers

- Reconstruction, parallel simulation, test, and data drivers should call
  `writer.start()` after declarations and before event loops.
- Drivers should call `writer.finish(eventCount)` instead of
  `writer.shutdown(histogramSets)`.
- Drivers should update metadata before `finish()`.
- Drivers should no longer construct or pass `Lambda::RootArray`.

### Tests

- Existing smoke tests should assert output histograms still contain the same
  values after the Writer-owned path.
- Add tests that producer threads call fill APIs concurrently and callback
  counts are correct.
- Add a test that checkpoint waits for earlier queued fills.
- Add a test that scribe exceptions propagate to `finish()`.
- Add a test for mixed tree branch types to validate `BranchBufferBase`.
- Add a test that duplicate declarations throw.
