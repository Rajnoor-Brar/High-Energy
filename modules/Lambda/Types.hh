#pragma once

#include "TTree.h"
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

    using RootObjects = Record::RootObjects<HistogramSet>;
    using RootArray   = std::vector<RootObjects>;
    using SpecsArray  = std::vector<Probe::CollectionSpec>;

    struct Candidates {
        std::vector<Lorentz> unvalidated;
        std::vector<Lorentz> validated;
        std::vector<Lorentz> selected;
    };

    struct InputConfig {
        string indexBranch = "Index";
        string energy      = "Energy";
        string px          = "pX";
        string py          = "pY";
        string pz          = "pZ";
        std::map<string, string> treeNames;
    };

    struct CandidateConfig {
        string label;
        bool        enabled   = true;
        bool        writeTree = true;
        int         pidAbs    = 0;
    };

    struct Parameters {
        Double_t    massTolerance     = 0.1;
        Double_t    thetaTolerance    = 0.1; // retained for config/log visibility; cuts use cosThetaTolerance
        Double_t    cosThetaTolerance = 0.0;
        std::size_t reservedProtons   = 20;   // baseline beam protons per event (e.g. 2 × Z for symmetric A–A)
        std::map<HistogramSet, std::map<Physics::ParticleProperty, Config::Bounds>> setParticleLimits;
        std::map<HistogramSet, std::map<Physics::EventProperty,    Config::Bounds>> setEventLimits;
        InputConfig input;
        std::vector<CandidateConfig> candidates = {
            {"Protons", true, true, 2212},
            {"Pions",   true, true, -211}
        };
    };

    struct HistogramSetAttributes {
        HistogramSet id{};
        const char* tag{};
        const char* directoryName{};
    };

    struct DataObjects {
        TTree* protons{};
        TTree* pions{};
        // unique_ptr keeps branch addresses stable when DataObjects is moved
        std::unique_ptr<std::array<Double_t, 4>> protonBranches{
            std::make_unique<std::array<Double_t, 4>>()};
        std::unique_ptr<std::array<Double_t, 4>> pionBranches{
            std::make_unique<std::array<Double_t, 4>>()};
        std::unique_ptr<Int_t> protonEventIndex{std::make_unique<Int_t>(0)};
        std::unique_ptr<Int_t> pionEventIndex{std::make_unique<Int_t>(0)};
    };
}
