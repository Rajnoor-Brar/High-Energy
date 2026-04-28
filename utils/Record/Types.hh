#pragma once

#include <cstddef>
#include <memory>
#include <vector>

#include "Config.hh"
#include "Physics.hh"
#include "Record/Extract.hh"
#include "TDirectory.h"
#include "TH1D.h"
#include "TH2.h"
#include "TGraph.h"
#include "TProfile.h"
#include "TTree.h"

namespace Record {

    using Lorentz = Physics::Lorentz;

    struct NoBasis {};

    struct TH1Record {
        TH1D*                    hist{};
        Physics::ParticleProperty property{};
    };
    struct TH2Record {
        TH2*                     hist{};
        Physics::ParticleProperty propertyX{};
        Physics::ParticleProperty propertyY{};
    };
    struct TreeRecord {
        TTree* tree{};
        std::vector<Physics::ParticleProperty>   properties{};
        std::unique_ptr<std::vector<Double_t>>  branchValues{std::make_unique<std::vector<Double_t>>()};
    };
    struct EventTH1Record {
        TH1D*                 hist{};
        Physics::EventProperty property{};
    };
    struct ExtractHist1D {
        TH1D*       hist{};
        Extract::Fn extractor{};
    };
    struct ExtractHist2D {
        TH2*        hist{};
        Extract::Fn extractorX{};
        Extract::Fn extractorY{};
    };

    template <typename Basis = NoBasis>
    struct RootObjects {
        Basis basis{};
        TDirectory* dir{};
        TH1D* count{};
        Int_t candidateCount{};
        std::vector<TH1Record>      hists1D;
        std::vector<EventTH1Record> eventHists1D;
        std::vector<TH2*>           hists2D;
        std::vector<TGraph*>        graphs;
        std::vector<TProfile*>      profiles;
        std::vector<TreeRecord>     trees;
        std::vector<ExtractHist1D>  extractHists1D;
        std::vector<ExtractHist2D>  extractHists2D;
    };

    template <typename Basis = NoBasis>
    using RootArray = std::vector<RootObjects<Basis>>;
}
