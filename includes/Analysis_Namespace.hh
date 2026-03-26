#pragma once

#include <array>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <utility>

#include "TDirectory.h"
#include "TFile.h"
#include "TH1.h"
#include "TH1D.h"
#include "TTree.h"
#include "Math/Vector4D.h"

#include "Config_Types.hh"

namespace RootAnalysis {
    using Lorentz  = ROOT::Math::PxPyPzEVector;
    using SysClock = std::chrono::system_clock;
    using uSeconds = std::chrono::microseconds;
    using Seconds  = std::chrono::seconds;
    using Minutes  = std::chrono::minutes;
    using Hours    = std::chrono::hours;
    using String   = std::string;
    using std::to_string;
    namespace Chrono = std::chrono;

    template <typename Enum>
    constexpr std::size_t toIndex(Enum value) {
        return static_cast<std::size_t>(value);
    }

    enum class RangeSize : std::size_t { Low, Medium, High };
    enum class Quantity : std::size_t { Mass, Energy, NetMomentum, TransMomentum, Eta };
    enum class ValidationBasis : std::size_t { Un, Mass, Energy, Theta, EnergyMass, EnergyTheta, MassTheta, All };

    constexpr std::size_t kQuantityCount   = 5;
    constexpr std::size_t kValidationCount = 8;
    constexpr std::size_t kRangeCount      = 3;

    /* Forward declarations */

    struct Bounds;
    struct QuantityAttributes;
    struct ValidationAttributes;
    struct ValidatedObjects;
    struct SkipList;
    using ValidatedArray = std::vector<ValidatedObjects>;
    /* Function declarations */

    std::array<QuantityAttributes, kQuantityCount> makeQuantityMap(const Config::Analysis& analysis);

    const ValidationAttributes&    validationAttr  (      ValidationBasis   basis      );

          bool                     isSkipped       (const SkipList&         skips    ,
                                                          ValidationBasis   basis      );

          bool                     isSkipped       (const SkipList&         skips    ,
                                                          Quantity          quantity   );

          Double_t                 valueOf         (const Lorentz&          particle ,
                                                          Quantity          quantity   );

          void                     declareObjects  (      ValidatedArray&   objects ,
                                                    const Config::Analysis& analysis,
                                                          Config::Root&     root    ,
                                                    const SkipList&         skips      );

          ValidatedObjects*        find            (      ValidatedArray&   objects , 
                                                          ValidationBasis   basis      );

          void                     fill            (      ValidatedObjects& obj     , 
                                                    const Lorentz& particle            );

          void                     fill            (      ValidatedArray&   objects ,
                                                          ValidationBasis   basis   ,
                                                    const Lorentz& particle            );

          void                     count           (      ValidatedObjects& obj        );

          void                     countAll        (      ValidatedArray&   objects    );

          void                     resetCount      (      ValidatedObjects& obj        );

          void                     resetAllCounts  (      ValidatedArray&   objects    );

          void                     scaleAndWrite   (      TH1*              hist    ,
                                                          Double_t          histScale, 
                                                          Int_t             nEvents , 
                                                          bool              width = true);

          void                     write           (      ValidatedObjects& obj     ,
                                                    const Config::Analysis& analysis, 
                                                    const Config::Log&      logging     );

          void                     writeAll        (      ValidatedArray&   objects,
                                                    const Config::Analysis& analysis,
                                                    const Config::Log&      logging     );

