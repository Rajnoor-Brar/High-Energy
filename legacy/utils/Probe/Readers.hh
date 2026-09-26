#pragma once

#include <cstdint>
#include <limits>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "TTreeReader.h"
#include "TTreeReaderArray.h"
#include "TTreeReaderValue.h"

#include "Probe/BranchControl.hh"
#include "Probe/Types.hh"

namespace Probe {

    class FlatReader {
      public:
        FlatReader(TFile* file, const EventParticleSpec& spec,
                   const std::string& filepath,
                   Long64_t minKey, Long64_t maxKey,
                   Bounds entryBounds = {},
                   bool hasEntryBounds = false);

        FlatReader(const FlatReader&)            = delete;
        FlatReader& operator=(const FlatReader&) = delete;

        const std::string& label() const;
        EventKey currentKey() const;
        bool exhausted() const;
        bool beyondMax() const;
        void ensureLabel(Event& ev) const;
        void drain(const EventKey& key, Event& ev);
        bool keyRange(Long64_t lo, Long64_t hi, Long64_t& outMin, Long64_t& outMax);
        const TTree* treePtr() const { return tree_; }

      private:
        Long64_t idxValue() const;

        struct AuxBuf { float f = 0.f; double d = 0.0; int32_t i = 0; uint32_t u = 0; int64_t l = 0; uint64_t ul = 0; bool b = false; };

        void bindAux(const BranchSpec& bspec);
        static AuxColumn makeAuxCol(BranchType t);
        void appendAux(std::unordered_map<std::string, AuxColumn>& m);

        std::string              label_;
        std::string              filepath_;
        CoordSpec                coords_;
        TTree*                   tree_         = nullptr;
        std::string              idxName_;
        Long64_t                 cursor_       = 0;
        Long64_t                 totalEntries_ = 0;
        Long64_t                 entryEnd_     = 0;
        Long64_t                 minKey_;
        Long64_t                 maxKey_;
        bool                     idxIsLong_   = false;
        Int_t                    idxI_         = 0;
        Long64_t                 idxL_         = 0;
        BranchControl::KinBuf    kinBuf_[4];
        std::vector<std::string> auxNames_;
        std::vector<BranchType>  auxTypes_;
        std::vector<AuxBuf>      auxBufs_;
    };

    // Forward declarations — full definitions follow in the Phase 4/5 sections.
    class EventReader;
    class FeedReader;

    // ── Phase 6: polymorphic EventStream ─────────────────────────────────────
    class EventStream {
      public:
        EventStream(const std::string& filepath,
                    const ProbeConfig& cfg,
                    Long64_t firstEvent,
                    Long64_t lastEvent,
                    std::size_t nEventsHint = 0,
                    const std::vector<Bounds>& entryBounds = {});

        ~EventStream();

        EventStream(const EventStream&)            = delete;
        EventStream& operator=(const EventStream&) = delete;

        bool next();
        const Event& event()    const;
        Event         takeEvent();
        std::size_t   nEvents() const;
        std::size_t   index()   const;

      private:
        std::string   filepath_;
        TFile*        file_       = nullptr;
        Event         current_;
        std::size_t   index_      = 0;
        std::size_t   nEvents_    = 0;
        Long64_t      firstEvent_ = 0;
        Long64_t      lastEvent_  = -1;
        Long64_t      nextEvent_  = 0;

        std::vector<std::unique_ptr<EventReader>> readers_;
    };

    // ── Phase 6: FeedStream ────────────────────────────────────────────────────
    class FeedStream {
      public:
        FeedStream(const std::string& filepath,
                   const ProbeConfig& cfg,
                   Long64_t firstEntry,
                   Long64_t lastEntry);
        ~FeedStream();

        FeedStream(const FeedStream&)            = delete;
        FeedStream& operator=(const FeedStream&) = delete;

        bool next();
        const Feed& current()   const { return current_; }
        Feed         takeCurrent() { return std::move(current_); }
        Long64_t     entryCount() const;

      private:
        std::string   filepath_;
        TFile*        file_       = nullptr;
        Feed          current_;
        Long64_t      firstEntry_ = 0;
        Long64_t      lastEntry_  = -1;
        Long64_t      nextEntry_  = 0;

        std::vector<std::unique_ptr<FeedReader>> readers_;
    };

// ── Phase 4: BranchHandle + abstract EventReader hierarchy ───────────────────

namespace detail {

    // Type traits for BranchHandle visitors.
    template<typename T> struct IsReaderValue : std::false_type {};
    template<typename T> struct IsReaderValue<TTreeReaderValue<T>> : std::true_type {};

    template<typename T> struct IsReaderArray : std::false_type {};
    template<typename T> struct IsReaderArray<TTreeReaderArray<T>> : std::true_type {};

} // namespace detail

// BranchHandle — variant-backed handle for a single TTreeReaderValue<T> or
// TTreeReaderArray<T>.  Consolidates the per-type switch logic scattered across
// FlatReader::AuxBuf/appendAux.
struct BranchHandle {
    using HandleVar = std::variant<
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
    >;

