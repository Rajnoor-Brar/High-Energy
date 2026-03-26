#pragma once

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <iostream>
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
#include </opt/homebrew/Cellar/tomlplusplus/3.4.0/include/toml++/toml.hpp>

namespace Lambda {
    using Lorentz = ROOT::Math::PxPyPzEVector;

    enum class RangeSize : std::size_t { Low, Medium, High };
    enum class Quantity : std::size_t { Mass, Energy, NetMomentum, TransMomentum, Eta };
    enum class ValidationBasis : std::size_t { Un, Mass, Energy, Theta, EnergyMass, EnergyTheta, MassTheta, All };

    constexpr std::size_t kQuantityCount   = 5;
    constexpr std::size_t kValidationCount = 8;
    constexpr std::size_t kRangeCount      = 3;

    using RootObjects = Analysis::RootObjects<ValidationBasis, kQuantityCount>;
    using RootArray   = std::vector<RootObjects>;

    struct Parameters {
        Double_t lambdaMass          = 1.115;
        Double_t lambdaEnergy        = 1.115;
        Double_t protonMass          = 0.938;
        Double_t pionMass            = 0.140;
        Double_t massDiff            = 0.037;
        Double_t EnergyTolerance     = 0.1;
        Double_t MassTolerance       = 0.05;
        Double_t ThetaTolerance      = 0.1;
        Double_t lambdaMomentum      = 1.115;
        Double_t lambdaTransMomentum = 1.0;
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

    struct ValidationAttributes {
        ValidationBasis id{};
        const char* tag{};
        const char* titlePrefix{};
        std::array<RangeSize, kQuantityCount> quantityRanges{};

        RangeSize rangeFor(Quantity quantity) const {
            return quantityRanges[static_cast<std::size_t>(quantity)];
        }
    };

    struct SkipList {
        std::vector<ValidationBasis> validationSkips;
        std::vector<Quantity> quantitySkips;
    };

    static constexpr std::array<ValidationAttributes, kValidationCount> kValidationMap{{
        {ValidationBasis::Un,          "un",          "un",           {RangeSize::High, RangeSize::High,   RangeSize::High,   RangeSize::High,   RangeSize::High}},
        {ValidationBasis::Mass,        "Mass",        "Mass",         {RangeSize::Low,  RangeSize::High,   RangeSize::High,   RangeSize::High,   RangeSize::Medium}},
        {ValidationBasis::Energy,      "Energy",      "Energy",       {RangeSize::Low,  RangeSize::Low,    RangeSize::Low,    RangeSize::Low,    RangeSize::Low}},
        {ValidationBasis::Theta,       "Theta",       "Theta",        {RangeSize::High, RangeSize::High,   RangeSize::High,   RangeSize::High,   RangeSize::High}},
        {ValidationBasis::EnergyMass,  "EnergyMass",  "Energy-Mass",  {RangeSize::Low,  RangeSize::Low,    RangeSize::Low,    RangeSize::Low,    RangeSize::Low}},
        {ValidationBasis::EnergyTheta, "EnergyTheta", "Energy-Theta", {RangeSize::Low,  RangeSize::Low,    RangeSize::Low,    RangeSize::Low,    RangeSize::Low}},
        {ValidationBasis::MassTheta,   "MassTheta",   "Mass-Theta",   {RangeSize::Low,  RangeSize::Medium, RangeSize::Medium, RangeSize::Medium, RangeSize::Low}},
        {ValidationBasis::All,         "All",         "All",          {RangeSize::Low,  RangeSize::Low,    RangeSize::Low,    RangeSize::Low,    RangeSize::Low}}
    }};

    inline const ValidationAttributes& validationAttr(ValidationBasis basis) {
        return kValidationMap[static_cast<std::size_t>(basis)];
    }

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
                {{{0.0, parameters.lambdaTransMomentum * 0.6},
                  {0.0, parameters.lambdaTransMomentum * 1.3},
                  {0.0, parameters.lambdaTransMomentum * 3.0}}}},
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

