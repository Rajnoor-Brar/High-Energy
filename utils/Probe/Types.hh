#pragma once

#include <cstdint>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#include "Physics.hh"
#include "Rtypes.h"

namespace Probe {

    using Physics::Lorentz;

    enum class BranchType         { Float, Double, Int32, UInt32, Int64, UInt64, Bool, Other };
    enum class MissingBranchPolicy{ Error };

    struct BranchSpec {
        std::string          name;
        BranchType           type;
        MissingBranchPolicy  policy = MissingBranchPolicy::Error;
    };

    // ── Coordinate specs ─────────────────────────────────────────────────────
    struct CartesianSpec  { std::vector<BranchSpec> branches; };
    struct PtEtaPhiESpec  { std::vector<BranchSpec> branches; };
    struct PtEtaPhiMSpec  { std::vector<BranchSpec> branches; };
    using CoordSpec = std::variant<CartesianSpec, PtEtaPhiESpec, PtEtaPhiMSpec>;

    struct ParticleSpec {
        std::string              label;
        std::string              tree;
        CoordSpec                coords;
        std::vector<BranchSpec>  indexBranches;
        std::vector<BranchSpec>  auxBranches;
    };

    using CollectionSpec = ParticleSpec;

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
    };

} // namespace Probe
