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

    inline void extractPhysics(const string& configPath,
                               Parameters& parameters,
                               const Record::HistConfig& hist) {
        toml::table config = Config::parseConfig(configPath);

        parameters.massTolerance     = config["lambda"]["delta_mass_gev"].value_or(0.1);
        parameters.thetaTolerance    = config["lambda"]["delta_theta_rad"].value_or(0.1);
        parameters.cosThetaTolerance = std::cos(parameters.thetaTolerance);
        parameters.reservedProtons = static_cast<std::size_t>(
            config["lambda"]["reserved_protons"].value_or<int64_t>(20));

        parameters.protonLabel = config["lambda"]["proton_label"].value_or("protons");
        parameters.pionLabel   = config["lambda"]["pion_label"].value_or("pions");

        // [lambda.analysis].writeTree — list of set names that get a candidate TTree.
        // e.g. writeTree = ["Selected"]
        parameters.writeTree.clear();
        if (const auto* analysisTable = config["lambda"]["analysis"].as_table()) {
            if (const auto* arr = (*analysisTable)["writeTree"].as_array()) {
                for (const auto& entry : *arr) {
                    const auto name = entry.value<std::string>();
                    if (!name) continue;
                    for (const auto& hs : kHistogramSetMap) {
                        if (std::string(hs.tag) == *name) {
                            parameters.writeTree.push_back(hs.id);
                            break;
                        }
                    }
                }
            }
        }

        parameters.setParticleLimits.clear();
        parameters.setEventLimits.clear();

        if (!std::filesystem::exists(hist.histLimitsFile.Data())) {
            throw std::runtime_error("Histogram limits file does not exist: " +
                                     string(hist.histLimitsFile.Data()));
        }

        toml::table limitTable = toml::parse_file(hist.histLimitsFile.Data());
        auto* limitsRoot = limitTable["record"]["limits"].as_table();
        if (!limitsRoot) {
            throw std::runtime_error(
                "[Config] Limits file missing [record.limits] section: " +
                string(hist.histLimitsFile.Data()));
        }
        for (const auto& histogramSet : kHistogramSetMap) {
            if (!limitsRoot->contains(histogramSet.tag) ||
                !(*limitsRoot)[histogramSet.tag].is_table()) {
                throw std::runtime_error("Missing histogram set table: " + string(histogramSet.tag));
            }

            toml::table& subTable = *(*limitsRoot)[histogramSet.tag].as_table();
            Config::RangeSize defaultLevel = Config::RangeSize::Moderate;
            if (const auto dn = subTable["default"]; dn.is_string())
                defaultLevel = Config::stringToLevel(dn.value<string>().value_or("Moderate"));

            for (const Physics::ParticleProperty prop : Recorded_ParticleProperties) {
                parameters.setParticleLimits[histogramSet.id][prop] =
                    resolveBounds(subTable, hist, prop, defaultLevel);
            }

            const std::array<Physics::EventProperty, 1> eventProperties = { Physics::EventProperty::Multiplicity };

            for (const Physics::EventProperty property : eventProperties) {
                parameters.setEventLimits[histogramSet.id][property] =
                    resolveBounds(subTable, hist, property, defaultLevel);
            }
        }
    }
}