    inline bool massAccepted(const Lorentz& lambda, const Parameters& parameters) {
        return
            (lambda.M() > (parameters.lambdaMass - parameters.MassTolerance)) &&
            (lambda.M() < (parameters.lambdaMass + parameters.MassTolerance));
    }

    inline bool thetaAccepted(Double_t theta, const Parameters& parameters) {
        return
            (theta > (-1 - std::cos(parameters.ThetaTolerance))) &&
            (theta < (-1 + std::cos(parameters.ThetaTolerance)));
    }

    inline bool isSkipped(const SkipList& skips, ValidationBasis basis);
    inline bool isSkipped(const SkipList& skips, Quantity quantity);
    inline void declareObjects(
        RootArray& objects,
        const Parameters& parameters,
        Config::Root& root,
        const SkipList& skips
    );
    inline RootObjects* find(RootArray& objects, ValidationBasis basis);
    inline void fill(RootObjects& object, const Lorentz& particle);
    inline void fill(RootArray& objects, ValidationBasis basis, const Lorentz& particle);
    inline void pythiaAnalysis(
        Pythia8::Pythia& pythia,
        RootArray& validated,
        const Parameters& parameters,
        Config::Log& logging
    );

    inline bool isSkipped(const SkipList& skips, ValidationBasis basis) {
        return std::find(skips.validationSkips.begin(), skips.validationSkips.end(), basis) != skips.validationSkips.end();
    }

    inline bool isSkipped(const SkipList& skips, Quantity quantity) {
        return std::find(skips.quantitySkips.begin(), skips.quantitySkips.end(), quantity) != skips.quantitySkips.end();
    }

