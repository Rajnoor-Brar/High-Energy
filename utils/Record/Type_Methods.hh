#pragma once

#include "Record/Types.hh"

namespace Record {

    inline bool operator==(const RecordKey& a, const RecordKey& b) {
        return a.domain == b.domain && a.value == b.value;
    }

    inline std::size_t RecordKeyHash::operator()(const RecordKey& key) const {
        const std::size_t h1 = key.domain.hash_code();
        const std::size_t h2 = std::hash<std::int64_t>{}(key.value);
        return h1 ^ (h2 + 0x9e3779b97f4a7c15ULL + (h1 << 6) + (h1 >> 2));
    }

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

    template <typename T>
    inline void* BranchBuffer<T>::address() { return &value; }

    template <typename T>
    inline void BranchBuffer<T>::set(const Value& incoming) {
        if (const auto* typed = std::get_if<T>(&incoming)) {
            value = *typed;
            return;
        }
        throw std::runtime_error(
            "Record::BranchBuffer type mismatch: expected " +
            RootUtil::typeName(type()) + " value");
    }

    template <> inline DataType BranchBuffer<float>::type() const { return DataType::Float; }
    template <> inline DataType BranchBuffer<double>::type() const { return DataType::Double; }
    template <> inline DataType BranchBuffer<std::int32_t>::type() const { return DataType::Int32; }
    template <> inline DataType BranchBuffer<std::uint32_t>::type() const { return DataType::UInt32; }
    template <> inline DataType BranchBuffer<std::int64_t>::type() const { return DataType::Int64; }
    template <> inline DataType BranchBuffer<std::uint64_t>::type() const { return DataType::UInt64; }
    template <> inline DataType BranchBuffer<bool>::type() const { return DataType::Bool; }
    template <> inline DataType BranchBuffer<char>::type() const { return DataType::Char; }
    template <> inline DataType BranchBuffer<std::string>::type() const { return DataType::String; }

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

} // namespace Record
