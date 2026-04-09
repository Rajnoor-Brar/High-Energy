#pragma once

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <iostream>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "Math/Vector4D.h"
#include "Math/VectorUtil.h"
#include "Pythia8/Pythia.h"
#include "TH1D.h"
#include "TH1I.h"

#include <sys/ioctl.h>
#include <unistd.h>

#include "Analysis.hh"
#include "Config.hh"
#include "Record.hh"
#include <toml++/toml.hpp>

namespace Lambda {
    using Lorentz = ROOT::Math::PxPyPzEVector;

    enum class RangeSize : std::size_t { Low, Medium, High };
    enum class Quantity : std::size_t { Mass, Energy, NetMomentum, TransMomentum, AxialMomentum, Eta };
    enum class HistogramSet : std::size_t { Unvalidated, Validated, Selected };

    constexpr std::size_t kQuantityCount     = 6;
    constexpr std::size_t kHistogramSetCount = 3;
    constexpr std::size_t kRangeCount        = 3;
    inline constexpr auto kSlowEventThreshold = std::chrono::seconds(5);

    using RootObjects = Analysis::RootObjects<HistogramSet, kQuantityCount>;
    using RootArray   = std::vector<RootObjects>;

    struct Parameters {
        Double_t lambdaMass          = 1.115;
        Double_t lambdaEnergy        = 1.115;
        Double_t protonMass          = 0.938;
        Double_t pionMass            = 0.140;
        Double_t massDiff            = 0.037;
        Double_t EnergyTolerance     = 0.1;
        Double_t ThetaTolerance      = 0.1;
        Double_t lambdaMomentum      = 1.115;
        Double_t lambdaTransMomentum = 1.0;
        Double_t lambdaAxialMomentum = 1.0;
        Double_t etaExtent           = 5.0;
    };

    struct Bounds {
        Double_t low{};
        Double_t high{};
    };

    struct QuantityAttributes {
        Quantity id{};
        const char* histSuffix{};
        const char* histTitle{};
        std::array<Bounds, kRangeCount> bounds{};

        Bounds range(RangeSize size) const {
            return bounds[static_cast<std::size_t>(size)];
        }
    };

    struct HistogramSetAttributes {
        HistogramSet id{};
        const char* tag{};
        const char* directoryName{};
        std::array<bool, kQuantityCount> enabledQuantities{};
        std::array<RangeSize, kQuantityCount> quantityRanges{};

        bool includes(Quantity quantity) const {
            return enabledQuantities[static_cast<std::size_t>(quantity)];
        }

        RangeSize rangeFor(Quantity quantity) const {
            return quantityRanges[static_cast<std::size_t>(quantity)];
        }
    };

    static constexpr std::array<HistogramSetAttributes, kHistogramSetCount> kHistogramSetMap{{
        {HistogramSet::Unvalidated, "Unvalidated", "Unvalidated",
            {true, true, true, true, true, true},
            {RangeSize::High, RangeSize::High, RangeSize::High, RangeSize::High, RangeSize::High, RangeSize::High}},
        {HistogramSet::Validated, "Validated", "Validated",
            {true, true, true, true, true, true},
            {RangeSize::Low, RangeSize::Low, RangeSize::Low, RangeSize::Low, RangeSize::Low, RangeSize::Low}},
        {HistogramSet::Selected, "Selected", "Selected",
            {true, true, true, true, true, true},
            {RangeSize::Low, RangeSize::Low, RangeSize::Low, RangeSize::Low, RangeSize::Low, RangeSize::Low}}
    }};

