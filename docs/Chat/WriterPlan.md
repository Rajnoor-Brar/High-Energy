# Writer Overhaul Implementation Plan

## Goal

Implement the architecture in `docs/Chat/WriterSketch.md`: `Record::Writer`
becomes the sole owner and mutator of ROOT output objects. Modules declare output
objects into `Writer` and submit fill requests; a Writer-owned scribe thread is
the only normal thread that calls ROOT mutation/write APIs such as `TH1::Fill`,
`TTree::Fill`, `TObject::Write`, `TFile::Write`, and `TFile::Close`.

Paint is out of scope for this plan. Paint remains a separate post-processing
layer for already-finished ROOT files.

The implementation must preserve current Lambda outputs while removing
analysis-callback ownership of `Record::RootArray`, direct histogram/tree
mutation, and caller-managed `recordingScope()` locking.

## Constraints And Decisions

- The project currently builds with `-std=c++17`; do not use `std::span` unless
  the build standard is deliberately upgraded. Use C++17-compatible request-view
  structs with references or pointers, and copy into owned queue payloads before
  returning from public fill methods.
- Naming follows the current repo style: `PascalCase` for types, `camelCase` for
  methods/local variables, and `camelCase_` for private members.
- `Record::Writer` remains non-copyable and non-movable.
- Declarations happen before `Writer::start()`. Fill/checkpoint/finish requests
  happen after `start()`.
- ROOT object creation may stay on the setup thread in v1. Runtime mutation and
  write/close happen on the scribe thread.
- Keep typed enum basis identifiers publicly. Convert to internal `RecordKey`
  for registries and queues.
- Use separate payload queues plus one `grandQueue_` ticket queue. Queue capacity
  applies to `grandQueue_`.
- Keep temporary compatibility only where needed to keep tests compiling during
  migration. New code should use Writer-owned records.

## Target Public API

### Shared ROOT Type Utility

Add a shared utility header, preferably `utils/Utility/RootTypes.hh`.

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

std::string typeName(DataType type);
std::string leafListSuffix(DataType type);
DataType detectBranchType(TBranch* branch);
double toDouble(const Value& value);

} // namespace RootUtil
```

Rules:

- `leafListSuffix(DataType::Double)` returns `"D"`, `Int32` returns `"I"`,
  etc.
- `String` has no ROOT leaf-list suffix and must be branched through ROOT's
  object branch overload.
- `toDouble` accepts numeric, bool, and char values. It throws for `String` and
  `Other`.
- `Probe::BranchType` should become an alias of `RootUtil::DataType`, or a
  bridge should be added first and then collapsed once Probe compiles.

### Writer Identity And Values

Add these to `Record`:

```cpp
namespace Record {

using DataType = RootUtil::DataType;
using Value    = RootUtil::Value;

struct NoBasis {};

struct RecordKey {
    std::type_index domain{typeid(void)};
    std::int64_t value = 0;
};

bool operator==(const RecordKey& a, const RecordKey& b);

struct RecordKeyHash {
    std::size_t operator()(const RecordKey& key) const;
};

template <typename Basis>
RecordKey keyOf(Basis basis);

} // namespace Record
```

`keyOf` must `static_assert(std::is_enum_v<Basis>)` and cast through the enum's
underlying type.

### Declaration Methods

Add Writer-owned declarations:

```cpp
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

template <typename Basis>
void declareHist1D(Basis basis, std::string histName, std::string title,
                   int bins, double low, double high,
                   DataType type = DataType::Double);

template <typename Basis>
void declareHist2D(Basis basis, std::string histName, std::string title,
                   int binsX, double lowX, double highX,
                   int binsY, double lowY, double highY,
                   DataType typeX = DataType::Double,
                   DataType typeY = DataType::Double);

template <typename Basis>
void declareGraph(Basis basis, std::string graphName, std::string title,
                  DataType typeX = DataType::Double,
                  DataType typeY = DataType::Double);

template <typename Basis>
void declareProfile(Basis basis, std::string profileName, std::string title,
                    int binsX, double lowX, double highX,
                    DataType typeX = DataType::Double,
                    DataType typeY = DataType::Double);

