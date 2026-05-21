#pragma once

#include <cstddef>
#include <functional>
#include <memory>
#include <set>
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

    // parseBranchEntry — parses one branch spec from any of three TOML forms:
    //   1. Inline table:       { name = "Muon_pt", type = "F" }
    //   2. Two-element array:  ["Muon_pt", "F"]
    //   3. Bare string:        "Muon_pt"  (only when allowBareString=true; type=Other)
    //
    // ctx is a "[probe.events.particles.muon]"-style path used in error messages.
    inline BranchSpec parseBranchEntry(const toml::node& n,
                                       bool allowBareString,
                                       const std::string& ctx)
    {
        // Form 1: inline table  { name = "X", type = "F" }
        if (const auto* tbl = n.as_table()) {
            const auto nameOpt = (*tbl)["name"].value<std::string>();
            const auto typeOpt = (*tbl)["type"].value<std::string>();
            if (!nameOpt)
                throw std::runtime_error("[Probe] " + ctx + ": branch table missing 'name'");
            if (!typeOpt)
                throw std::runtime_error("[Probe] " + ctx + ": branch table missing 'type'");
            const BranchType bt = RootUtil::detectBranchType(*typeOpt);
            if (bt == BranchType::Other)
                throw std::runtime_error(
                    "[Probe] " + ctx + ": unknown branch type code '" + *typeOpt + "'");
            return { *nameOpt, bt };
        }
        // Form 2: two-element array  ["X", "F"]
        if (const auto* arr = n.as_array()) {
            if (arr->size() != 2)
                throw std::runtime_error(
                    "[Probe] " + ctx + ": branch array must have exactly 2 elements [name, type], got " +
                    std::to_string(arr->size()));
            const auto nameOpt = (*arr)[0].value<std::string>();
            const auto typeOpt = (*arr)[1].value<std::string>();
            if (!nameOpt || !typeOpt)
                throw std::runtime_error(
                    "[Probe] " + ctx + ": branch array elements must be strings");
            const BranchType bt = RootUtil::detectBranchType(*typeOpt);
            if (bt == BranchType::Other)
                throw std::runtime_error(
                    "[Probe] " + ctx + ": unknown branch type code '" + *typeOpt + "'");
            return { *nameOpt, bt };
        }
        // Form 3: bare string  "X"  (kinematic-only; type detected at runtime)
        if (const auto s = n.value<std::string>()) {
            if (!allowBareString)
                throw std::runtime_error(
                    "[Probe] " + ctx +
                    ": bare string branch not allowed here;"
                    " use [\"name\",\"type\"] or { name=..., type=... }");
            return { *s, BranchType::Other };
        }
        throw std::runtime_error(
            "[Probe] " + ctx + ": unrecognised branch entry"
            " (expected string, [name,type] array, or {name=...,type=...} table)");
    }

    // parseBranchList — parses an array of branch specs using parseBranchEntry.
    inline std::vector<BranchSpec> parseBranchList(const toml::array& arr,
                                                    bool allowBareString,
                                                    const std::string& ctx)
    {
        std::vector<BranchSpec> out;
        out.reserve(arr.size());
        for (const auto& elem : arr)
            out.push_back(parseBranchEntry(elem, allowBareString, ctx));
        return out;
    }

} // namespace detail


// (Phase 11: parseCollectionsFromToml and applyIndexSpecsFromToml removed;
//  use parseProbeConfig for all new TOML parsing.)

