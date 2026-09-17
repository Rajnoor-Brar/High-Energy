#pragma once

#include <cstdint>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <variant>

#include "TBranch.h"

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

    inline std::string typeName(DataType type) {
        switch (type) {
            case DataType::Float:  return "Float_t";
            case DataType::Double: return "Double_t";
            case DataType::Int32:  return "Int_t";
            case DataType::UInt32: return "UInt_t";
            case DataType::Int64:  return "Long64_t";
            case DataType::UInt64: return "ULong64_t";
            case DataType::Bool:   return "Bool_t";
            case DataType::Char:   return "Char_t";
            case DataType::String: return "std::string";
            case DataType::Other:  return "other";
        }
        return "unknown";
    }

    inline std::string leafListSuffix(DataType type) {
        switch (type) {
            case DataType::Float:  return "F";
            case DataType::Double: return "D";
            case DataType::Int32:  return "I";
            case DataType::UInt32: return "i";
            case DataType::Int64:  return "L";
            case DataType::UInt64: return "l";
            case DataType::Bool:   return "O";
            case DataType::Char:   return "B";
            case DataType::String: return "C";
            case DataType::Other:  return "";
        }
        return "";
    }

    inline DataType detectBranchType(char code) {
        switch (code) {
            case 'F': return DataType::Float;
            case 'D': return DataType::Double;
            case 'I': return DataType::Int32;
            case 'i': return DataType::UInt32;
            case 'L': return DataType::Int64;
            case 'l': return DataType::UInt64;
            case 'O': return DataType::Bool;
            case 'B': return DataType::Char;
            case 'C': return DataType::String;
            default:  return DataType::Other;
        }
    }

    inline DataType detectBranchType(const std::string& text) {
        return text.empty() ? DataType::Other : detectBranchType(text[0]);
    }

    inline DataType detectBranchType(TBranch* branch) {
        if (branch == nullptr) return DataType::Other;

        const std::string title = branch->GetTitle();
        if (title.size() >= 2 && title[title.size() - 2] == '/')
            return detectBranchType(title.back());

        const std::string className = branch->GetClassName();
        if (className == "string" || className == "std::string")
            return DataType::String;

        return DataType::Other;
    }

    inline double toDouble(const Value& value) {
        return std::visit([](const auto& v) -> double {
            using T = std::decay_t<decltype(v)>;
            if constexpr (std::is_same_v<T, std::string>) {
                throw std::runtime_error("RootUtil::toDouble: std::string is not numeric");
            } else {
                return static_cast<double>(v);
            }
        }, value);
    }

} // namespace RootUtil