    inline void declareObjects(
        RootArray& objects,
        const Parameters& parameters,
        Config::Root& root,
        const SkipList& skips
    ) {
        if (root.outFile == nullptr) {
            throw std::invalid_argument("root.outFile must not be null");
        }

        const auto quantityMap = Lambda::makeQuantityMap(parameters);
        objects.clear();
        objects.reserve(Lambda::kValidationCount);

        for (const auto& validation : Lambda::kValidationMap) {
            if (isSkipped(skips, validation.id)) {
                continue;
            }

            RootObjects object{};
            object.basis = validation.id;
            object.dir   = root.outFile->mkdir((std::string(validation.titlePrefix) + "Validated").c_str());
            object.count = new TH1I(
                (std::string(validation.tag) + "CountHist").c_str(),
                "Count of Reconstructed Candidates",
                41,
                -0.5,
                40.5
            );

            for (const auto& quantity : quantityMap) {
                if (isSkipped(skips, quantity.id)) {
                    continue;
                }

                const Lambda::Bounds range = quantity.range(validation.rangeFor(quantity.id));
                const std::string histName = std::string(validation.tag) + "Validated_" + quantity.histSuffix;

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

    inline RootObjects* find(RootArray& objects, ValidationBasis basis) {
        for (auto& object : objects) {
            if (object.basis == basis) {
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

    inline void fill(RootArray& objects, ValidationBasis basis, const Lorentz& particle) {
        if (RootObjects* object = find(objects, basis)) {
            fill(*object, particle);
        }
    }

    inline void pythiaAnalysis(
        Pythia8::Pythia& pythia,
        RootArray& validated,
        const Parameters& parameters,
        Config::Log& logging
    ) {
        const Int_t eventIndex = ++logging.iEvent;
        ++logging.nRealEvents;

        static int wsCol = [] {
            struct winsize windowSize{};
            ioctl(STDOUT_FILENO, TIOCGWINSZ, &windowSize);
            return static_cast<int>(windowSize.ws_col);
        }();

        const Int_t progressGap = std::max<Int_t>(1, logging.nEvents / std::max(1, wsCol - 6));

        Lorentz lambda;
        Lorentz proton;
        Lorentz pion;
        std::vector<Lorentz> protonList;
        std::vector<Lorentz> pionList;

        protonList.reserve(pythia.event.size());
        pionList.reserve(pythia.event.size());

        if (eventIndex == 1) {
            pythia.info.list();
            std::cout << std::flush;
        }

        if (eventIndex == 2) {
            std::cout << "\n\n\n";
            logging.elapsed = std::chrono::duration_cast<Config::uSeconds>(std::chrono::system_clock::now() - logging.start);
            Record::printProgressStat(
                2,
                logging.nEvents,
                logging.nDigits,
                Record::updatedETA(2, logging.nEvents, logging.elapsed)
            );
            Record::printProgressBar(0.01);
        }

        for (Int_t particle = 0; particle < pythia.event.size(); ++particle) {
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

        if (eventIndex % logging.printInterval == 0 || eventIndex == logging.nEvents) {
            logging.elapsed = std::chrono::duration_cast<Config::uSeconds>(std::chrono::system_clock::now() - logging.start);
            Record::printProgressStat(
                eventIndex,
                logging.nEvents,
                logging.nDigits,
                Record::updatedETA(eventIndex, logging.nEvents, logging.elapsed)
            );
        }

        if (eventIndex % progressGap == 0 || eventIndex == logging.nEvents) {
            Record::printProgressBar(static_cast<double>(eventIndex) / logging.nEvents);
            logging.barInterval = progressGap;
        }

        Analysis::resetAllCounts(validated);

        for (Int_t iProton = 0; iProton < static_cast<Int_t>(protonList.size()); ++iProton) {
            for (Int_t iPion = 0; iPion < static_cast<Int_t>(pionList.size()); ++iPion) {
                proton = protonList[iProton];
                pion   = pionList[iPion];
                lambda = proton + pion;

                fill(validated, ValidationBasis::Un, lambda);

                const Double_t theta       = Lambda::openingCosTheta(proton, pion, lambda);
                const Bool_t   massCheck   = Lambda::massAccepted(lambda, parameters);
                const Bool_t   energyCheck = Lambda::energyAccepted(lambda, parameters);
                const Bool_t   thetaCheck  = Lambda::thetaAccepted(theta, parameters);

                if (massCheck) {
                    fill(validated, ValidationBasis::Mass, lambda);
                }
                if (energyCheck) {
                    fill(validated, ValidationBasis::Energy, lambda);
                }
                if (thetaCheck) {
                    fill(validated, ValidationBasis::Theta, lambda);
                }
                if (massCheck && energyCheck) {
                    fill(validated, ValidationBasis::EnergyMass, lambda);
                }
                if (massCheck && thetaCheck) {
                    fill(validated, ValidationBasis::MassTheta, lambda);
                }
                if (energyCheck && thetaCheck) {
                    fill(validated, ValidationBasis::EnergyTheta, lambda);
                }
                if (energyCheck && massCheck && thetaCheck) {
                    fill(validated, ValidationBasis::All, lambda);
                }
            }
        }

        Analysis::countAll(validated);
    }

    inline void extractPhysics( const std::string& project, Parameters& parameters) {
        toml::table config = toml::parse_file("configs/" + project + ".toml");
        parameters.EnergyTolerance = config["physics"]["delta_energy_gev"].value_or(0.1);
        parameters.MassTolerance   = config["physics"]["delta_mass_gev"].value_or(0.1);
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
        stream << "Mass Tolerance                : " << parameters.MassTolerance << '\n';
        stream << "Theta Tolerance               : " << parameters.ThetaTolerance << '\n';
        stream << "Lambda Momentum               : " << parameters.lambdaMomentum << '\n';
        stream << "Lambda Transverse Momentum    : " << parameters.lambdaTransMomentum << '\n';
        stream << "Eta Extent                    : " << parameters.etaExtent << '\n';

        return stream.str();
    }
}
