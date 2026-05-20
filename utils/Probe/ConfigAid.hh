#pragma once

#include <cstddef>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include <toml++/toml.hpp>

#include "TFile.h"
#include "TParameter.h"

#include "Probe/Types.hh"
#include "Probe/BranchControl.hh"

namespace Probe {

namespace detail {

    inline CoordSpec makeCoordSpec(int specId,
                                   std::vector<BranchSpec> branches,
                                   const std::string& label)
    {
        switch (specId) {
            case 0: return CartesianSpec{ std::move(branches)};
            case 1: return PtEtaPhiESpec{std::move(branches)};
            case 2: return PtEtaPhiMSpec{std::move(branches)};
            default:
                throw std::runtime_error(
                    "[Probe] invalid coord spec ID " + std::to_string(specId) +
                    " for '" + label + "'");
        }
    }

    inline BranchSpec parseBranchPair(const toml::array& pair) {
        return {pair.at(0).value_or(std::string{}),
                RootUtil::detectBranchType(pair.at(1).value_or(std::string{}))};
    }

} // namespace detail

// applyIndexSpecsFromToml — reads [probe.index] bool arrays and applies them element-wise to collection specs.
inline void applyIndexSpecsFromToml(const toml::table& cfg,
                                    std::vector<CollectionSpec>& specs)
{
    const auto* idxTbl = cfg["probe"]["index"].as_table();
    if (!idxTbl || specs.empty()) return;

    auto parseBoolArr = [idxTbl](const char* key) -> std::vector<bool> {
        const auto* arr = (*idxTbl)[key].as_array();
        if (!arr) return {};
        std::vector<bool> result;
        result.reserve(arr->size());
        for (const auto& v : *arr) result.push_back(v.value_or(true));
        return result;
    };

    const auto sorted    = parseBoolArr("sorted");
    const auto ascending = parseBoolArr("ascending");
    const auto monotonic = parseBoolArr("monotonic");

    for (std::size_t i = 0; i < specs.size(); ++i) {
        if (i < sorted.size())    specs[i].indexSorted    = sorted[i];
        if (i < ascending.size()) specs[i].indexAscending = ascending[i];
        if (i < monotonic.size()) specs[i].indexMonotonic = monotonic[i];
    }
}

// parseCollectionsFromToml — parses [probe].event_particles; supports inline array and named-table syntax.

inline std::vector<CollectionSpec>
parseCollectionsFromToml(const toml::table& cfg)
{
    std::vector<CollectionSpec> out;

    const auto* evArr = cfg["probe"]["event_particles"].as_array();
    if (!evArr || evArr->empty()) return out;

    if ((*evArr)[0].is_string()) {
        // Named-table syntax
        const auto* particleTbl = cfg["probe"]["particle"].as_table();

        for (const auto& elem : *evArr) {
            const std::string label = elem.value_or(std::string{});
            if (label.empty()) continue;

            const auto* ptbl = particleTbl ? (*particleTbl)[label].as_table() : nullptr;
            if (!ptbl)
                throw std::runtime_error(
                    "[Probe] event_particles label '" + label +
                    "' has no matching [probe.particle." + label + "] table");

            const int         specId   = (*ptbl)["spec"].value_or(0);
            const std::string treeName = (*ptbl)["tree_name"].value_or(std::string{});

            std::vector<BranchSpec> momentaBranches;
            for (int i = 1; i <= 4; ++i) {
                const std::string key = "branch_" + std::to_string(i);
                if (const auto* pair = (*ptbl)[key].as_array(); pair && pair->size() == 2)
                    momentaBranches.push_back(detail::parseBranchPair(*pair));
            }
            if (momentaBranches.size() != 4)
                throw std::runtime_error(
                    "[Probe] '" + label + "': expected branch_1..4, got " +
                    std::to_string(momentaBranches.size()));

            std::vector<BranchSpec> indexBranches;
            if (const auto* pair = (*ptbl)["index_branch"].as_array(); pair && pair->size() == 2)
                indexBranches.push_back(detail::parseBranchPair(*pair));

            CollectionSpec spec;
            spec.label         = label;
            spec.tree          = treeName;
            spec.coords        = detail::makeCoordSpec(specId, std::move(momentaBranches), label);
            spec.indexBranches = std::move(indexBranches);
            out.push_back(std::move(spec));
        }
    } else {
        // Inline array syntax
        for (const auto& entry : *evArr) {
            const auto* row = entry.as_array();
            if (!row || row->size() < 5) continue;

            const std::string label    = (*row)[0].value_or(std::string{});
            const int         specId   = (*row)[1].value_or(0);
            const std::string treeName = (*row)[2].value_or(std::string{});

            std::vector<BranchSpec> momentaBranches;
            if (const auto* momentaArr = (*row)[3].as_array()) {
                for (const auto& b : *momentaArr) {
                    if (const auto* pair = b.as_array(); pair && pair->size() == 2)
                        momentaBranches.push_back(detail::parseBranchPair(*pair));
                }
            }
            if (momentaBranches.size() != 4)
                throw std::runtime_error(
                    "[Probe] '" + label + "' must have exactly 4 momenta branches, got " +
                    std::to_string(momentaBranches.size()));

            std::vector<BranchSpec> indexBranches;
            if (const auto* indexArr = (*row)[4].as_array()) {
                for (const auto& b : *indexArr) {
                    if (const auto* pair = b.as_array(); pair && pair->size() == 2)
                        indexBranches.push_back(detail::parseBranchPair(*pair));
                }
            }

            CollectionSpec spec;
            spec.label         = label;
            spec.tree          = treeName;
            spec.coords        = detail::makeCoordSpec(specId, std::move(momentaBranches), label);
            spec.indexBranches = std::move(indexBranches);
            out.push_back(std::move(spec));
        }
    }

    applyIndexSpecsFromToml(cfg, out);
    return out;
}


// resolveEventCount — reads About/events/n_events_total from a ROOT file; returns 0 if absent or non-positive.
inline std::size_t resolveEventCount(const std::string& filepath) {
    std::unique_ptr<TFile> f(TFile::Open(filepath.c_str(), "READ"));
    if (!f || f->IsZombie()) return 0;

    if (auto* dir = f->GetDirectory("About/events")) {
        if (auto* par =
                dynamic_cast<TParameter<Long64_t>*>(dir->Get("n_events_total")))
            if (par->GetVal() > 0)
                return static_cast<std::size_t>(par->GetVal());
    }
    return 0;
}

} // namespace Probe