    inline std::array<QuantityAttributes, kQuantityCount> makeQuantityMap(const Parameters& parameters) {
        return {{
            {Quantity::Mass, "Mass_Hist", "Mass Distribution of Reconstructed Lambda-particles",
                {{{parameters.lambdaMass * 0.89, parameters.lambdaMass * 1.10},
                  {parameters.lambdaMass * 0.80, parameters.lambdaMass * 1.25},
                  {parameters.lambdaMass * 0.25, parameters.lambdaMass * 10.0}}}},
            {Quantity::Energy, "Energy_Hist", "Energy Distribution of Reconstructed Lambda-particles",
                {{{parameters.lambdaEnergy * 0.89, parameters.lambdaEnergy * 1.20},
                  {parameters.lambdaEnergy * 0.89, parameters.lambdaEnergy * 1.80},
                  {parameters.lambdaEnergy * 0.89, parameters.lambdaEnergy * 10.0}}}},
            {Quantity::NetMomentum, "Total_Momentum_Hist", "Momentum Distribution of Reconstructed Lambda-particles",
                {{{0.0, parameters.lambdaMomentum * 0.8},
                  {0.0, parameters.lambdaMomentum * 1.5},
                  {0.0, parameters.lambdaMomentum * 10.0}}}},
            {Quantity::TransMomentum, "Transverse_Momentum_Hist", "Transverse Momentum Distribution of Reconstructed Lambda-particles",
                {{{0.0, parameters.lambdaTransMomentum * 0.8},
                  {0.0, parameters.lambdaTransMomentum * 1.3},
                  {0.0, parameters.lambdaTransMomentum * 4.0}}}},
            {Quantity::AxialMomentum, "Axial_Momentum_Hist", "Axial Momentum Distribution of Reconstructed Lambda-particles",
                {{{parameters.lambdaAxialMomentum * -0.8, parameters.lambdaAxialMomentum * 0.8},
                  {parameters.lambdaAxialMomentum * -1.3, parameters.lambdaAxialMomentum * 1.3},
                  {parameters.lambdaAxialMomentum * -4.0, parameters.lambdaAxialMomentum * 4.0}}}},
            {Quantity::Eta, "Eta_Hist", "Eta Distribution of Reconstructed Lambda-particles",
                {{{-parameters.etaExtent, parameters.etaExtent},
                  {-2.0 * parameters.etaExtent, 2.0 * parameters.etaExtent},
                  {-4.0 * parameters.etaExtent, 4.0 * parameters.etaExtent}}}}
        }};
    }

    inline Double_t valueOf(const Lorentz& particle, Quantity quantity) {
        switch (quantity) {
            case Quantity::Mass:          return particle.M();
            case Quantity::Energy:        return particle.E();
            case Quantity::NetMomentum:   return particle.P();
            case Quantity::TransMomentum: return particle.Pt();
            case Quantity::AxialMomentum: return particle.Pz();
            case Quantity::Eta:           return particle.Eta();
        }

        throw std::out_of_range("unknown quantity");
    }

    inline Double_t openingCosTheta(const Lorentz& proton, const Lorentz& pion, const Lorentz& lambda) {
        namespace VectorUtil = ROOT::Math::VectorUtil;

        const auto beta     = lambda.BoostToCM();
        const auto protonCM = VectorUtil::boost(proton, beta);
        const auto pionCM   = VectorUtil::boost(pion, beta);

        return
            (protonCM.Px() * pionCM.Px() +
             protonCM.Py() * pionCM.Py() +
             protonCM.Pz() * pionCM.Pz()) /
            (protonCM.P() * pionCM.P());
    }

    inline bool energyAccepted(const Lorentz& lambda, const Parameters& parameters) {
        return
            (lambda.E() > (parameters.lambdaMass - parameters.EnergyTolerance)) &&
            (lambda.E() < (parameters.lambdaMass + parameters.EnergyTolerance));
    }

    inline bool thetaAccepted(Double_t theta, const Parameters& parameters) {
        return
            (theta > (-1 - std::cos(parameters.ThetaTolerance))) &&
            (theta < (-1 + std::cos(parameters.ThetaTolerance)));
    }

    inline void declareObjects(
        RootArray& objects,
        const Parameters& parameters,
        Config::Root& root
    );
    inline RootObjects* find(RootArray& objects, HistogramSet set);
    inline void fill(RootObjects& object, const Lorentz& particle);
    inline void fill(RootArray& objects, HistogramSet set, const Lorentz& particle);
    inline void pythiaAnalysis(
        Pythia8::Pythia& pythia,
        RootArray& histogramSets,
        const Parameters& parameters,
        Config::Root& root,
        Config::Log& logging,
        Record::AsyncLogger& asyncLogger
    );
    inline std::string logString(const Parameters& parameters);

