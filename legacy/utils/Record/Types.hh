#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <typeindex>
#include <unordered_map>
#include <utility>
#include <vector>

#include "Config.hh"
#include "Physics.hh"
#include "Utility/RootTypes.hh"
#include "TDirectory.h"
#include "TH1D.h"
#include "TH2.h"
#include "TGraph.h"
#include "TProfile.h"
#include "TTree.h"

namespace Record {

    using DataType = RootUtil::DataType;
    using Value    = RootUtil::Value;

    struct RecordKey {
        std::type_index domain{typeid(void)};
        std::int64_t value = 0;
    };

    bool operator==(const RecordKey& a, const RecordKey& b);

    struct RecordKeyHash {
        std::size_t operator()(const RecordKey& key) const;
    };

    std::string keyString(const RecordKey& key);

    template <typename Basis>
    RecordKey keyOf(Basis basis);

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
        void set(const Value& incoming) override;
        DataType type() const override;
    };

    struct BranchRecord {
        TBranch* branch{};
        std::string name;
        DataType type = DataType::Other;
        std::unique_ptr<BranchBufferBase> buffer;
    };

    std::unique_ptr<BranchBufferBase> makeBranchBuffer(DataType type);
    void setBranchBuffer(BranchRecord& record, const Value& value);
    void declareBranch(TTree& tree, BranchRecord& record);

    // AxisSpec — one histogram axis. Bundling {bins, low, high} keeps the
    // declare* signatures short and makes x/y axis groups impossible to
    // misorder (declareParticleHist2D previously took 11 scalar parameters).
    struct AxisSpec {
        int      bins = 0;
        double   low  = 0.0;
        double   high = 0.0;
    };

    // ── CloneSet — the one master+per-worker-clones storage shape ───────────
    // Replaces eight structurally identical structs (ParticleTH1/TH2/Graph/
    // Profile + Hist1D/Hist2D/Graph/ProfileRecord storage). `master` is owned
    // by the output TFile's directory; clones are detached per-worker copies
    // merged back at finalize (Cloning.hh).
    template <typename TObj>
    struct CloneSet {
        TObj*                              master{};
        std::vector<std::unique_ptr<TObj>> clones;   // [workerIdx]
    };

    // Graph clones additionally track the next free point per worker.
    template <typename TObj>
    struct GraphCloneSet : CloneSet<TObj> {
        std::vector<std::int32_t> nextPoint;   // [workerIdx]
    };

    struct ParticleTH1 : CloneSet<TH1> {
        Physics::ParticleProperty property{};
    };

    struct ParticleTH2 : CloneSet<TH2> {
        Physics::ParticleProperty propertyX{};
        Physics::ParticleProperty propertyY{};
    };

    struct ParticleGraph : GraphCloneSet<TGraph> {
        Physics::ParticleProperty propertyX{};
        Physics::ParticleProperty propertyY{};
    };

    struct ParticleProfile : CloneSet<TProfile> {
        Physics::ParticleProperty propertyX{};
        Physics::ParticleProperty propertyY{};
    };

    struct ParticleTree {
        TTree*                       tree{};
        std::unique_ptr<std::mutex>  mutex = std::make_unique<std::mutex>();
        std::vector<Physics::ParticleProperty> properties;
        std::vector<BranchRecord> branches;
    };

    using ParticleCount = CloneSet<TH1>;

    struct ParticleObjects {
        RecordKey basis{};
        std::string name;
        TDirectory* dir{};
        ParticleCount count;
        std::vector<ParticleTH1>     hists1D;
        std::vector<ParticleTH2>     hists2D;
        std::vector<ParticleGraph>   graphs;
        std::vector<ParticleProfile> profiles;
        ParticleTree                 tree;
    };

    struct Hist1DRecord : CloneSet<TH1> {
        DataType type = DataType::Double;
    };

    struct Hist2DRecord : CloneSet<TH2> {
        DataType typeX = DataType::Double;
        DataType typeY = DataType::Double;
    };

    struct GraphRecord : GraphCloneSet<TGraph> {
        DataType typeX = DataType::Double;
        DataType typeY = DataType::Double;
    };

    struct ProfileRecord : CloneSet<TProfile> {
        DataType typeX = DataType::Double;
        DataType typeY = DataType::Double;
    };

    struct ExplicitTreeRecord {
        TTree*                       tree{};
        std::unique_ptr<std::mutex>  mutex = std::make_unique<std::mutex>();
        std::unordered_map<RecordKey, BranchRecord, RecordKeyHash> branches;
        std::vector<RecordKey> branchOrder;
    };

} // namespace Record

#include "Record/Type_Methods.hh"
