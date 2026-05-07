#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <stdexcept>
#include <string>

#include "TH1D.h"
#include "TTree.h"

#include "Record/Writer.hh"
#include "Parameters.hh"

namespace Lambda {

    // ── declareDataObjects ───────────────────────────────────────────────────
    // Restored from b522cfd (deleted by f1fe646 mid Pipeline-A migration).
    // Creates the Protons / Pions output trees with the branch layout that
    // [probe].event_particles in Lambda_Reconstruction.toml expects:
    //   event_index/I, Energy/D, pX/D, pY/D, pZ/D
    inline void declareDataObjects(DataObjects& data, Record::Writer& writer) {
        TFile* outFile = writer.file();
        if (outFile == nullptr)
            throw std::invalid_argument("writer.file() must not be null");

        outFile->cd();
        data.protons = new TTree("Protons", "Final state protons");
        data.pions   = new TTree("Pions",   "Final state #pi^{-}");

        auto declareBranches = [](TTree* tree, std::array<Double_t, 4>& branches, Int_t& idx) {
            tree->Branch("event_index", &idx,           "event_index/I");
            tree->Branch("Energy",      &branches[0],   "Energy/D");
            tree->Branch("pX",          &branches[1],   "pX/D");
            tree->Branch("pY",          &branches[2],   "pY/D");
            tree->Branch("pZ",          &branches[3],   "pZ/D");
        };
        declareBranches(data.protons, *data.protonBranches, *data.protonEventIndex);
        declareBranches(data.pions,   *data.pionBranches,   *data.pionEventIndex);
    }

    inline void declareObjects(RootArray& objects,
                               const Parameters& parameters,
                               Record::Writer& writer)
    {
        TFile* outFile = writer.file();
        if (outFile == nullptr)
            throw std::invalid_argument("writer.file() must not be null");

        const Record::HistConfig& hist = writer.histConfig();

        objects.clear();
        objects.reserve(kHistogramSetCount);

        for (const auto& histogramSet : kHistogramSetMap) {
            RootObjects object{};

            object.basis = histogramSet.id;
            object.dir   = outFile->mkdir(histogramSet.directoryName);
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
                             hist.binCount,
                             bounds.low,
                             bounds.high),
                    prop
                });
            }

            // Declare candidate TTree if this set appears in parameters.writeTree.
            const bool enableTree = std::find(
                parameters.writeTree.begin(),
                parameters.writeTree.end(),
                histogramSet.id) != parameters.writeTree.end();

            if (enableTree) {
                object.trees.push_back(Record::declareTree(
                    object.dir,
                    std::string(histogramSet.tag) + "_candidates",
                    "Reconstructed " + std::string(histogramSet.tag) + " candidates",
                    Recorded_ParticleProperties
                ));
            }

            objects.push_back(std::move(object));
        }
    }
}