template <typename TreeBasis, typename BranchBasis>
void declareTree(TreeBasis treeBasis,
                 std::string treeName,
                 std::string title,
                 std::vector<std::tuple<BranchBasis, std::string, DataType>> branches);
```

Declaration errors:

- `open()` not called before declaration: throw.
- declaration after `start()`: throw.
- duplicate key in the same registry: throw.
- particle child declaration without matching `declareParticleGroup`: throw.
- invalid bins or bounds: throw with object name/key.
- unsupported branch type: throw.

### Fill Methods

Use C++17-compatible input views:

```cpp
template <typename Basis>
struct ParticleFillView {
    Basis basis;
    const std::vector<Physics::Lorentz>& particles;
};

template <typename Basis>
void fillParticleEvent(std::initializer_list<ParticleFillView<Basis>> fills);

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
```

Public fill methods:

- validate that `Writer` is started and accepting requests;
- convert basis enums to `RecordKey`;
- copy all referenced vectors/values into owned request payloads;
- push request payload and matching grand-queue ticket under one mutex;
- never touch ROOT objects directly.

For Lambda, one call to `fillParticleEvent` is one logical event and must
preserve reset/fill/count ordering inside the scribe.

### Lifecycle Methods

Replace the templated RootArray lifecycle API with:

```cpp
void start();
void checkpoint(std::size_t eventIndex);
void finish(std::size_t eventCount);
bool fatalWrite(std::size_t eventCount, std::chrono::milliseconds timeout);
void setQueueCapacity(std::size_t capacity);
std::size_t queueCapacity() const;
std::string stats() const;
```

Keep:

```cpp
void open(Paths paths, HistConfig hist, Meta::Record initialMeta);
TFile* file() const;                  // temporary during migration only
const Paths& paths() const;
const HistConfig& histConfig() const;
Meta::Record& meta();
const Meta::Record& meta() const;
```

`file()` can remain temporarily for older declaration code, but the final
Writer-owned path should not require modules to call it.

## Internal Record Model

Create or reorganize `utils/Record` headers into at least:

- `Record/Types.hh`: public-ish types such as `NoBasis`, `RecordKey`, aliases.
- `Record/Objects.hh`: private ROOT registry records.
- `Record/Requests.hh`: queue payload and barrier records.
- `Record/Writer.hh`: Writer class declaration and small inline template
  wrappers.
- `Record/Finalizer.hh` or `Record/WriterImpl.hh`: non-template lifecycle and
  scribe method definitions, if header-only style is retained.

Owned object records:

```cpp
struct BranchBufferBase {
    virtual ~BranchBufferBase() = default;
    virtual void* address() = 0;
    virtual void set(const Value& value) = 0;
    virtual DataType type() const = 0;
};

template <typename T>
struct BranchBuffer final : BranchBufferBase {
    T value{};
    void* address() override;
    void set(const Value& value) override;
    DataType type() const override;
};

struct BranchRecord {
    TBranch* branch{};
    std::string name;
    DataType type = DataType::Other;
    std::unique_ptr<BranchBufferBase> buffer;
};

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
```

Writer registries:

```cpp
std::unordered_map<RecordKey, ParticleObjects, RecordKeyHash> particleObjects_;
std::unordered_map<RecordKey, Hist1DRecord,  RecordKeyHash> hists1D_;
std::unordered_map<RecordKey, Hist2DRecord,  RecordKeyHash> hists2D_;
std::unordered_map<RecordKey, GraphRecord,   RecordKeyHash> graphs_;
std::unordered_map<RecordKey, ProfileRecord, RecordKeyHash> profiles_;
std::unordered_map<RecordKey, TreeRecord,    RecordKeyHash> trees_;
```

Branch creation rules:

- Arithmetic branches use ROOT leaf-list branches with stable buffer addresses.
- String branches use ROOT's string/object branch overload and store a
  `std::string` buffer.
- `ParticleTree` branches are all `Double` in v1 because they are derived from
  `Physics::ParticleProperty`.
- Explicit `TreeRecord` supports mixed branch types.

## Queue And Scribe Model

Request types:

```cpp
enum class ParticleRequestKind { FillEvent };