// parseProbeConfig — parses the [probe.events.*] / [probe.feed.*] bucket schema.
//
// Labels are auto-discovered by iterating the sub-tables under
// [probe.events.particles], [probe.events.nodes], [probe.feed.particles], and
// [probe.feed.nodes].  No separate declaration list is needed — simply define
// a [probe.events.particles.<label>] block to include that label.
//
// Applies validation rules from docs/ProbeStream.md at parse time.
inline ProbeConfig parseProbeConfig(const toml::table& cfg)
{
    const auto* probeTbl = cfg["probe"].as_table();
    if (!probeTbl)
        throw std::runtime_error("[Probe] parseProbeConfig: missing [probe] table");

    ProbeConfig config;

    // Step 1: parse [probe].stream
    const auto streamStr = (*probeTbl)["stream"].value_or(std::string{"auto"});
    if      (streamStr == "events") config.requestedMode = StreamMode::Events;
    else if (streamStr == "feed")   config.requestedMode = StreamMode::Feed;
    else if (streamStr == "auto")   config.requestedMode = StreamMode::Auto;
    else throw std::runtime_error(
        "[Probe] [probe].stream must be 'auto', 'events', or 'feed', got '" + streamStr + "'");

    const auto* eventsTbl = (*probeTbl)["events"].as_table();
    const auto* feedTbl   = (*probeTbl)["feed"].as_table();

    // Shared helpers — capture detail:: helpers and avoid repeating the label-loop and
    // kinematic/index boilerplate across the four bucket types.

    // Iterate every sub-table in tbl and call fn(label, sub-table).
    auto forEachLabel = [](const toml::table* tbl,
                           const std::function<void(const std::string&,
                                                    const toml::table&)>& fn) {
        if (!tbl) return;
        for (const auto& [k, v] : *tbl) {
            const auto* sub = v.as_table();
            if (sub) fn(std::string{k.str()}, *sub);
        }
    };

    // Parse 4 kinematic branches + coords into spec.coords for particle specs.
    auto parseKinematic = [](const toml::table& tbl, const std::string& ctx,
                              const std::string& label, auto& spec) {
        const auto* arr = tbl["branches"].as_array();
        if (!arr) throw std::runtime_error(ctx + ": missing 'branches' array");
        auto kb = detail::parseBranchList(*arr, /*allowBareString=*/true, ctx + " branches");
        if (kb.size() != 4)
            throw std::runtime_error(ctx + ": must have exactly 4 kinematic branches, got " +
                                     std::to_string(kb.size()));
        spec.coords = detail::makeCoordSpec(tbl["spec"].value_or(0), std::move(kb), label);
    };

    // Parse optional index + index-ordering flags into any spec that carries them.
    auto parseIndexFlags = [](const toml::table& tbl, auto& spec) {
        if (const auto* arr = tbl["index"].as_array(); arr && arr->size() == 2)
            spec.indexBranches.push_back(detail::parseBranchPair(*arr));
        spec.indexSorted    = tbl["index_sorted"].value_or(true);
        spec.indexAscending = tbl["index_ascending"].value_or(true);
        spec.indexMonotonic = tbl["index_monotonic"].value_or(true);
    };

    // Step 2: [probe.events.particles.*]
    forEachLabel(eventsTbl ? (*eventsTbl)["particles"].as_table() : nullptr,
                 [&](const std::string& label, const toml::table& tbl) {
        const std::string ctx = "[probe.events.particles." + label + "]";
        EventParticleSpec spec;
        spec.label = label;
        spec.tree  = tbl["tree"].value_or(std::string{});
        parseKinematic(tbl, ctx, label, spec);
        if (const auto* aux = tbl["aux"].as_array())
            spec.auxBranches = detail::parseBranchList(*aux, false, ctx + " aux");
        parseIndexFlags(tbl, spec);
        config.eventParticles.push_back(std::move(spec));
    });

    // Step 3: [probe.events.nodes.*]
    forEachLabel(eventsTbl ? (*eventsTbl)["nodes"].as_table() : nullptr,
                 [&](const std::string& label, const toml::table& tbl) {
        const std::string ctx = "[probe.events.nodes." + label + "]";
        EventNodeSpec spec;
        spec.label = label;
        spec.tree  = tbl["tree"].value_or(std::string{});
        const auto* arr = tbl["branches"].as_array();
        if (!arr) throw std::runtime_error(ctx + ": missing 'branches' array");
        spec.branches = detail::parseBranchList(*arr, false, ctx + " branches");
        parseIndexFlags(tbl, spec);
        config.eventNodes.push_back(std::move(spec));
    });

    // Step 4: [probe.feed.particles.*]  (index key forbidden in Feed)
    forEachLabel(feedTbl ? (*feedTbl)["particles"].as_table() : nullptr,
                 [&](const std::string& label, const toml::table& tbl) {
        const std::string ctx = "[probe.feed.particles." + label + "]";
        if (tbl["index"].as_array())
            throw std::runtime_error(ctx + ": 'index' key not permitted in Feed");
        FeedParticleSpec spec;
        spec.label = label;
        spec.tree  = tbl["tree"].value_or(std::string{});
        parseKinematic(tbl, ctx, label, spec);
        config.feedParticles.push_back(std::move(spec));
    });

    // Step 5: [probe.feed.nodes.*]  (index key forbidden in Feed)
    forEachLabel(feedTbl ? (*feedTbl)["nodes"].as_table() : nullptr,
                 [&](const std::string& label, const toml::table& tbl) {
        const std::string ctx = "[probe.feed.nodes." + label + "]";
        if (tbl["index"].as_array())
            throw std::runtime_error(ctx + ": 'index' key not permitted in Feed");
        FeedNodeSpec spec;
        spec.label = label;
        spec.tree  = tbl["tree"].value_or(std::string{});
        const auto* arr = tbl["branches"].as_array();
        if (!arr) throw std::runtime_error(ctx + ": missing 'branches' array");
        spec.branches = detail::parseBranchList(*arr, false, ctx + " branches");
        config.feedNodes.push_back(std::move(spec));
    });

    // Validation rule 6: stream mode / bucket mismatch
    if (config.requestedMode == StreamMode::Events && !config.hasEventData())
        throw std::runtime_error("[Probe] stream='events' but no event-bound specs found");
    if (config.requestedMode == StreamMode::Feed && !config.hasFeedData())
        throw std::runtime_error("[Probe] stream='feed' but no feed-bound specs found");
    if (!config.hasEventData() && !config.hasFeedData())
        throw std::runtime_error("[Probe] [probe.events] and [probe.feed] both empty; nothing to stream");

    // Validation rule 7: same label in both events and feed
    {
        std::set<std::string> evLabels;
        for (const auto& s : config.eventParticles) evLabels.insert(s.label);
        for (const auto& s : config.eventNodes)     evLabels.insert(s.label);
        for (const auto& s : config.feedParticles)
            if (evLabels.count(s.label))
                throw std::runtime_error(
                    "[Probe] label '" + s.label + "' present in both events and feed");
        for (const auto& s : config.feedNodes)
            if (evLabels.count(s.label))
                throw std::runtime_error(
                    "[Probe] label '" + s.label + "' present in both events and feed");
    }

    return config;
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
