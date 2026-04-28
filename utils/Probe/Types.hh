#pragma once

#include <cstdint>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <variant>
#include <vector>

#include "Physics.hh"
#include "Rtypes.h"

namespace Probe {

    using Lorentz = Physics::Lorentz;

    // ── Coordinate specs ─────────────────────────────────────────────────────
    struct CartesianSpec  { std::string px, py, pz, E; };
    struct PtEtaPhiESpec  { std::string pt, eta, phi, E; };
    struct PtEtaPhiMSpec  { std::string pt, eta, phi, M; };
    using CoordSpec = std::variant<CartesianSpec, PtEtaPhiESpec, PtEtaPhiMSpec>;

    enum class BranchType         { Float, Double, Int32, UInt32, Int64, UInt64, Bool, Other };
    enum class MissingBranchPolicy{ Error };

    struct BranchSpec {
        std::string          name;
        BranchType           type;
        MissingBranchPolicy  policy = MissingBranchPolicy::Error;
    };

    struct CollectionSpec {
        std::string              label;
        std::string              tree;
        CoordSpec                coords;
        std::vector<std::string> indexBranches;
        std::vector<BranchSpec>  auxBranches;
    };

    struct ScalarSpec {
        std::string name;
        std::string tree;
        std::string branch;
        BranchType  type;
    };

    struct AuxColumn {
        std::variant<
            std::vector<int64_t>,
            std::vector<uint64_t>,
            std::vector<double>,
            std::vector<bool>
        > data;

        template<typename T>
        const std::vector<T>& as() const {
            if (const auto* p = std::get_if<std::vector<T>>(&data)) return *p;
            throw std::runtime_error("[Probe] AuxColumn type mismatch");
        }
        void clear() { std::visit([](auto& v){ v.clear(); }, data); }
    };

    using ScalarValue = std::variant<int64_t, uint64_t, double, bool>;

    struct EventKey {
        std::vector<Long64_t> components;
        bool operator< (const EventKey& o) const { return components <  o.components; }
        bool operator==(const EventKey& o) const { return components == o.components; }
        bool operator!=(const EventKey& o) const { return !(*this == o); }
    };

    // ── Event ─────────────────────────────────────────────────────────────────
    struct Event {
        Long64_t index{-1};
        std::unordered_map<std::string, std::vector<Lorentz>>                        particles;
        std::unordered_map<std::string, std::unordered_map<std::string, AuxColumn>>  aux;
        std::unordered_map<std::string, ScalarValue>                                 scalars;

        const std::vector<Lorentz>& operator[](const std::string& label) const {
            auto it = particles.find(label);
            if (it == particles.end())
                throw std::runtime_error("[Probe] Event: unknown label '" + label + "'");
            return it->second;
        }
        std::size_t n(const std::string& label) const {
            auto it = particles.find(label);
            return it == particles.end() ? 0 : it->second.size();
        }
        template<typename T>
        const std::vector<T>& column(const std::string& label, const std::string& col) const {
            auto li = aux.find(label);
            if (li == aux.end())
                throw std::runtime_error("[Probe] Event: unknown label '" + label + "'");
            auto ci = li->second.find(col);
            if (ci == li->second.end())
                throw std::runtime_error("[Probe] Event: unknown column '" + col + "' in '" + label + "'");
            return ci->second.as<T>();
        }
        template<typename T>
        T scalar(const std::string& name) const {
            auto it = scalars.find(name);
            if (it == scalars.end())
                throw std::runtime_error("[Probe] Event: unknown scalar '" + name + "'");
            if (const auto* p = std::get_if<T>(&it->second)) return *p;
            throw std::runtime_error("[Probe] Event: scalar '" + name + "' type mismatch");
        }
    };

} // namespace Probe