    /* Struct definitions */

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
            return bounds[toIndex(size)];
        }
    };

    struct ValidationAttributes {
        ValidationBasis id{};
        const char* tag{};
        const char* titlePrefix{};
        std::array<RangeSize, kQuantityCount> quantityRanges{};

        RangeSize rangeFor(Quantity quantity) const {
            return quantityRanges[toIndex(quantity)];
        }
    };

    struct ValidatedObjects {
        ValidationBasis basis{};
        TDirectory* dir{};
        TH1I* count{};
        Int_t validatedCount{};
        std::array<TH1D*, kQuantityCount> hists{};
    };

    struct SkipList {
        std::vector<ValidationBasis> validationSkips;
        std::vector<Quantity> quantitySkips;
    };

    /* Static data */

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

    /* Function definitions */

    inline const ValidationAttributes& validationAttr(ValidationBasis basis) {
        return kValidationMap[toIndex(basis)];
    }

    inline bool isSkipped(const SkipList& skips, ValidationBasis basis) {
        return std::find(skips.validationSkips.begin(), skips.validationSkips.end(), basis)
            != skips.validationSkips.end();
    }

    inline bool isSkipped(const SkipList& skips, Quantity quantity) {
        return std::find(skips.quantitySkips.begin(), skips.quantitySkips.end(), quantity)
            != skips.quantitySkips.end();
    }

    inline std::array<QuantityAttributes, kQuantityCount>
                        makeQuantityMap(const Config::Analysis& analysis) {
        const Double_t lambdaMomentum      = analysis.lambdaEnergy;
        const Double_t lambdaTransMomentum = 1.0;
        const Double_t etaExtent           = 5.0;

        return {{
            {Quantity::Mass, "Mass_Hist", "Mass Distribution of Reconstructed Lambda-particles",
                {{{analysis.lambdaMass * 0.89, analysis.lambdaMass * 1.10},
                  {analysis.lambdaMass * 0.80, analysis.lambdaMass * 1.25},
                  {analysis.lambdaMass * 0.25, analysis.lambdaMass * 10.0}}}},
            {Quantity::Energy, "Energy_Hist", "Energy Distribution of Reconstructed Lambda-particles",
                {{{analysis.lambdaEnergy * 0.89, analysis.lambdaEnergy * 1.20},
                  {analysis.lambdaEnergy * 0.89, analysis.lambdaEnergy * 1.80},
                  {analysis.lambdaEnergy * 0.89, analysis.lambdaEnergy * 10.0}}}},
            {Quantity::NetMomentum, "Total_Momentum_Hist", "Momentum Distribution of Reconstructed Lambda-particles",
                {{{0.0, lambdaMomentum * 0.8},
                  {0.0, lambdaMomentum * 1.5},
                  {0.0, lambdaMomentum * 10.0}}}},
            {Quantity::TransMomentum, "Transverse_Momentum_Hist", "Transverse Momentum Distribution of Reconstructed Lambda-particles",
                {{{0.0, lambdaTransMomentum * 0.6},
                  {0.0, lambdaTransMomentum * 1.3},
                  {0.0, lambdaTransMomentum * 3.0}}}},
            {Quantity::Eta, "Eta_Hist", "Eta Distribution of Reconstructed Lambda-particles",
                {{{-etaExtent, etaExtent},
                  {-2.0 * etaExtent, 2.0 * etaExtent},
                  {-4.0 * etaExtent, 4.0 * etaExtent}}}}
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

    inline void declareObjects(ValidatedArray& objects,  const Config::Analysis& analysis,  Config::Root& root, const SkipList& skips) {
        if (root.outFile == nullptr) {
            throw std::invalid_argument("root.outFile must not be null");
        }

        const auto quantityMap = makeQuantityMap(analysis);
        objects.clear();
        objects.reserve(kValidationCount);

        for (const auto& validation : kValidationMap) {
            if (isSkipped(skips, validation.id)) {
                continue;
            }

            ValidatedObjects obj{};
            obj.basis = validation.id;
            obj.dir = root.outFile->mkdir((String(validation.titlePrefix) + "Validated").c_str());
            obj.count = new TH1I(
                (String(validation.tag) + "CountHist").c_str(),
                "Count of Reconstructed Lambda-particles",
                41, -0.5, 40.5
            );

            for (const auto& quantity : quantityMap) {
                if (isSkipped(skips, quantity.id)) {
                    continue;
                }

                const Bounds range = quantity.range(validation.rangeFor(quantity.id));
                const String histName = String(validation.tag) + "Validated_" + quantity.histSuffix;

                obj.hists[toIndex(quantity.id)] = new TH1D(
                    histName.c_str(),
                    quantity.histTitle,
                    root.binCount,
                    range.low,
                    range.high
                );
            }

            objects.push_back(obj);
        }
    }

    inline ValidatedObjects* find(ValidatedArray& objects, ValidationBasis basis) {
        for (auto& obj : objects) {
            if (obj.basis == basis) {
                return &obj;
            }
        }
        return nullptr;
    }

    inline void fill(ValidatedObjects& obj, const Lorentz& particle) {
        ++obj.validatedCount;

        for (std::size_t i = 0; i < kQuantityCount; ++i) {
            TH1D* hist = obj.hists[i];
            if (hist != nullptr) {
                hist->Fill(valueOf(particle, static_cast<Quantity>(i)));
            }
        }
    }

    inline void fill(ValidatedArray& objects, ValidationBasis basis, const Lorentz& particle) {
        if (ValidatedObjects* obj = find(objects, basis)) {
            fill(*obj, particle);
        }
    }

    inline void count(ValidatedObjects& obj) {
        if (obj.count != nullptr) {
            obj.count->Fill(obj.validatedCount);
        }
    }

    inline void countAll(ValidatedArray& objects) {
        for (auto& obj : objects) {
            count(obj);
        }
    }

    inline void resetCount(ValidatedObjects& obj) {
        obj.validatedCount = 0;
    }

    inline void resetAllCounts(ValidatedArray& objects) {
        for (auto& obj : objects) {
            resetCount(obj);
        }
    }

    inline void scaleAndWrite(TH1* hist, Double_t histScale, Int_t nEvents, bool width) {
        if (hist == nullptr) {
            return;
        }

        if (nEvents > 0) {
            const Double_t scale = histScale / static_cast<Double_t>(nEvents);
            if (width) hist->Scale(scale, "width");
            else hist->Scale(scale);
        }

        hist->Write();
    }

    inline void write(ValidatedObjects& obj, const Config::Analysis& analysis, const Config::Log& logging) {
        if (obj.dir == nullptr) {
            return;
        }

        obj.dir->cd();
        scaleAndWrite(obj.count, analysis.histScale, logging.nEvents, false);

        for (TH1D* hist : obj.hists) {
            scaleAndWrite(hist, analysis.histScale, logging.nEvents, true);
        }
    }

    inline void writeAll(
        ValidatedArray& objects,
        const Config::Analysis& analysis,
        const Config::Log& logging
    ) {
        for (auto& obj : objects) {
            write(obj, analysis, logging);
        }
    }

} // namespace RootAnalysis