    inline void declareObjects(
        RootArray& objects,
        const Parameters& parameters,
        Config::Root& root
    ) {
        if (root.outFile == nullptr) {
            throw std::invalid_argument("root.outFile must not be null");
        }

        const auto quantityMap = Lambda::makeQuantityMap(parameters);
        objects.clear();
        objects.reserve(Lambda::kHistogramSetCount);

        for (const auto& histogramSet : Lambda::kHistogramSetMap) {
            RootObjects object{};
            object.basis = histogramSet.id;
            object.dir   = root.outFile->mkdir(histogramSet.directoryName);
            object.count = new TH1I(
                (std::string(histogramSet.tag) + "CountHist").c_str(),
                "Count of Reconstructed Candidates",
                41,
                -0.5,
                40.5
            );

            for (const auto& quantity : quantityMap) {
                if (!histogramSet.includes(quantity.id)) {
                    continue;
                }

                const Lambda::Bounds range = quantity.range(histogramSet.rangeFor(quantity.id));
                const std::string histName = std::string(histogramSet.tag) + "_" + quantity.histSuffix;

                object.hists[Analysis::toIndex(quantity.id)] = new TH1D(
                    histName.c_str(),
                    quantity.histTitle,
                    root.binCount,
                    range.low,
                    range.high
                );
            }

            objects.push_back(object);
        }
    }

    inline RootObjects* find(RootArray& objects, HistogramSet set) {
        for (auto& object : objects) {
            if (object.basis == set) {
                return &object;
            }
        }

        return nullptr;
    }

    inline void fill(RootObjects& object, const Lorentz& particle) {
        ++object.validatedCount;

        for (std::size_t i = 0; i < Lambda::kQuantityCount; ++i) {
            TH1D* hist = object.hists[i];
            if (hist != nullptr) {
                hist->Fill(Lambda::valueOf(particle, static_cast<Lambda::Quantity>(i)));
            }
        }
    }

    inline void fill(RootArray& objects, HistogramSet set, const Lorentz& particle) {
        if (RootObjects* object = find(objects, set)) {
            fill(*object, particle);
        }
    }

