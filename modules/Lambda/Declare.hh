#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include "Record/Writer.hh"
#include "Parameters.hh"

namespace Lambda {

    inline void declareDataObjects(Record::Writer& writer) {
        using Record::DataType;

        const std::vector<std::tuple<DataBranch, std::string, DataType>> branches = {
            {DataBranch::EventIndex, "event_index", DataType::Int32},
            {DataBranch::Energy,     "Energy",      DataType::Double},
            {DataBranch::Px,         "pX",          DataType::Double},
            {DataBranch::Py,         "pY",          DataType::Double},
            {DataBranch::Pz,         "pZ",          DataType::Double},
        };

        writer.declareTree(DataTree::Protons, "Protons", "Final state protons", branches);
        writer.declareTree(DataTree::Pions,   "Pions",   "Final state #pi^{-}", branches);
    }

    inline void declareObjects(const Parameters& parameters,  Record::Writer& writer ){
        const Record::HistConfig& hist = writer.histConfig();

        for (const auto& histogramSet : kHistogramSetMap) {
            writer.declareParticleGroup(histogramSet.id, histogramSet.directoryName, histogramSet.tag);

            if (!parameters.setEventLimits.count(histogramSet.id) ||
                !parameters.setEventLimits.at(histogramSet.id).count(Physics::EventProperty::Multiplicity)) {
                throw std::runtime_error("No Multiplicity limit defined for set " + std::string(histogramSet.tag));
            }
            const Config::Bounds multiplicityBounds = parameters.setEventLimits.at(histogramSet.id).at(Physics::EventProperty::Multiplicity);

            writer.declareParticleCount(
                histogramSet.id,
                std::string(histogramSet.tag) + "CountHist",
                "Count of Reconstructed Candidates",
                static_cast<int>(multiplicityBounds.high - multiplicityBounds.low + 1),
                multiplicityBounds.low - 0.5,
                multiplicityBounds.high + 0.5
            );

            for (const auto& prop : Recorded_ParticleProperties) {
                if (!parameters.setParticleLimits.count(histogramSet.id) ||
                    !parameters.setParticleLimits.at(histogramSet.id).count(prop)) {
                    throw std::runtime_error( "No limit defined for set " + std::string(histogramSet.tag) + " and property " + Physics::particlePropertyName(prop));
                }
                const Config::Bounds bounds = parameters.setParticleLimits.at(histogramSet.id).at(prop);
                const std::string propName = Physics::particlePropertyName(prop);

                writer.declareParticleHist1D(
                    histogramSet.id,
                    prop,
                    std::string(histogramSet.tag) + "_" + propName + "_Hist",
                    propName + " Distribution",
                    hist.binCount,
                    bounds.low,
                    bounds.high);
            }

            const bool enableTree = std::find( parameters.writeTree.begin(), parameters.writeTree.end(), histogramSet.id) != parameters.writeTree.end();

            if (enableTree) {
                writer.declareParticleTree(
                    histogramSet.id,
                    std::string(histogramSet.tag) + "_candidates",
                    "Reconstructed " + std::string(histogramSet.tag) + " candidates",
                    std::vector<Physics::ParticleProperty>(  Recorded_ParticleProperties.begin(), Recorded_ParticleProperties.end()));
            }
        }
    }
} // namespace Lambda
