#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <typeindex>
#include <unordered_map>
#include <utility>
#include <vector>

#include "Config.hh"
#include "Physics.hh"
#include "Record/Extract.hh"
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

    struct NoBasis {};

    struct RecordKey {
        std::type_index domain{typeid(void)};
        std::int64_t value = 0;
    };

    inline bool operator==(const RecordKey& a, const RecordKey& b) {
        return a.domain == b.domain && a.value == b.value;
    }

    struct RecordKeyHash {
        std::size_t operator()(const RecordKey& key) const {
            const std::size_t h1 = key.domain.hash_code();
            const std::size_t h2 = std::hash<std::int64_t>{}(key.value);
            return h1 ^ (h2 + 0x9e3779b97f4a7c15ULL + (h1 << 6) + (h1 >> 2));
        }
    };

    inline std::string keyString(const RecordKey& key) {
        return std::string(key.domain.name()) + ":" + std::to_string(key.value);
    }

    template <typename Basis>
    inline RecordKey keyOf(Basis basis) {
        static_assert(std::is_enum_v<Basis>, "Record::keyOf requires an enum basis");
        using Underlying = std::underlying_type_t<Basis>;
        return RecordKey{std::type_index(typeid(Basis)),
                         static_cast<std::int64_t>(static_cast<Underlying>(basis))};
    }

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

        void set(const Value& incoming) override {
            if (const auto* typed = std::get_if<T>(&incoming)) {
                value = *typed;
                return;
            }
            throw std::runtime_error(
                "Record::BranchBuffer type mismatch: expected " +
                RootUtil::typeName(type()) + " value");
        }

        DataType type() const override;
    };

    template <> inline DataType BranchBuffer<float>::type() const { return DataType::Float; }
    template <> inline DataType BranchBuffer<double>::type() const { return DataType::Double; }
    template <> inline DataType BranchBuffer<std::int32_t>::type() const { return DataType::Int32; }
    template <> inline DataType BranchBuffer<std::uint32_t>::type() const { return DataType::UInt32; }
    template <> inline DataType BranchBuffer<std::int64_t>::type() const { return DataType::Int64; }
    template <> inline DataType BranchBuffer<std::uint64_t>::type() const { return DataType::UInt64; }
    template <> inline DataType BranchBuffer<bool>::type() const { return DataType::Bool; }
    template <> inline DataType BranchBuffer<char>::type() const { return DataType::Char; }
    template <> inline DataType BranchBuffer<std::string>::type() const { return DataType::String; }

    struct BranchRecord {
        TBranch* branch{};
        std::string name;
        DataType type = DataType::Other;
        std::unique_ptr<BranchBufferBase> buffer;
    };

    inline std::unique_ptr<BranchBufferBase> makeBranchBuffer(DataType type) {
        switch (type) {
            case DataType::Float:  return std::make_unique<BranchBuffer<float>>();
            case DataType::Double: return std::make_unique<BranchBuffer<double>>();
            case DataType::Int32:  return std::make_unique<BranchBuffer<std::int32_t>>();
            case DataType::UInt32: return std::make_unique<BranchBuffer<std::uint32_t>>();
            case DataType::Int64:  return std::make_unique<BranchBuffer<std::int64_t>>();
            case DataType::UInt64: return std::make_unique<BranchBuffer<std::uint64_t>>();
            case DataType::Bool:   return std::make_unique<BranchBuffer<bool>>();
            case DataType::Char:   return std::make_unique<BranchBuffer<char>>();
            case DataType::String: return std::make_unique<BranchBuffer<std::string>>();
            case DataType::Other:
                throw std::runtime_error("Record::makeBranchBuffer: unsupported DataType::Other");
        }
        throw std::runtime_error("Record::makeBranchBuffer: unknown data type");
    }

    inline void setBranchBuffer(BranchRecord& record, const Value& value) {
        if (!record.buffer)
            throw std::runtime_error("Record::setBranchBuffer: branch '" + record.name + "' has no buffer");
        record.buffer->set(value);
    }

    inline void declareBranch(TTree& tree, BranchRecord& record) {
        if (!record.buffer) record.buffer = makeBranchBuffer(record.type);
        if (record.name.empty())
            throw std::runtime_error("Record::declareBranch: branch name must not be empty");
        if (record.type == DataType::Other)
            throw std::runtime_error("Record::declareBranch: unsupported type for branch '" + record.name + "'");

        if (record.type == DataType::String) {
            record.branch = tree.Branch(record.name.c_str(),
                                        static_cast<std::string*>(record.buffer->address()));
            return;
        }

        const std::string suffix = RootUtil::leafListSuffix(record.type);
        if (suffix.empty())
            throw std::runtime_error("Record::declareBranch: missing leaf suffix for branch '" + record.name + "'");
        const std::string leafList = record.name + "/" + suffix;
        record.branch = tree.Branch(record.name.c_str(), record.buffer->address(), leafList.c_str());
    }

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

    struct ExplicitTreeRecord {
        TTree* tree{};
        std::unordered_map<RecordKey, BranchRecord, RecordKeyHash> branches;
        std::vector<RecordKey> branchOrder;
    };

    struct TH1Record {
        TH1D*                    hist{};
        Physics::ParticleProperty property{};
    };
    struct TH2Record {
        TH2*                     hist{};
        Physics::ParticleProperty propertyX{};
        Physics::ParticleProperty propertyY{};
    };
    struct TreeRecord {
        TTree* tree{};
        std::vector<Physics::ParticleProperty>   properties{};
        std::unique_ptr<std::vector<Double_t>>  branchValues{std::make_unique<std::vector<Double_t>>()};
    };
    struct EventTH1Record {
        TH1D*                 hist{};
        Physics::EventProperty property{};
    };
    struct ExtractHist1D {
        TH1D*       hist{};
        Record::Extract::Fn extractor{};
    };
    struct ExtractHist2D {
        TH2*        hist{};
        Record::Extract::Fn extractorX{};
        Record::Extract::Fn extractorY{};
    };

    template <typename Basis = NoBasis>
    struct RootObjects {
        Basis basis{};
        TDirectory* dir{};
        TH1D* count{};
        Int_t candidateCount{};
        std::vector<TH1Record>      hists1D;
        std::vector<EventTH1Record> eventHists1D;
        std::vector<TH2*>           hists2D;
        std::vector<TGraph*>        graphs;
        std::vector<TProfile*>      profiles;
        std::vector<TreeRecord>     trees;
        std::vector<ExtractHist1D>  extractHists1D;
        std::vector<ExtractHist2D>  extractHists2D;
    };

    template <typename Basis = NoBasis>
    using RootArray = std::vector<RootObjects<Basis>>;
}
