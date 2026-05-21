#pragma once

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <variant>
#include <vector>

#include "Physics.hh"
#include "Rtypes.h"
#include "Utility/RootTypes.hh"

namespace Probe {

    using Physics::Lorentz;

    using BranchType = RootUtil::DataType;

    struct BranchSpec {
        std::string          name;
        BranchType           type;
    };

    // ── Coordinate specs ─────────────────────────────────────────────────────
    struct CartesianSpec  { std::vector<BranchSpec> branches; };
    struct PtEtaPhiESpec  { std::vector<BranchSpec> branches; };
    struct PtEtaPhiMSpec  { std::vector<BranchSpec> branches; };
    using CoordSpec = std::variant<CartesianSpec, PtEtaPhiESpec, PtEtaPhiMSpec>;

    // ── Spec types ───────────────────────────────────────────────────────────

    // EventParticleSpec — per-particle collection within the Events bucket.
    // Identical to the former CollectionSpec; CollectionSpec is now an alias.
    struct EventParticleSpec {
        std::string              label;
        std::string              tree;
        CoordSpec                coords;
        std::vector<BranchSpec>  indexBranches;   // empty → per-entry array source
        std::vector<BranchSpec>  auxBranches;     // per-particle aux columns
        bool indexSorted    = true;
        bool indexAscending = true;
        bool indexMonotonic = true;
    };

    // EventNodeSpec — independent column group within the Events bucket.
    struct EventNodeSpec {
        std::string              label;
        std::string              tree;
        std::vector<BranchSpec>  indexBranches;   // empty → per-entry array source
        std::vector<BranchSpec>  branches;
        bool indexSorted    = true;
        bool indexAscending = true;
        bool indexMonotonic = true;
    };

    // FeedParticleSpec — per-entry scalar particle within the Feed bucket.
    struct FeedParticleSpec {
        std::string  label;
        std::string  tree;
        CoordSpec    coords;
    };

    // FeedNodeSpec — per-entry scalar/array columns within the Feed bucket.
    struct FeedNodeSpec {
        std::string              label;
        std::string              tree;
        std::vector<BranchSpec>  branches;
    };

    // ── Stream discriminators ─────────────────────────────────────────────────
    // StreamMode — user-facing request in ProbeConfig.
    enum class StreamMode { Auto, Events, Feed };
    // ActiveMode — resolved by ProbeParallel after examining ProbeConfig.
    enum class ActiveMode { Events, Feed, Mixed };
    // StreamType — internal detail for the legacy flat-vs-vector path. Not public API.
    enum class StreamType { Unset, Events, Vectors };

    enum class CallbackMode { WorkerThread, CollectorThread };

    // ── ProbeConfig ───────────────────────────────────────────────────────────
    struct ProbeConfig {
        StreamMode                       requestedMode = StreamMode::Auto;
        std::vector<EventParticleSpec>   eventParticles;
        std::vector<EventNodeSpec>       eventNodes;
        std::vector<FeedParticleSpec>    feedParticles;
        std::vector<FeedNodeSpec>        feedNodes;

        bool hasEventData() const {
            return !eventParticles.empty() || !eventNodes.empty();
        }
        bool hasFeedData() const {
            return !feedParticles.empty() || !feedNodes.empty();
        }
    };

    // ── Bounds / EventKey ────────────────────────────────────────────────────
    struct Bounds {
        Long64_t first = 0;
        Long64_t last  = -1;

        bool valid() const { return first <= last; }
    };

    // ── AuxColumn — typed vector variant for per-particle/per-node columns ───
    // Broadened in Phase 1 to cover float, int32_t, uint32_t alongside the
    // original four alternatives (double, int64_t, uint64_t, bool).
    struct AuxColumn {
        std::variant<
            std::vector<double>, std::vector<float>,
            std::vector<int32_t>, std::vector<uint32_t>,
            std::vector<int64_t>, std::vector<uint64_t>,
            std::vector<bool>
        > data;

        template<typename T>
        const std::vector<T>& as() const {
            if (const auto* p = std::get_if<std::vector<T>>(&data)) return *p;
            throw std::runtime_error("[Probe] AuxColumn type mismatch");
        }
        void clear() { std::visit([](auto& v){ v.clear(); }, data); }
    };

    // ── AuxValue — scalar (or array) value for Feed.node entries ─────────────
    using AuxValue = std::variant<
        double, float, int32_t, uint32_t, int64_t, uint64_t, bool,
        std::vector<double>, std::vector<float>,
        std::vector<int32_t>, std::vector<uint32_t>,
        std::vector<int64_t>, std::vector<uint64_t>,
        std::vector<bool>
    >;

    struct EventKey {
        std::vector<Long64_t> components;
        bool operator< (const EventKey& o) const { return components <  o.components; }
        bool operator==(const EventKey& o) const { return components == o.components; }
        bool operator!=(const EventKey& o) const { return !(*this == o); }
    };

    // ── Event ─────────────────────────────────────────────────────────────────
    struct Event {
        Long64_t index{-1};
        // Phase 7: renamed from particles/aux → particle/node (consistent with Feed).
        std::unordered_map<std::string, std::vector<Lorentz>>                        particle;
        std::unordered_map<std::string, std::unordered_map<std::string, AuxColumn>>  node;

        const std::vector<Lorentz>& operator[](const std::string& label) const {
            auto it = particle.find(label);
            if (it == particle.end())
                throw std::runtime_error("[Probe] Event: unknown label '" + label + "'");
            return it->second;
        }
        std::size_t n(const std::string& label) const {
            auto it = particle.find(label);
            return it == particle.end() ? 0 : it->second.size();
        }
        template<typename T>
        const std::vector<T>& column(const std::string& label, const std::string& col) const {
            auto li = node.find(label);
            if (li == node.end())
                throw std::runtime_error("[Probe] Event: unknown label '" + label + "'");
            auto ci = li->second.find(col);
            if (ci == li->second.end())
                throw std::runtime_error("[Probe] Event: unknown column '" + col + "' in '" + label + "'");
            return ci->second.as<T>();
        }

    };

    // ── Feed ──────────────────────────────────────────────────────────────────
    struct Feed {
        Long64_t index{-1};
        std::unordered_map<std::string, Lorentz>                                       particle;
        std::unordered_map<std::string, std::unordered_map<std::string, AuxValue>>     node;

        const Lorentz& particles(const std::string& label) const {
            auto it = particle.find(label);
            if (it == particle.end())
                throw std::runtime_error("[Probe] Feed: unknown particle label '" + label + "'");
            return it->second;
        }
        const std::unordered_map<std::string, AuxValue>& nodes(const std::string& label) const {
            auto it = node.find(label);
            if (it == node.end())
                throw std::runtime_error("[Probe] Feed: unknown node label '" + label + "'");
            return it->second;
        }
        template<typename T>
        const T& value(const std::string& label, const std::string& col) const {
            const auto& nm = nodes(label);
            auto it = nm.find(col);
            if (it == nm.end())
                throw std::runtime_error("[Probe] Feed: unknown column '" + col + "' in node '" + label + "'");
            if (const T* p = std::get_if<T>(&it->second)) return *p;
            throw std::runtime_error("[Probe] Feed: type mismatch for '" + col + "' in '" + label + "'");
        }
    };

    // QueuedFrame — queue payload for ProbeParallel.
    // Feed field is default-constructed (empty maps) in Event-only mode (near-zero cost).
    struct QueuedFrame {
        std::size_t workerIndex = 0;
        Long64_t    eventIndex  = 0;
        Event       event;
        Feed        feed;
    };

} // namespace Probe
