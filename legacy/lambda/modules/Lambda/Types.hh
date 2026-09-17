#pragma once

#include "Record.hh"

namespace Lambda{
    inline constexpr Double_t kLambdaMass = 1.115;
    inline constexpr Double_t kProtonMass = 0.938;
    inline constexpr Double_t kPionMass   = 0.140;
    inline constexpr Double_t kMassDiff   = 0.037;

    inline constexpr int ProtonPid = 2212;
    inline constexpr int PionPid   = -211;

    enum class HistogramSet : std::size_t { Unvalidated, Validated, Selected };
    constexpr std::size_t kHistogramSetCount = 3;

    using std::string;
    using Physics::Lorentz;

    enum class DataTree : std::size_t { Protons, Pions };
    enum class DataBranch : std::size_t { EventIndex, Energy, Px, Py, Pz };

    struct Candidates {
        std::vector<Lorentz> unvalidated;
        std::vector<Lorentz> validated;
        std::vector<Lorentz> selected;
    };

    struct Parameters {
        Double_t    massTolerance     = 0.1;
        Double_t    thetaTolerance    = 0.1; // retained for config/log visibility; cuts use cosThetaTolerance
        Double_t    cosThetaTolerance = 0.0;
        std::size_t reservedProtons   = 20;   // baseline beam protons per event (e.g. 2 × Z for symmetric A–A)
        std::map<HistogramSet, std::map<Physics::ParticleProperty, Config::Bounds>> setParticleLimits;
        std::map<HistogramSet, std::map<Physics::EventProperty,    Config::Bounds>> setEventLimits;
        std::string protonLabel = "Protons";
        std::string pionLabel   = "Pions";
        std::vector<HistogramSet> writeTree; // sets for which a candidate TTree is declared
    };

    struct HistogramSetAttributes {
        HistogramSet id{};
        const char* tag{};
        const char* directoryName{};
    };

}