struct ParticleGroupFillRequest {
    RecordKey basis{};
    std::vector<Physics::Lorentz> particles;
};

struct ParticleRequest {
    ParticleRequestKind kind = ParticleRequestKind::FillEvent;
    std::vector<ParticleGroupFillRequest> groups;
};

struct Hist1DRequest  { RecordKey basis{}; Value value; };
struct Hist2DRequest  { RecordKey basis{}; Value x; Value y; };
struct GraphRequest   { RecordKey basis{}; Value x; Value y; };
struct ProfileRequest { RecordKey basis{}; Value x; Value y; };

struct TreeRowRequest {
    RecordKey tree{};
    std::vector<std::pair<RecordKey, Value>> values;
};

struct BarrierState {
    std::mutex mutex;
    std::condition_variable cv;
    bool done = false;
    std::exception_ptr exception;
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

Queue state:

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

Push protocol:

1. Public fill method builds an owned payload before taking `queueMutex_`.
2. Lock `queueMutex_`.
3. If not accepting or if `scribeException_` is set, throw.
4. Wait until `grandQueue_.size() < queueCapacity_`, unless pushing fatal.
5. Push payload into its lane queue.
6. Push matching `QueueTicket` into `grandQueue_`.
7. Unlock and `queueNotEmpty_.notify_one()`.

Pop protocol:

1. Scribe locks `queueMutex_`.
2. Wait until `grandQueue_` is not empty or stop/fatal is requested.
3. Pop the front ticket from `grandQueue_`.
4. Pop the matching payload queue.
5. Unlock and `queueNotFull_.notify_one()`.
6. Apply payload outside `queueMutex_`.

Fatal request protocol:

- `fatalWrite` sets `accepting_ = false` before inserting the fatal request.
- Fatal request insertion does not wait for normal queue capacity.
- Producers blocked on `queueNotFull_` must wake and throw.
- If the scribe is already inside a ROOT call, fatal cannot guarantee recovery;
  the timeout result reports this.

Barrier protocol:

- `checkpoint`, `finish`, and `fatalWrite` create a `BarrierState`.
- The scribe stores any request exception into the barrier and marks it done.
- The caller waits on the barrier and rethrows `barrier->exception`.
- `finish` joins the scribe after its barrier completes.

## Request Application

`applyParticleRequest`:

- For each requested particle group, find `ParticleObjects` by key.
- Reset `candidateCount` to zero.
- For each particle:
  - increment `candidateCount`;
  - fill every `ParticleTH1`;
  - fill every `ParticleTH2`;
  - append every `ParticleGraph` point;
  - fill every `ParticleProfile`;
  - fill `ParticleTree` if declared.
- After all particles in the group, fill `count` with `candidateCount` if count
  exists.

`applyHist1DRequest`:

- require registered histogram;
- validate expected type if useful;
- convert request value using `RootUtil::toDouble`;
- call `TH1::Fill`.

`applyHist2DRequest`, `applyGraphRequest`, and `applyProfileRequest`:

- require registered object;
- convert x/y values using `RootUtil::toDouble`;
- call the corresponding ROOT API.

`applyTreeRowRequest`:

- require registered tree;
- verify all supplied branch keys exist;
- set supplied branch buffers;
- for missing branches, leave the previous value only if that behavior is
  explicitly documented. Recommended v1 behavior: require exactly all declared
  branches to be supplied and throw otherwise.
- call `TTree::Fill`.

Conversion and missing-record exceptions must include the record key, object
kind, and expected type.

## Write, Checkpoint, Finish

Add one internal write path:

```cpp
void writeAllToCurrentFile(std::size_t eventCount, bool checkpoint);
void writeParticleObjects(ParticleObjects& object, std::size_t eventCount, bool checkpoint);
void writeIndependentObjects(std::size_t eventCount, bool checkpoint);
```

Rules:

- Reuse current clone-before-scale behavior from `Record::scaleAndWrite`.
- `TH1`-derived objects are cloned, scaled, and written.
- Scale factor is `hist_.histScale / eventCount` when `eventCount > 0`.
- Width scaling applies to 1D histograms only.
- `TH2`, profiles, graphs, and trees are written without width scaling.
- Trees are skipped in checkpoint mode in v1, matching current behavior.
- Final write writes all records, writes `Meta::writeAbout(outFile_, meta_)`,
  runs any `preCloseHook_`, writes the file, closes it, deletes the `TFile`, and
  nulls `outFile_`.

`checkpoint(eventIndex)`:

- enqueue checkpoint barrier request;
- scribe opens checkpoint ROOT file;
- scribe writes all currently applied records to checkpoint file;
- scribe closes checkpoint file;
- caller returns only after checkpoint file is complete.

`finish(eventCount)`:

- enqueue finish barrier request;
- scribe drains all prior fill requests first because of `grandQueue_` ordering;
- scribe writes final ROOT output and closes the file;
- caller waits, rethrows any exception, and joins the scribe.

Destructor:

- If `outFile_` is still open and scribe not started, close/delete it.
- If scribe is running and `finish` was not called, request stop and join if
  possible. Prefer throwing earlier via misuse checks rather than relying on the
  destructor for normal shutdown.

## Implementation Slices

### Slice 1: Shared Root Types

Files:

- `utils/Utility/RootTypes.hh` new.
- `utils/Utility.hh` umbrella update if present/appropriate.
- `utils/Probe/Types.hh` and `utils/Probe/BranchControl.hh` bridge to shared
  type functions.

Tasks:

1. Add `RootUtil::DataType`, `RootUtil::Value`, `typeName`,
   `leafListSuffix`, `detectBranchType`, and `toDouble`.
2. Keep `Probe::BranchType` source-compatible by aliasing it or mapping it.
3. Replace `Probe::BranchControl::branchTypeStr` and `detectType` internals with
   shared helpers while preserving old function names as wrappers if needed.
4. Build and run existing tests.

Verification:

- `make test`
- Existing Probe tests still pass.

### Slice 2: Record Keys, Branch Buffers, And Object Records

Files:

- `utils/Record/Types.hh`
- optionally new `utils/Record/Objects.hh`
- `utils/Record.hh`

Tasks:

1. Add `RecordKey`, `RecordKeyHash`, `keyOf`, `DataType`, and `Value`.
2. Add `BranchBufferBase`, typed `BranchBuffer<T>`, and factory helpers:
   - `makeBranchBuffer(DataType)`;
   - `setBranchBuffer(BranchRecord&, const Value&)`;
   - `declareBranch(TTree&, BranchRecord&)`.
3. Add particle object records and independent object records.
4. Keep old `TH1Record`, `TH2Record`, `EventTH1Record`, `ExtractHist1D`,
   `ExtractHist2D`, `RootObjects`, and `RootArray` temporarily so current Lambda
   still compiles.

Verification:

- Add a focused unit test for `RecordKey` equality/hash and `BranchBuffer`
  setting.
- `make test`

### Slice 3: Writer Registries And Declaration API

Files:

- `utils/Record/Writer.hh`
- `utils/Record/Histogram.hh` if helper reuse is needed
- `utils/Record.hh`

Tasks:

1. Add Writer registries for particle and independent objects.
2. Add declaration state checks:
   - `requireOpenForDeclaration`;
   - `requireNotStarted`;
   - duplicate-key validation.
3. Implement `declareParticleGroup`, count, hist1D, hist2D, graph, profile, and
   tree methods.
4. Implement independent `declareHist1D`, `declareHist2D`, `declareGraph`,
   `declareProfile`, and `declareTree`.
5. Use `outFile_->mkdir` and `TDirectory::cd` inside declarations.
6. Keep old `file()` accessor for compatibility, but new declarations must not
   require callers to use it.

Verification:

- New tests:
  - duplicate declarations throw;
  - declaration after `start()` throws after Slice 4;
  - particle group plus particle hists can be declared without external
    `RootArray`;
  - mixed branch explicit tree declares correctly.
- `make test`

### Slice 4: Queue Infrastructure And Scribe Lifecycle

Files:

- `utils/Record/Writer.hh`
- new `utils/Record/Requests.hh` if useful
- `utils/Record/Finalizer.hh` or new implementation header

Tasks:

1. Add queue payload types and lane queues.
2. Add `setQueueCapacity`, `queueCapacity`, and `stats`.
3. Implement `start()`:
   - require file open;
   - require not already started;
   - set `accepting_ = true`;
   - start `scribe_`.
4. Implement public fill methods that only enqueue.
5. Implement scribe pop helpers and `scribeLoop`.
6. Implement request application methods.
7. Implement exception propagation from scribe to producers and barrier callers.
8. Add `Stop` handling only for destructor/error cleanup, not normal shutdown.

Verification:

- New tests:
  - concurrent producers enqueue fill requests;
  - bounded queue blocks producers until scribe drains;
  - scribe exception propagates to `finish`;
  - `finish` rejects later fill calls.
- `make test`

### Slice 5: Writer-Owned Checkpoint, Finish, And Fatal Write

Files:

- `utils/Record/Finalizer.hh`
- `utils/Record/Writer.hh`
- `utils/Monitor/Logger.hh` and fatal-stall related headers if needed

Tasks:

1. Move final write logic from templated `shutdown(RootArrayT&)` into
   non-template Writer-owned `finish(eventCount)`.
2. Move checkpoint write logic from templated `checkpoint(RootArrayT&, idx)` into
   Writer-owned `checkpoint(eventIndex)`.
3. Implement `fatalWrite(eventCount, timeout)` without requiring external object
   references.
4. Keep logger finishing/reporting behavior initially in drivers if that reduces
   blast radius:
   - Writer writes/closes ROOT.
   - Logger handles terminal/log output.
5. Remove or deprecate `installFatalStallHandler(RootArrayT&)`; replace it with
   a logger-owned fatal handler that calls `writer.fatalWrite`.

Verification:

- New tests:
  - checkpoint includes earlier queued fills;
  - final output file contains histograms and metadata;
  - fatal write path does not block on a full normal queue;
  - fatal timeout returns false if completion cannot be observed.
- `make test`

### Slice 6: Lambda Reconstruction Migration

Files:

- `modules/Lambda/Types.hh`
- `modules/Lambda/Declare.hh`
- `modules/Lambda/Recording.hh`
- `modules/Lambda/Context.hh`
- `modules/Lambda.hh`
- `_Lambda_Reconstruction.cc`
- `_Lambda_Parallel.cc`
- `_Lambda_Test.cc`
- tests touching `Lambda::RootArray`

Tasks:

1. Change `Lambda::configure` to:
   - load `Parameters`;
   - call `Lambda::declareObjects(parameters, writer)`.
2. Change `Lambda::declareObjects` to declare into `Record::Writer`:
   - call `declareParticleGroup` for each `HistogramSet`;
   - call `declareParticleCount`;
   - call `declareParticleHist1D` for each `Recorded_ParticleProperties`;
   - call `declareParticleTree` for `parameters.writeTree`.
3. Change `Lambda::AnalysisContext` to remove `RootArray& histograms`.
4. Change `Lambda::fillCandidates` into a Writer adapter:
   - one `fillParticleEvent<HistogramSet>` call per logical event.
5. Change `Lambda::rootAnalysis` and `Lambda::pythiaAnalysis`:
   - reconstruct candidates;
   - submit to Writer;
   - remove `recordingScope()`.
6. Update drivers:
   - remove `Lambda::RootArray histogramSets`;
   - call `writer.start()` after declarations/bind setup;
   - call `writer.finish(asyncLogger.watch().nEvents)` or actual event count as
     appropriate;
   - keep metadata updates before `finish()`.
7. Update smoke tests to inspect output after `finish` rather than checking
   external in-memory `RootArray` pointers.

Verification:

- `make test`
- Run `_Lambda_Reconstruction.exe` on the fixture config.
- Compare histogram entries/integrals against current baseline for a fixed
  small fixture.
- Confirm `rootAnalysis` callback count equals logical event count, not
  `eventCount * nThreads`.

### Slice 7: Lambda Data-Generation Tree Migration

Files:

- `modules/Lambda/Declare.hh`
- `modules/Lambda/Context.hh`
- `modules/Lambda.hh`
- `_Lambda_Data.cc`

Tasks:

1. Replace `Lambda::DataObjects` ownership of `TTree*`, branch arrays, and
   `treeMutex` with Writer-owned explicit trees.
2. Add Lambda enum bases for raw data trees and branches, for example:
   - `enum class DataTree { Protons, Pions };`
   - `enum class DataBranch { EventIndex, Energy, Px, Py, Pz };`
3. Declare raw trees through `writer.declareTree`.
4. In `dataGenerator`, enqueue `writer.fillTree` rows for protons and pions.
5. Preserve tree and branch names expected by Probe:
   - trees: `Protons`, `Pions`;
   - branches: `event_index`, `Energy`, `pX`, `pY`, `pZ`.
6. Preserve the existing `preCloseHook` index-building behavior if it is still
   needed. It must run on the scribe thread before final `TFile::Write/Close`,
   or be converted into a Writer pre-close hook executed by finish.

Verification:

- Generate a small Lambda data file.
- Run Probe reconstruction against it.
- Confirm Probe can read `event_index`, `Energy`, `pX`, `pY`, `pZ`.
- `make test`

### Slice 8: Monitor And Fatal-Stall Integration

Files:

- `utils/Monitor/Logger.hh`
- `utils/Monitor/Render.hh`
- `utils/Record/Writer.hh`
- drivers

Tasks:

1. Keep `AsyncLogger::initialise(const Record::Writer&)` using `writer.paths()`
   and `writer.histConfig()`.
2. Move fatal-stall orchestration into Monitor:
   - logger detects fatal;
   - logger writes emergency log;
   - logger calls `writer.fatalWrite(eventCount, timeout)`;
   - logger writes final terminal/log state and exits.
3. Ensure Writer no longer captures external object containers.
4. Decide whether `writer.checkpoint(eventIndex)` writes only ROOT and driver
   separately calls logger checkpoint output, or whether a narrow helper remains.
   Recommended: keep ROOT checkpoint and log checkpoint explicit.

Verification:

- Existing monitor logs still include output paths and histogram scale.
- Fatal path can be triggered in a controlled test or manual run without needing
  `RootArray`.
- `make test`

### Slice 9: Cleanup And Compatibility Removal

Files:

- `utils/Record/Types.hh`
- `utils/Record/Histogram.hh`
- `utils/Record/Finalizer.hh`
- `utils/Record.hh`
- docs referencing old RootArray path

Tasks:

1. Remove old `Record::RootObjects`, `RootArray`, free `Record::fill`, and
   `Record::writeAll` if no callers remain.
2. Remove `Writer::recordingScope()`.
3. Remove templated `shutdown(RootArrayT&)`, `checkpoint(RootArrayT&)`, and
   `installFatalStallHandler(RootArrayT&)`.
4. Remove `Lambda::RootArray`, `Lambda::RootObjects`, and `DataObjects` if no
   callers remain.
5. Update `Record.hh` umbrella comments to describe Writer-owned records and
   scribe queues.
6. Update docs that still show old driver lifecycle snippets.

Verification:

- `rg "RootArray|RootObjects|recordingScope|installFatalStallHandler|shutdown\\("`
  should show only intentionally retained docs or unrelated symbols.
- `make test`
- Build all main drivers:
  - `make _Lambda_Reconstruction.exe`
  - `make _Lambda_Parallel.exe`
  - `make _Lambda_Data.exe`
  - `make _Lambda_Test.exe`

## Driver Lifecycle After Migration

Target reconstruction flow:

```cpp
Probe::ProbeParallel probe;
Record::Writer writer;
Monitor::AsyncLogger asyncLogger;

Config::configure(configPath, project, probe, writer, asyncLogger);

Lambda::Parameters physParams;
Lambda::configure(physParams, writer, configPath);

writer.bind(asyncLogger, asyncLogger.watch(),
            [&physParams]() { return Lambda::logString(physParams); });

asyncLogger.initialise(writer);
writer.start();

Lambda::AnalysisContext ctx{physParams, asyncLogger.watch(), asyncLogger, writer};
probe.run([&](const Probe::Event& ev, int threadId) {
    Lambda::rootAnalysis(ev, threadId, ctx);
});

writer.meta().dataset.parent_files = {probe.inputFile()};
Record::Meta::fillDerived(writer.meta(), project, configPath,
                          asyncLogger.watch(), Config::Register{});
Record::Meta::integrityAddFileSha(writer.meta(), configPath);
Record::Meta::integrityAddFileSha(writer.meta(), writer.histConfig().histLimitsFile.Data());

writer.finish(asyncLogger.watch().nEvents);
asyncLogger.finish(...); // exact call shape depends on Monitor integration slice
```

The exact logger finalization call should be settled during Slice 5/8. The key
rule is that Writer final output must be complete before final terminal/log
reporting points at the output file.

## Test Plan

Add or update tests for:

- `RootUtil::DataType` detection and `Value` conversion.
- `Record::RecordKey` equality and hashing for two different enum domains with
  the same underlying value.
- Branch buffers:
  - numeric buffer set and branch declaration;
  - string buffer declaration if string support is enabled in v1;
  - wrong `Value` type throws.
- Writer declarations:
  - duplicate declarations throw;
  - missing particle group throws;
  - declaration after `start()` throws.
- Queue behavior:
  - concurrent producers submit requests safely;
  - bounded queue blocks and drains;
  - producer wakes and throws after scribe exception;
  - finish rejects later fills.
- Scribe application:
  - particle request fills histograms and count correctly;
  - graph/profile requests append/fill correctly;
  - explicit tree requires all branches and writes rows correctly.
- Barriers:
  - checkpoint waits for earlier fills;
  - finish waits for all prior fills;
  - fatal request does not wait for normal queue capacity.
- Lambda:
  - reconstruction smoke test output matches current histogram entries;
  - data-generation file remains readable by Probe;
  - no callback path mutates ROOT objects directly.

Manual checks:

- Run `_Lambda_Reconstruction.exe` with fixed `event_count` and
  `nThreads = 1, 2, 4, 8`.
- Confirm final output file is created and readable.
- Confirm output histograms have stable entries/integrals across thread counts.
- Confirm queue stats report produced/consumed request counts and max backlog.

## Acceptance Criteria

The overhaul is complete when:

- `Record::Writer` owns all output ROOT objects used by Lambda.
- Lambda analysis callbacks never call `TH1::Fill`, `TTree::Fill`, or mutate
  `RootArray`/candidate counters directly.
- No module outside `Record::Writer` owns output `TFile`, `TDirectory`, `TH1`,
  `TH2`, `TGraph`, `TProfile`, `TTree`, or `TBranch` objects.
- `writer.finish(eventCount)` writes final ROOT output and closes the file
  without external object containers.
- `writer.checkpoint(eventIndex)` is an ordered barrier over queued fills.
- Fatal write no longer captures external `RootArray&`.
- Existing tests pass and Lambda smoke output remains consistent.

## Known Risks

- The scribe thread deliberately serializes ROOT output mutation. This improves
  correctness and removes callback-side ROOT contention, but if output filling
  dominates runtime, the scribe can become the throughput ceiling.
- Queue payloads copy vectors of `Physics::Lorentz`; for very large per-event
  candidate lists, a move-oriented API may be needed later.
- ROOT string branches need special handling and should be tested separately.
- Fatal write cannot recover if the scribe is already hung inside a ROOT call.
- During migration, old and new Writer paths must not write the same ROOT object.
  Each slice should keep a clear ownership boundary.
