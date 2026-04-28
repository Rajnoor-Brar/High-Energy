#pragma once
#include <algorithm>
#include <array>
#include <cctype>
#include <cstddef>
#include <cmath>
#include <filesystem>
#include <map>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <toml++/toml.hpp>

#include "Config.hh"
#include "Probe.hh"
#include "TTree.h"
#include "Types.hh"
#include "TypeAid.hh"
#include "ParamAid.hh"

namespace Lambda {

    inline constexpr std::array<Physics::ParticleProperty, 6> Recorded_ParticleProperties = {
        Physics::ParticleProperty::Mass_Invariant,
        Physics::ParticleProperty::Energy_Net,
        Physics::ParticleProperty::Momentum_Net,
        Physics::ParticleProperty::Momentum_Transverse,
        Physics::ParticleProperty::Momentum_Z,
        Physics::ParticleProperty::Pseudorapidity
    };

    inline constexpr std::array<HistogramSet, 0> kTreeEnabledSets = {
        // HistogramSet::Selected
    };

    inline std::optional<Config::Bounds> explicitBounds(const toml::node& node) {
        if (!node.is_array()) return std::nullopt;

        const toml::array& array = *node.as_array();
        if (array.size() != 2) {
            throw std::runtime_error( "Expected exactly 2 numeric values in explicit histogram bounds");
        }

        const auto low  = array[0].value<Double_t>();
        const auto high = array[1].value<Double_t>();
        if (!low || !high) throw std::runtime_error("Expected numeric histogram bounds");

        return Config::Bounds{*low, *high};
    }

    inline const Config::Bounds& levelBounds(const Config::Root& root, Physics::ParticleProperty property, Config::RangeSize level) {
        const auto quantityIt = root.particleLimits.find(property);
        if (quantityIt == root.particleLimits.end()) {
            throw std::runtime_error( "No configured limits for particle property " + propertyName(property));
        }

        const auto levelIt = quantityIt->second.find(level);
        if (levelIt == quantityIt->second.end()) {
            throw std::runtime_error( "No configured " + propertyAlias(property) + " limit for level " + levelName(level));
        }
        return levelIt->second;
    }

    inline const Config::Bounds& levelBounds(const Config::Root& root, Physics::EventProperty property, Config::RangeSize level) {
        const auto quantityIt = root.eventLimits.find(property);
        if (quantityIt == root.eventLimits.end()) {
            throw std::runtime_error( "No configured limits for event property " + propertyName(property));
        }

        const auto levelIt = quantityIt->second.find(level);
        if (levelIt == quantityIt->second.end()) {
            throw std::runtime_error( "No configured " + propertyAlias(property) + " limit for level " + levelName(level));
        }
        return levelIt->second;
    }

    template <typename Property>
    inline std::optional<Config::Bounds> boundsFromNode(const toml::node& node, const Config::Root& root, Property property) {
        if (const auto bounds = explicitBounds(node)) return bounds;
        if (!node.is_string()) return std::nullopt;
        return levelBounds( root, property, Config::stringToLevel(node.value<string>().value_or("")));
    }

    template <typename Property>
    inline Config::Bounds resolveBounds(const toml::table& table, const Config::Root& root, Property property, Config::RangeSize defaultLevel) {
        std::optional<Config::Bounds> resolved;
        const string primaryKey = propertyName(property);
        const string aliasKey   = propertyAlias(property);

        if (const toml::node* node = table.get(primaryKey)) resolved = boundsFromNode(*node, root, property);

        if (!resolved && aliasKey != primaryKey) {
            if (const toml::node* node = table.get(aliasKey)) resolved = boundsFromNode(*node, root, property);
        }

        if (!resolved) resolved = levelBounds(root, property, defaultLevel);

        return *resolved;
    }

    inline SpecsArray inputSchema(const Parameters& params) {
        SpecsArray schema;
        const InputConfig& input = params.input;
        for (const auto& candidate : params.candidates) {
            if (!candidate.enabled) continue;
            schema.push_back({
                candidate.label,
                resolveTreeName(input, candidate),
                Probe::CartesianSpec{input.px, input.py, input.pz, input.energy},
                {input.indexBranch},
                {}
            });
        }
        return schema;
    }

    inline SpecsArray inputSchema() {return inputSchema(Parameters{}); }

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

