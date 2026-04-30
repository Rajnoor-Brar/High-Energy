#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <stdexcept>
#include <string>

#include "TH1D.h"
#include "TTree.h"

#include "ParamAid.hh"
#include "Parameters.hh"

namespace Lambda {

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

    inline void declareDataObjects(DataObjects& data, Config::Register& root) {
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
                               Config::Register& root)
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
}