    HandleVar h;

    template<typename T>
    explicit BranchHandle(std::unique_ptr<T> ptr) : h(std::move(ptr)) {}

    BranchHandle(const BranchHandle&) = delete;
    BranchHandle& operator=(const BranchHandle&) = delete;
    BranchHandle(BranchHandle&&) = default;
    BranchHandle& operator=(BranchHandle&&) = default;

    // readScalar — dereferences a Value handle; throws if this is an Array handle.
    AuxValue readScalar() const;
    // readArray — collects an Array handle's contents; throws if this is a Value handle.
    AuxColumn readArray() const;
    // appendInto — appends the current scalar value into col.  col.data must already
    // hold the matching vector<T> alternative.  Throws if this is an Array handle.
    void appendInto(AuxColumn& col) const;
};

// EventReader — abstract base for all event-side readers.
// Each implementation populates a slice of an Event struct for event index K.
class EventReader {
public:
    virtual ~EventReader() = default;
    virtual void seekToEvent(Long64_t K) = 0;
    virtual void readForEvent(Long64_t K, Event& out) = 0;
    virtual Bounds eventRange() const = 0;
    virtual std::string treeName() const = 0;
    virtual const TTree* treePtr() const = 0;
};

// EventParticleReaderArray — per-entry TTreeReaderArray reader for Lorentz particles.
class EventParticleReaderArray : public EventReader {
public:
    EventParticleReaderArray(TFile* file, const EventParticleSpec& spec,
                             const std::string& filepath,
                             Long64_t firstEntry, Long64_t lastEntry);
    EventParticleReaderArray(const EventParticleReaderArray&) = delete;
    EventParticleReaderArray& operator=(const EventParticleReaderArray&) = delete;

    void seekToEvent(Long64_t K) override;
    void readForEvent(Long64_t K, Event& out) override;
    Bounds eventRange() const override { return {firstEntry_, lastEntry_}; }
    std::string treeName() const override { return treeName_; }
    const TTree* treePtr() const override { return tree_; }

private:
    std::string label_;
    std::string treeName_;
    CoordSpec   coords_;
    TTree*      tree_  = nullptr;
    TTreeReader reader_;
    Long64_t    firstEntry_, lastEntry_;
    std::unique_ptr<TTreeReaderArray<float>> kinArrays_[4];
    std::vector<std::string>  auxNames_;
    std::vector<BranchHandle> auxHandles_;
};

// EventParticleReaderRowJoin — row-indexed reader for Lorentz particles.
// Thin adapter over FlatReader that implements the EventReader interface.
class EventParticleReaderRowJoin : public EventReader {
public:
    EventParticleReaderRowJoin(TFile* file, const EventParticleSpec& spec,
                               const std::string& filepath,
                               Long64_t minKey, Long64_t maxKey,
                               Bounds entryBounds = {},
                               bool hasEntryBounds = false);
    EventParticleReaderRowJoin(const EventParticleReaderRowJoin&) = delete;
    EventParticleReaderRowJoin& operator=(const EventParticleReaderRowJoin&) = delete;

    // seekToEvent — no-op for sequential forward iteration (FlatReader self-advances).
    void seekToEvent(Long64_t K) override { (void)K; }
    void readForEvent(Long64_t K, Event& out) override;
    Bounds eventRange() const override { return {minKey_, maxKey_}; }
    std::string treeName() const override;
    const TTree* treePtr() const override;

    // Non-virtual helpers used by EventStream's compat ctor for key-range scanning.
    bool     exhausted()  const;
    EventKey currentKey() const;
    bool     keyRange(Long64_t lo, Long64_t hi, Long64_t& outMin, Long64_t& outMax) const;

private:
    std::unique_ptr<FlatReader> inner_;
    Long64_t                    minKey_, maxKey_;
};

// EventNodeReaderArray — per-entry TTreeReaderArray reader for node columns (no Lorentz).
// Uses BranchHandle to support all branch types.
class EventNodeReaderArray : public EventReader {
public:
    EventNodeReaderArray(TFile* file, const EventNodeSpec& spec,
                         const std::string& filepath,
                         Long64_t firstEntry, Long64_t lastEntry);
    EventNodeReaderArray(const EventNodeReaderArray&) = delete;
    EventNodeReaderArray& operator=(const EventNodeReaderArray&) = delete;

