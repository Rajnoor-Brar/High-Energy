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

    struct ParticleTH1 {
        TH1*                                hist{};   // master
        std::vector<std::unique_ptr<TH1>>   clones;   // [workerIdx]
        Physics::ParticleProperty property{};
    };

    struct ParticleTH2 {
        TH2*                                hist{};
        std::vector<std::unique_ptr<TH2>>   clones;
        Physics::ParticleProperty propertyX{};
        Physics::ParticleProperty propertyY{};
    };

    struct ParticleGraph {
        TGraph*                                graph{};
        std::vector<std::unique_ptr<TGraph>>   clones;
        std::vector<std::int32_t>              nextPoint;   // [workerIdx]
        Physics::ParticleProperty propertyX{};
        Physics::ParticleProperty propertyY{};
    };

    struct ParticleProfile {
        TProfile*                                profile{};
        std::vector<std::unique_ptr<TProfile>>   clones;
        Physics::ParticleProperty propertyX{};
        Physics::ParticleProperty propertyY{};
    };

    struct ParticleTree {
        TTree*                       tree{};
        std::unique_ptr<std::mutex>  mutex = std::make_unique<std::mutex>();
        std::vector<Physics::ParticleProperty> properties;
        std::vector<BranchRecord> branches;
    };

    struct ParticleCount {
        TH1*                              hist{};
        std::vector<std::unique_ptr<TH1>> clones;
    };

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

    struct Hist1DRecord {
        TH1*                              hist{};
        std::vector<std::unique_ptr<TH1>> clones;
        DataType type = DataType::Double;
    };

    struct Hist2DRecord {
        TH2*                              hist{};
        std::vector<std::unique_ptr<TH2>> clones;
        DataType typeX = DataType::Double;
        DataType typeY = DataType::Double;
    };

    struct GraphRecord {
        TGraph*                              graph{};
        std::vector<std::unique_ptr<TGraph>> clones;
        std::vector<std::int32_t>            nextPoint;   // [workerIdx]
        DataType typeX = DataType::Double;
        DataType typeY = DataType::Double;
    };

    struct ProfileRecord {
        TProfile*                              profile{};
        std::vector<std::unique_ptr<TProfile>> clones;
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