    inline void declareDataObjects(DataObjects& data, Config::Root& root) {
        if (root.outFile == nullptr)
            throw std::invalid_argument("root.outFile must not be null");

        root.outFile->cd();
        data.protons = new TTree("Protons", "Final state protons");
        data.pions   = new TTree("Pions",   "Final state #pi^{-}");

        auto declareBranches = [](TTree* tree, std::array<Double_t, 4>& branches, Int_t& idx) {
            tree->Branch("event_index", &idx, "event_index/I");
            tree->Branch("Energy",      &branches[0], "Energy/D");
            tree->Branch("pX",          &branches[1], "pX/D");
            tree->Branch("pY",          &branches[2], "pY/D");
            tree->Branch("pZ",          &branches[3], "pZ/D");
        };
        declareBranches(data.protons, *data.protonBranches, *data.protonEventIndex);
        declareBranches(data.pions,   *data.pionBranches,   *data.pionEventIndex);
    }

    inline bool shouldWriteTree(HistogramSet set, const Parameters& parameters) {
        const bool treeEnabled = std::find(
            kTreeEnabledSets.begin(),
            kTreeEnabledSets.end(),
            set) != kTreeEnabledSets.end();
        if (!treeEnabled) return false;

        return std::any_of(
            parameters.candidates.begin(),
            parameters.candidates.end(),
            [](const CandidateConfig& candidate) {
                return candidate.enabled && candidate.writeTree;
            });
    }

    inline void declareObjects(RootArray& objects,
                               const Parameters& parameters,
                               Config::Root& root)
    {
        if (root.outFile == nullptr)
            throw std::invalid_argument("root.outFile must not be null");

        objects.clear();
        objects.reserve(kHistogramSetCount);

        for (const auto& histogramSet : kHistogramSetMap) {
            RootObjects object{};

            object.basis = histogramSet.id;
            object.dir   = root.outFile->mkdir(histogramSet.directoryName);
            object.dir->cd();

            if (!parameters.setEventLimits.count(histogramSet.id) ||
                !parameters.setEventLimits.at(histogramSet.id).count(Physics::EventProperty::Multiplicity)) {
                throw std::runtime_error("No Multiplicity limit defined for set " +
                                         std::string(histogramSet.tag));
            }
            const Config::Bounds multiplicityBounds =
                parameters.setEventLimits.at(histogramSet.id).at(Physics::EventProperty::Multiplicity);

            object.count = new TH1D(
                (std::string(histogramSet.tag) + "CountHist").c_str(),
                "Count of Reconstructed Candidates",
                static_cast<int>(multiplicityBounds.high - multiplicityBounds.low + 1),
                multiplicityBounds.low - 0.5,
                multiplicityBounds.high + 0.5);

            for (const auto& prop : Recorded_ParticleProperties) {
                if (!parameters.setParticleLimits.count(histogramSet.id) ||
                    !parameters.setParticleLimits.at(histogramSet.id).count(prop)) {
                    throw std::runtime_error(
                        "No limit defined for set " + std::string(histogramSet.tag) +
                        " and property " + Physics::particlePropertyName(prop));
                }
                const Config::Bounds bounds =
                    parameters.setParticleLimits.at(histogramSet.id).at(prop);
                const std::string propName = Physics::particlePropertyName(prop);
                const std::string histName =
                    std::string(histogramSet.tag) + "_" + propName + "_Hist";

                object.hists1D.push_back(Record::TH1Record{
                    new TH1D(histName.c_str(),
                             (propName + " Distribution").c_str(),
                             root.binCount,
                             bounds.low,
                             bounds.high),
                    prop
                });
            }

            if (shouldWriteTree(histogramSet.id, parameters)) {
                const std::string treeName = std::string(histogramSet.tag) + "_Candidates";
                object.trees.push_back(
                    Record::declareTree(
                        object.dir,
                        treeName,
                        std::string(histogramSet.tag) + " candidate quantities",
                        Recorded_ParticleProperties
                    )
                );
            }

            objects.push_back(std::move(object));
        }
    }

    inline void extractPhysics(const string& configPath,
                               Parameters& parameters,
                               const Config::Root& root) {
        toml::table config = toml::parse_file(configPath);

        parameters.massTolerance   = config["lambda"]["delta_mass_gev"].value_or(0.1);
        parameters.ThetaTolerance  = config["lambda"]["delta_theta_rad"].value_or(0.1);
        parameters.cosThetaTolerance = std::cos(parameters.ThetaTolerance);
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