    void seekToEvent(Long64_t K) override;
    void readForEvent(Long64_t K, Event& out) override;
    Bounds eventRange() const override { return {firstEntry_, lastEntry_}; }
    std::string treeName() const override { return treeName_; }
    const TTree* treePtr() const override { return tree_; }

private:
    std::string label_;
    std::string treeName_;
    TTree*      tree_  = nullptr;
    TTreeReader reader_;
    Long64_t    firstEntry_, lastEntry_;
    std::vector<std::string>  branchNames_;
    std::vector<BranchHandle> handles_;
};

// ── Phase 5: FeedReader hierarchy ─────────────────────────────────────────────

// FeedReader — abstract base for per-entry Feed readers.
// Each implementation reads one TTree entry and populates one slice of a Feed struct.
class FeedReader {
public:
    virtual ~FeedReader() = default;
    virtual void readEntry(Long64_t N, Feed& out) = 0;
    virtual Long64_t entryCount() const = 0;
    virtual std::string treeName() const = 0;
    virtual const TTree* treePtr() const = 0;
};

// FeedParticleReader — per-entry scalar Lorentz particle reader.
// Reads four kinematic scalar branches per entry and fills Feed.particle[label].
class FeedParticleReader : public FeedReader {
public:
    FeedParticleReader(TFile* file, const FeedParticleSpec& spec,
                       const std::string& filepath,
                       Long64_t firstEntry = 0,
                       Long64_t lastEntry  = std::numeric_limits<Long64_t>::max());
    FeedParticleReader(const FeedParticleReader&) = delete;
    FeedParticleReader& operator=(const FeedParticleReader&) = delete;

    void readEntry(Long64_t N, Feed& out) override;
    Long64_t entryCount() const override { return entryCount_; }
    std::string treeName() const override { return treeName_; }
    const TTree* treePtr() const override { return tree_; }

private:
    std::string              label_;
    std::string              treeName_;
    CoordSpec                coords_;
    TTree*                   tree_       = nullptr;
    TTreeReader              reader_;
    Long64_t                 entryCount_ = 0;
    // Four scalar kinematic handles (TTreeReaderValue<float>), built in constructor body
    std::vector<BranchHandle> kinHandles_;
};

// FeedNodeReader — per-entry scalar and/or variable-length-array reader for node columns.
// Fills Feed.node[label][branchName] with AuxValue (scalar or vector<T> alternative).
// Branch kind (scalar vs array) is auto-detected: if the ROOT branch title contains "["
// the branch is treated as variable-length array and read via TTreeReaderArray;
// otherwise it is read as a scalar via TTreeReaderValue.
class FeedNodeReader : public FeedReader {
public:
    FeedNodeReader(TFile* file, const FeedNodeSpec& spec,
                   const std::string& filepath,
                   Long64_t firstEntry = 0,
                   Long64_t lastEntry  = std::numeric_limits<Long64_t>::max());
    FeedNodeReader(const FeedNodeReader&) = delete;
    FeedNodeReader& operator=(const FeedNodeReader&) = delete;

    void readEntry(Long64_t N, Feed& out) override;
    Long64_t entryCount() const override { return entryCount_; }
    std::string treeName() const override { return treeName_; }
    const TTree* treePtr() const override { return tree_; }

private:
    std::string label_;
    std::string treeName_;
    TTree*      tree_       = nullptr;
    TTreeReader reader_;
    Long64_t    entryCount_ = 0;
    std::vector<std::string>  branchNames_;
    std::vector<bool>         isArray_;     // true → TTreeReaderArray, false → TTreeReaderValue
    std::vector<BranchHandle> handles_;
};

// EventNodeReaderRowJoin — row-indexed reader for node columns (no Lorentz).
// Uses raw TTree + SetBranchAddress (same pattern as FlatReader) for scalar branches.
class EventNodeReaderRowJoin : public EventReader {
public:
    EventNodeReaderRowJoin(TFile* file, const EventNodeSpec& spec,
                           const std::string& filepath,
                           Long64_t minKey, Long64_t maxKey,
                           Bounds entryBounds = {},
                           bool hasEntryBounds = false);
    EventNodeReaderRowJoin(const EventNodeReaderRowJoin&) = delete;
    EventNodeReaderRowJoin& operator=(const EventNodeReaderRowJoin&) = delete;

    void seekToEvent(Long64_t K) override { (void)K; }  // no-op for sequential use
    void readForEvent(Long64_t K, Event& out) override;
    Bounds eventRange() const override { return {minKey_, maxKey_}; }
    std::string treeName() const override { return treeName_; }
    const TTree* treePtr() const override { return tree_; }

private:
    struct NodeBuf {
        float f=0.f; double d=0.0; int32_t i32=0; uint32_t u32=0;
        int64_t i64=0; uint64_t u64=0; bool b=false;
    };
    static AuxColumn makeAuxCol(BranchType t);
    void bindBranch(const BranchSpec& bspec);
    void appendRow(std::unordered_map<std::string, AuxColumn>& nodeMap);

    std::string label_;
    std::string treeName_;
    TTree*      tree_         = nullptr;
    Long64_t    cursor_       = 0;
    Long64_t    totalEntries_ = 0;
    Long64_t    entryEnd_     = 0;
    Long64_t    minKey_       = 0;
    Long64_t    maxKey_       = 0;
    bool        idxIsLong_    = false;
    Int_t       idxI_         = 0;
    Long64_t    idxL_         = 0;
    std::vector<std::string> branchNames_;
    std::vector<BranchType>  branchTypes_;
    std::vector<NodeBuf>     bufs_;

    Long64_t idxVal() const { return idxIsLong_ ? idxL_ : static_cast<Long64_t>(idxI_); }
};

} // namespace Probe
