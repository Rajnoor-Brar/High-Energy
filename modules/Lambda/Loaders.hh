#pragma once

#include <array>
#include <cmath>
#include <cstddef>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

#include <toml++/toml.hpp>

#include "Parameters.hh"

namespace Lambda {

    inline void loadInputSection(const toml::table& config, InputConfig& input) {
        const auto* section = config["input"].as_table();
        if (!section) return;

        input.indexBranch = (*section)["index_branch"].value_or(input.indexBranch);
        input.energy      = (*section)["energy"].value_or(input.energy);
        input.px          = (*section)["px"].value_or(input.px);
        input.py          = (*section)["py"].value_or(input.py);
        input.pz          = (*section)["pz"].value_or(input.pz);

        for (auto&& [key, value] : *section) {
            if (!value.is_table()) continue;
            const auto* sub = value.as_table();
            if (auto treeName = (*sub)["tree_name"].value<string>())
                input.treeNames[string(key.str())] = *treeName;
        }
    }

    inline void loadCandidatesSection(const toml::table& config, std::vector<CandidateConfig>& candidates) {
        const auto* section = config["candidates"].as_table();
        if (!section || section->empty()) return;

        candidates.clear();
        for (auto&& [key, value] : *section) {
            if (!value.is_table()) continue;
            const auto* sub = value.as_table();

            CandidateConfig candidate;
            candidate.label     = string(key.str());
            candidate.enabled   = (*sub)["enabled"].value_or(true);
            candidate.writeTree = (*sub)["write_tree"].value_or(true);
            candidate.pidAbs    = (*sub)["pid_abs"].value_or(0);
            candidates.push_back(candidate);
        }
    }

    inline void extractPhysics(const string& configPath,
                               Parameters& parameters,
                               const Config::Register& root) {
        toml::table config = toml::parse_file(configPath);

        parameters.massTolerance     = config["lambda"]["delta_mass_gev"].value_or(0.1);
        parameters.thetaTolerance    = config["lambda"]["delta_theta_rad"].value_or(0.1);
        parameters.cosThetaTolerance = std::cos(parameters.thetaTolerance);
        parameters.reservedProtons = static_cast<std::size_t>(
            config["lambda"]["reserved_protons"].value_or<int64_t>(20));

        parameters.setParticleLimits.clear();
        parameters.setEventLimits.clear();

        loadInputSection(config, parameters.input);
        loadCandidatesSection(config, parameters.candidates);

        if (!std::filesystem::exists(root.histLimitsFile.Data())) {
            throw std::runtime_error("Histogram limits file does not exist: " +
                                     string(root.histLimitsFile.Data()));
        }

        toml::table limitTable = toml::parse_file(root.histLimitsFile.Data());
        for (const auto& histogramSet : kHistogramSetMap) {
            if (!limitTable.contains(histogramSet.tag) || !limitTable[histogramSet.tag].is_table()) {
                throw std::runtime_error("Missing histogram set table: " + string(histogramSet.tag));
            }

            toml::table& subTable = *limitTable[histogramSet.tag].as_table();
            Config::RangeSize defaultLevel = Config::RangeSize::Moderate;
            if (const auto dn = subTable["default"]; dn.is_string())
                defaultLevel = Config::stringToLevel(dn.value<string>().value_or("Moderate"));

            for (const Physics::ParticleProperty prop : Recorded_ParticleProperties) {
                parameters.setParticleLimits[histogramSet.id][prop] =
                    resolveBounds(subTable, root, prop, defaultLevel);
            }

            const std::array<Physics::EventProperty, 1> eventProperties = { Physics::EventProperty::Multiplicity };

            for (const Physics::EventProperty property : eventProperties) {
                parameters.setEventLimits[histogramSet.id][property] =
                    resolveBounds(subTable, root, property, defaultLevel);
            }
        }
    }
}