    inline void pythiaAnalysis(
        Pythia8::Pythia&     pythia,
                 RootArray&  histogramSets,
        const    Parameters& parameters,
        Config::Root&        root,
        Config:: Log&        logging,
        Record::AsyncLogger& asyncLogger
    ) {
        const std::size_t eventIndex = ++logging.iEvent;
        ++logging.nRealEvents;
        const int workerIndex = pythia.mode("Parallelism:index");

        Lorentz lambda, proton, pion;
        std::vector<Lorentz> protonList, pionList;

        protonList.reserve(pythia.event.size());
        pionList.reserve(pythia.event.size());

        std::size_t particle, iProton, iPion;

        if (eventIndex == 1) {
            std::lock_guard<std::mutex> terminalLock(Record::terminalMutex());
            pythia.info.list();
            asyncLogger.makeSpace();
        }

        for (particle = 0; particle < pythia.event. size(); ++particle) {
            const auto& eventParticle = pythia.event[particle];

            if (eventParticle.id() == 2212) {
                protonList.emplace_back(
                    eventParticle.px(),
                    eventParticle.py(),
                    eventParticle.pz(),
                    eventParticle.e()
                );
            } else if (eventParticle.id() == -211) {
                pionList.emplace_back(
                    eventParticle.px(),
                    eventParticle.py(),
                    eventParticle.pz(),
                    eventParticle.e()
                );
            }
        }

        Analysis::resetAllCounts(histogramSets);

        std::vector<char> pionTaken(pionList.size(), 0);
        logging.elapsed = std::chrono::duration_cast<Config::uSeconds>(std::chrono::system_clock::now() - logging.start);
        
        asyncLogger.publishThreadStats(
            workerIndex,
            Record::ThreadPhase::Analysis,
            eventIndex,
            Record::NoCallbackCompleted,
            Record::HasParticleCounts,
            protonList.size(),
            pionList.size()
        );

        for (iProton = 0; iProton < protonList.size(); ++iProton) {
            Bool_t   hasCandidate   = false;
            std::size_t   bestPionIndex  = 0;
            Double_t leastMassDelta = 0.0;
            Lorentz  bestLambda;

            proton = protonList[iProton];

            for (iPion = 0; iPion < pionList.size(); ++iPion) {

                if (pionTaken[iPion] != 0) {
                    continue;
                }

                pion   = pionList[iPion];
                lambda = proton + pion;

                fill(histogramSets, HistogramSet::Unvalidated, lambda);

                const Double_t theta = Lambda::openingCosTheta(proton, pion, lambda);
                const Bool_t   energyCheck = Lambda::energyAccepted(lambda, parameters);
                const Bool_t   thetaCheck  = Lambda::thetaAccepted(theta, parameters);

                if (!(energyCheck && thetaCheck)) {
                    continue;
                }

                fill(histogramSets, HistogramSet::Validated, lambda);

                const Double_t currentMassDelta = std::abs(lambda.M() - parameters.lambdaMass);

                if (!hasCandidate || currentMassDelta < leastMassDelta) {
                    hasCandidate   = true;
                    leastMassDelta = currentMassDelta;
                    bestPionIndex  = iPion;
                    bestLambda     = lambda;
                }
            }

            if (!hasCandidate) {
                continue;
            }

            pionTaken[bestPionIndex] = 1;

            fill(histogramSets, HistogramSet::Selected, bestLambda);
        }

        Analysis::countAll(histogramSets);
        logging.elapsed = std::chrono::duration_cast<Config::uSeconds>(std::chrono::system_clock::now() - logging.start);

        const bool shouldRenderStatus = (eventIndex % logging.printInterval == 0) || (eventIndex == 1) || (eventIndex == logging.nEvents);
        const bool shouldRenderBar = (eventIndex % logging.barInterval == 0)  || (eventIndex == 1) || (eventIndex == logging.nEvents);

        asyncLogger.publish(
            logging,
            Record::RunPhase::Analysis,
            eventIndex,
            shouldRenderStatus,
            shouldRenderBar,
            Record::DontWriteRunStat,
            Record::HasParticleCounts,
            protonList.size(),
            pionList.size()
        );

        if (logging.checkInterval > 0 && eventIndex % logging.checkInterval == 0) {
            logging.elapsed = std::chrono::duration_cast<Config::uSeconds>(std::chrono::system_clock::now() - logging.start);
            Analysis::checkpointWrite(histogramSets, root.checkpointOutName, root.histScale, eventIndex);

            logging.elapsed =
                std::chrono::duration_cast<Config::uSeconds>(std::chrono::system_clock::now() - logging.start);
            Record::outputLog(pythia, root, logging, logString(parameters), root.checkpointLogName);
        }


        asyncLogger.publishThreadStats(
            workerIndex,
            Record::ThreadPhase::Simulation,
            eventIndex,
            Record::CallbackCompleted
        );
    }

    inline void extractPhysics(
        const std::string& configPath,
        Parameters& parameters
    ) {
        toml::table config = toml::parse_file(configPath);
        parameters.EnergyTolerance = config["physics"]["delta_energy_gev"].value_or(0.1);
        parameters.ThetaTolerance  = config["physics"]["delta_theta_rad"].value_or(0.1);
    }

    inline std::string logString(const Parameters& parameters) {
        std::ostringstream stream;

        stream << "Lambda Mass                   : " << parameters.lambdaMass << '\n';
        stream << "Lambda Energy                 : " << parameters.lambdaEnergy << '\n';
        stream << "Proton Mass                   : " << parameters.protonMass << '\n';
        stream << "Pion Mass                     : " << parameters.pionMass << '\n';
        stream << "Mass Difference               : " << parameters.massDiff << '\n';
        stream << "Energy Tolerance              : " << parameters.EnergyTolerance << '\n';
        stream << "Theta Tolerance               : " << parameters.ThetaTolerance << '\n';
        stream << "Lambda Momentum               : " << parameters.lambdaMomentum << '\n';
        stream << "Lambda Transverse Momentum    : " << parameters.lambdaTransMomentum << '\n';
        stream << "Eta Extent                    : " << parameters.etaExtent << '\n';

        return stream.str();
    }
}
