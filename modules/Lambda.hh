#pragma once

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <map>

#include "Pythia8/Pythia.h"
#include "Math/VectorUtil.h"

#include "Config.hh"
#include "Explore.hh"
#include "Record.hh"
#include "Monitor.hh"
#include <toml++/toml.hpp>

namespace Lambda {
    using Lorentz = Record::Lorentz;

    enum class HistogramSet : std::size_t { Unvalidated, Validated, Selected };

    constexpr std::size_t kHistogramSetCount = 3;

    using RootObjects = Record::RootObjects<HistogramSet>;
    using RootArray   = std::vector<RootObjects>;

    struct DataObjects {
        TTree* protons{};
        TTree* pions{};
        // unique_ptr keeps branch addresses stable when DataObjects is moved
        std::unique_ptr<std::array<Double_t, 4>> protonBranches{std::make_unique<std::array<Double_t, 4>>()};
        std::unique_ptr<std::array<Double_t, 4>> pionBranches{std::make_unique<std::array<Double_t, 4>>()};
        std::unique_ptr<Int_t> protonEventIndex{std::make_unique<Int_t>(0)};
        std::unique_ptr<Int_t> pionEventIndex{std::make_unique<Int_t>(0)};
    };

    inline void declareDataObjects(DataObjects& data, Config::Root& root) {
        if (root.outFile == nullptr)
            throw std::invalid_argument("root.outFile must not be null");

        root.outFile->cd();
        data.protons = new TTree("Protons", "Final state protons");
        data.pions   = new TTree("Pions",   "Final state #pi^{-}");

        auto declareBranches = [](TTree* tree, std::array<Double_t, 4>& b, Int_t& idx) {
            tree->Branch("event_index", &idx, "event_index/I");
            tree->Branch("Energy",      &b[0], "Energy/D");
            tree->Branch("pX",          &b[1], "pX/D");
            tree->Branch("pY",          &b[2], "pY/D");
            tree->Branch("pZ",          &b[3], "pZ/D");
        };
        declareBranches(data.protons, *data.protonBranches, *data.protonEventIndex);
        declareBranches(data.pions,   *data.pionBranches,   *data.pionEventIndex);
    }

    inline constexpr Double_t kLambdaMass = 1.115;
    inline constexpr Double_t kProtonMass = 0.938;
    inline constexpr Double_t kPionMass   = 0.140;
    inline constexpr Double_t kMassDiff   = 0.037;

    struct Parameters {
        Double_t massTolerance       = 0.1;
        Double_t ThetaTolerance      = 0.1;
        Double_t cosThetaTolerance   = 0.0;
        std::map<HistogramSet, std::map<Config::Quantity, Config::Bounds>> setLimits;
    };

    inline constexpr std::array<Config::Quantity, 6> Recorded_Quantities = {
        Config::Quantity::Mass_Invariant,
        Config::Quantity::Energy_Net,
        Config::Quantity::Momentum_Net,
        Config::Quantity::Momentum_Transverse,
        Config::Quantity::Momentum_Z,
        Config::Quantity::Pseudorapidity
    };

    inline constexpr std::array<HistogramSet, 1> kTreeEnabledSets = {
        HistogramSet::Selected
    };

    struct HistogramSetAttributes {
        HistogramSet id{};
        const char* tag{};
        const char* directoryName{};
    };

    static constexpr std::array<HistogramSetAttributes, kHistogramSetCount> kHistogramSetMap{{
        {HistogramSet::Unvalidated, "Unvalidated", "Unvalidated"},
        {HistogramSet::Validated, "Validated", "Validated"},
        {HistogramSet::Selected, "Selected", "Selected"}
    }};

    inline bool hasTree(HistogramSet set) {
        return std::find(kTreeEnabledSets.begin(), kTreeEnabledSets.end(), set) != kTreeEnabledSets.end();
    }

    inline std::string quantityAlias(Config::Quantity quantity) {
        switch (quantity) {
            case Config::Quantity::Mass_Invariant: return "Mass";
            case Config::Quantity::Energy_Net:     return "Energy";
            default:                               return Analysis::quantityName(quantity);
        }
    }

    inline const char* levelName(Config::RangeSize level) {
        switch (level) {
            case Config::RangeSize::Minute:   return "Minute";
            case Config::RangeSize::Small:    return "Small";
            case Config::RangeSize::Moderate: return "Moderate";
            case Config::RangeSize::Large:    return "Large";
            case Config::RangeSize::Extreme:  return "Extreme";
        }

        return "Unknown";
    }

    inline const Config::Bounds& levelBounds(const Config::Root& root, Config::Quantity quantity, Config::RangeSize level) {
        const auto quantityIt = root.limits.find(quantity);
        if (quantityIt == root.limits.end()) {
            throw std::runtime_error("No configured limits available for quantity " + Analysis::quantityName(quantity));
        }

        const auto levelIt = quantityIt->second.find(level);
        if (levelIt == quantityIt->second.end()) {
            throw std::runtime_error(
                "No configured " + std::string(quantityAlias(quantity)) + " limit for level " + levelName(level)
            );
        }

        return levelIt->second;
    }

    inline std::optional<Config::Bounds> boundsFromValue(const toml::node& node) {
        if (!node.is_array()) return std::nullopt;
        const toml::array& array = *node.as_array();
        if (array.size() != 2) {
            throw std::runtime_error("Expected exactly 2 numeric values in explicit histogram bounds");
        }

        const auto low = array[0].value<Double_t>();
        const auto high = array[1].value<Double_t>();
        if (!low || !high) {
            throw std::runtime_error("Expected numeric histogram bounds");
        }

        return Config::Bounds{*low, *high};
    }

    inline std::optional<Config::Bounds> boundsFromValue(const toml::node& node, const Config::Root& root, Config::Quantity quantity) {
        if (const auto explicitBounds = boundsFromValue(node)) return explicitBounds;
        if (!node.is_string()) return std::nullopt;
        return levelBounds(root, quantity, Config::stringToLevel(node.value<std::string>().value_or("")));
    }

    inline std::string logString(const Parameters& parameters);

    inline Double_t cosTheta(const Lorentz& proton, const Lorentz& pion, const Lorentz& lambda) {
        namespace VectorUtil = ROOT::Math::VectorUtil;
        const auto beta     = lambda.BoostToCM();
        const auto protonCM = VectorUtil::boost(proton, beta);
        const auto pionCM   = VectorUtil::boost(pion, beta);
        return (protonCM.Px() * pionCM.Px() + protonCM.Py() * pionCM.Py() + protonCM.Pz() * pionCM.Pz()) / (protonCM.P() * pionCM.P());
    }

    inline bool massAccepted(const Lorentz& lambda, const Parameters& parameters) {
        return (lambda.M() > (kLambdaMass - parameters.massTolerance)) && (lambda.M() < (kLambdaMass + parameters.massTolerance));
    }

    inline bool thetaAccepted(Double_t theta, const Parameters& parameters) {
        return (theta > (-1 - parameters.cosThetaTolerance)) && (theta < (-1 + parameters.cosThetaTolerance));
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

            if (!parameters.setLimits.count(histogramSet.id) || !parameters.setLimits.at(histogramSet.id).count(Config::Quantity::Multiplicity)) {
                throw std::runtime_error("No Multiplicity limit defined for set " + std::string(histogramSet.tag) );
            }

            const Config::Bounds mBounds = parameters.setLimits.at(histogramSet.id).at(Config::Quantity::Multiplicity);

            object.count = new TH1D(
                (std::string(histogramSet.tag) + "CountHist").c_str(),
                "Count of Reconstructed Candidates",
                static_cast<int>(mBounds.high - mBounds.low + 1),
                mBounds.low - 0.5,
                mBounds.high + 0.5
            );

            for (const auto& quantity : Recorded_Quantities) {
                if (!parameters.setLimits.count(histogramSet.id) ||
                    !parameters.setLimits.at(histogramSet.id).count(quantity)) {
                    throw std::runtime_error(
                        "No limit defined for set " + std::string(histogramSet.tag) + " and quantity " + Analysis::quantityName(quantity)
                    );
                }

                const Config::Bounds bounds = parameters.setLimits.at(histogramSet.id).at(quantity);
                const std::string quantityName = Analysis::quantityName(quantity);
                const std::string histName = std::string(histogramSet.tag) + "_" + quantityName + "_Hist";

                object.hists1D.push_back(
                    Record::TH1Record{
                        new TH1D(
                            histName.c_str(),
                            (quantityName + " Distribution").c_str(),
                            root.binCount,
                            bounds.low,
                            bounds.high
                        ),
                        quantity
                    }
                );
            }

            if (hasTree(histogramSet.id)) {
                const std::string treeName = std::string(histogramSet.tag) + "_Candidates";
                object.trees.push_back(
                    Record::declareTree(
                        object.dir,
                        treeName,
                        std::string(histogramSet.tag) + " candidate quantities",
                        Recorded_Quantities
                    )
                );
            }

            objects.push_back(std::move(object));
        }
    }

    inline RootObjects* find(RootArray& objects, HistogramSet set) {
        static_assert(static_cast<std::size_t>(HistogramSet::Selected) == kHistogramSetCount - 1, "Enum out of sync");
        std::size_t index = static_cast<std::size_t>(set);
        if (index < objects.size() && objects[index].basis == set) return &objects[index];
        return nullptr;
    }

    inline void fill(RootObjects& object, const Lorentz& particle) {
        ++object.candidateCount;
        for (auto& hist : object.hists1D) Record::fill(hist, particle);
        for (auto& tree : object.trees) Record::fill(tree, particle);
    }

    inline void fill(RootArray& objects, HistogramSet set, const Lorentz& particle) {
        if (RootObjects* object = find(objects, set)) fill(*object, particle);
    }

   inline void pythiaAnalysis(Pythia8::Pythia& pythia,
                           RootArray& histogramSets,
                           const Parameters& parameters,
                           Config::Root& root,
                           Config::Log& logging,
                           Monitor::AsyncLogger& asyncLogger)
    {
        const std::size_t eventIndex = ++logging.iEvent;
        ++logging.nRealEvents;

        const int workerIndex = pythia.mode("Parallelism:index");

        Lorentz lambda, proton, pion;
        std::vector<Lorentz> protonList, pionList;

        protonList.reserve(pythia.event.size());
        pionList.reserve(pythia.event.size());

        if (eventIndex == 1) {
            std::lock_guard<std::mutex> terminalLock(Monitor::terminalMutex());
            pythia.info.list();
            std::cout << "\n\n\n" << std::endl;
        }

        for (std::size_t i = 0; i < pythia.event.size(); ++i) {
            const auto& p = pythia.event[i];

            if (p.id() == 2212)
                protonList.emplace_back(p.px(), p.py(), p.pz(), p.e());
            else if (p.id() == -211)
                pionList.emplace_back(p.px(), p.py(), p.pz(), p.e());
        }

        Record::resetAllCounts(histogramSets);
        logging.elapsed = std::chrono::duration_cast<Config::uSeconds>( std::chrono::system_clock::now() - logging.start);

        asyncLogger.publishThreadStats( workerIndex, Monitor::ThreadPhase::Analysis, eventIndex, Monitor::NoCallbackCompleted );

        std::vector<bool> pionTaken(pionList.size(), false);

        for (std::size_t iProton = 0; iProton < protonList.size(); ++iProton) {
            bool hasCandidate = false;
            std::size_t bestPionIndex = 0;
            Double_t leastMassDelta = 0.0;
            Lorentz bestLambda;

            proton = protonList[iProton];

            for (std::size_t iPion = 0; iPion < pionList.size(); ++iPion) {

                pion = pionList[iPion];
                lambda = proton + pion;

                fill(histogramSets, HistogramSet::Unvalidated, lambda);

                if (pionTaken[iPion]) continue;

                const Double_t theta = cosTheta(proton, pion, lambda);

                if (!(massAccepted(lambda, parameters) && thetaAccepted(theta, parameters))) continue;

                fill(histogramSets, HistogramSet::Validated, lambda);

                const Double_t currentMassDelta = std::abs(lambda.M() - kLambdaMass);

                if (!hasCandidate || currentMassDelta < leastMassDelta) {
                    hasCandidate     = true;
                    leastMassDelta   = currentMassDelta;
                    bestPionIndex    = iPion;
                    bestLambda       = lambda;
                }
            }

            if (hasCandidate) {
                pionTaken[bestPionIndex] = true;
                fill(histogramSets, HistogramSet::Selected, bestLambda);
            }
        }

        Record::countAll(histogramSets);
        logging.elapsed = std::chrono::duration_cast<Config::uSeconds>( std::chrono::system_clock::now() - logging.start );

        const bool shouldRenderStatus = (eventIndex % logging.printInterval == 0) || (eventIndex == 1) || (eventIndex == logging.nEvents);
        const bool shouldRenderBar    = (eventIndex % logging.barInterval == 0)   || (eventIndex == 1) || (eventIndex == logging.nEvents);

        asyncLogger.publish( logging, Monitor::RunPhase::Analysis, eventIndex, shouldRenderStatus, shouldRenderBar, Monitor::DontWriteRunStat );

        if (logging.checkInterval > 0 && eventIndex % logging.checkInterval == 0) {
            Record::checkpointWrite( histogramSets, root.checkpointOutName, root.histScale, eventIndex );
            Monitor::outputLog( pythia, root, logging, logString(parameters), root.checkpointLogName );
        }

        asyncLogger.publishThreadStats( workerIndex, Monitor::ThreadPhase::Simulation, eventIndex, Monitor::CallbackCompleted );
    }

    // Schema declaration — owned by the physics module, consumed by any binary
    // that reads the Lambda ROOT data format.
    inline std::vector<Explore::CollectionSpec> inputSchema() {
        return {
            {"protons", "Protons", Explore::CartesianSpec{"pX", "pY", "pZ", "Energy"}, {"event_index"}, {}},
            {"pions",   "Pions",   Explore::CartesianSpec{"pX", "pY", "pZ", "Energy"}, {"event_index"}, {}},
        };
    }

    inline void analyzeEvent(const Explore::Event& ev,
                              int threadId,
                              RootArray& histogramSets,
                              const Parameters& parameters,
                              Config::Log& logging,
                              Monitor::AsyncLogger& asyncLogger,
                              std::mutex& histMutex)
    {
        const std::size_t eventIndex = ++logging.iEvent;

        asyncLogger.publishThreadStats(threadId, Monitor::ThreadPhase::Analysis, eventIndex, Monitor::NoCallbackCompleted);

        // Reconstruction math — thread-local, no lock required
        const auto& protons = ev["protons"];
        const auto& pions   = ev["pions"];

        std::vector<Lorentz> unvalidated, validated, selected;
        std::vector<bool> pionTaken(pions.size(), false);

        for (std::size_t iProton = 0; iProton < protons.size(); ++iProton) {
            const Lorentz& proton = protons[iProton];
            bool hasCandidate     = false;
            std::size_t bestIdx   = 0;
            Double_t leastDelta   = 0.0;
            Lorentz bestLambda;

            for (std::size_t iPion = 0; iPion < pions.size(); ++iPion) {
                const Lorentz& pion = pions[iPion];
                const Lorentz lambda = proton + pion;

                unvalidated.push_back(lambda);

                if (pionTaken[iPion]) continue;

                const Double_t theta = cosTheta(proton, pion, lambda);
                if (!(massAccepted(lambda, parameters) && thetaAccepted(theta, parameters))) continue;

                validated.push_back(lambda);

                const Double_t delta = std::abs(lambda.M() - kLambdaMass);
                if (!hasCandidate || delta < leastDelta) {
                    hasCandidate = true;
                    leastDelta   = delta;
                    bestIdx      = iPion;
                    bestLambda   = lambda;
                }
            }

            if (hasCandidate) {
                pionTaken[bestIdx] = true;
                selected.push_back(bestLambda);
            }
        }

        // Lock only for shared histogram and logging state
        {
            std::lock_guard<std::mutex> lock(histMutex);
            ++logging.nRealEvents;
            Record::resetAllCounts(histogramSets);
            for (const auto& l : unvalidated) fill(histogramSets, HistogramSet::Unvalidated, l);
            for (const auto& l : validated)   fill(histogramSets, HistogramSet::Validated,   l);
            for (const auto& l : selected)    fill(histogramSets, HistogramSet::Selected,     l);
            Record::countAll(histogramSets);
            logging.elapsed = std::chrono::duration_cast<Config::uSeconds>(
                std::chrono::system_clock::now() - logging.start);
        }

        const bool renderStatus = (eventIndex % logging.printInterval == 0) || (eventIndex == 1) || (eventIndex == logging.nEvents);
        const bool renderBar    = (eventIndex % logging.barInterval == 0)   || (eventIndex == 1) || (eventIndex == logging.nEvents);

        asyncLogger.publish(logging, Monitor::RunPhase::Analysis, eventIndex, renderStatus, renderBar, Monitor::DontWriteRunStat);
        asyncLogger.publishThreadStats(threadId, Monitor::ThreadPhase::Simulation, eventIndex, Monitor::CallbackCompleted);
    }

    inline void pythiaGenerator(
        Pythia8::Pythia&       pythia,
        DataObjects&           data,
        std::mutex&            treeMutex,
        Config::Log&           logging,
        Monitor::AsyncLogger&  asyncLogger)
    {
        const std::size_t eventIndex = ++logging.iEvent;
        ++logging.nRealEvents;
        const int workerIndex = pythia.mode("Parallelism:index");

        asyncLogger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Analysis, eventIndex, Monitor::NoCallbackCompleted);

        // Collect final-state protons and π⁻ per-thread before taking the lock
        std::vector<std::array<Double_t, 4>> protons, pions;
        for (int i = 0; i < pythia.event.size(); ++i) {
            const auto& p = pythia.event[i];
            if (!p.isFinal()) continue;
            if      (p.id() ==  2212) protons.push_back({p.e(), p.px(), p.py(), p.pz()});
            else if (p.id() == -211)  pions.push_back(  {p.e(), p.px(), p.py(), p.pz()});
        }

        // TTree::Fill is not thread-safe — serialise fills, keep the lock scope tight
        const Int_t eventIdx = static_cast<Int_t>(eventIndex);
        {
            std::lock_guard<std::mutex> lock(treeMutex);
            auto& pb = *data.protonBranches;
            *data.protonEventIndex = eventIdx;
            for (const auto& v : protons) { pb = v; data.protons->Fill(); }
            auto& ib = *data.pionBranches;
            *data.pionEventIndex = eventIdx;
            for (const auto& v : pions)   { ib = v; data.pions->Fill(); }
        }

        logging.elapsed = std::chrono::duration_cast<Config::uSeconds>(
            std::chrono::system_clock::now() - logging.start);

        const bool shouldRenderStatus = (eventIndex % logging.printInterval == 0) || eventIndex == 1 || eventIndex == logging.nEvents;
        const bool shouldRenderBar    = (eventIndex % logging.barInterval == 0)   || eventIndex == 1 || eventIndex == logging.nEvents;

        asyncLogger.publish(logging, Monitor::RunPhase::Analysis, eventIndex, shouldRenderStatus, shouldRenderBar, Monitor::DontWriteRunStat);
        asyncLogger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Simulation, eventIndex, Monitor::CallbackCompleted);
    }

    inline std::string dataLogString() {
        std::ostringstream stream;
        stream << "Proton PDG ID                 : 2212\n";
        stream << "Pion PDG ID                   : -211 (pi-)\n";
        stream << "Selection                     : isFinal() only\n";
        return stream.str();
    }

    inline void extractPhysics(const std::string& configPath, Parameters& parameters, const Config::Root& root) {
        toml::table config = toml::parse_file(configPath);

        parameters.massTolerance      = config["lambda"]["delta_mass_gev"].value_or(0.1);
        parameters.ThetaTolerance     = config["lambda"]["delta_theta_rad"].value_or(0.1);
        parameters.cosThetaTolerance  = std::cos(parameters.ThetaTolerance);

        if (!std::filesystem::exists(root.histLimitsFile.Data())) {
            throw std::runtime_error("Histogram limits file does not exist: " + std::string(root.histLimitsFile.Data()));
        }

        toml::table lTbl = toml::parse_file(root.histLimitsFile.Data());
        for (const auto& histogramSet : kHistogramSetMap) {
            if (!lTbl.contains(histogramSet.tag) || !lTbl[histogramSet.tag].is_table()) {
                throw std::runtime_error("Missing histogram set table: " + std::string(histogramSet.tag));
            }

            toml::table& subTbl = *lTbl[histogramSet.tag].as_table();
            Config::RangeSize defaultLevel = Config::RangeSize::Moderate;
            if (const auto defaultNode = subTbl["default"]; defaultNode.is_string()) {
                defaultLevel = Config::stringToLevel(defaultNode.value<std::string>().value_or("Moderate"));
            }

            std::vector<Config::Quantity> toResolve = {Config::Quantity::Multiplicity};
            toResolve.insert(toResolve.end(), Recorded_Quantities.begin(), Recorded_Quantities.end());

            for (const Config::Quantity quantity : toResolve) {
                std::optional<Config::Bounds> resolved;
                const std::string primaryKey = Analysis::quantityName(quantity);
                const std::string aliasKey = quantityAlias(quantity);

                if (toml::node* node = subTbl.get(primaryKey)) {
                    resolved = boundsFromValue(*node, root, quantity);
                }

                if (!resolved && aliasKey != primaryKey) {
                    if (toml::node* node = subTbl.get(aliasKey)) {
                        resolved = boundsFromValue(*node, root, quantity);
                    }
                }

                if (!resolved) {
                    resolved = levelBounds(root, quantity, defaultLevel);
                }

                parameters.setLimits[histogramSet.id][quantity] = *resolved;
            }
        }
    }

    inline std::string logString(const Parameters& parameters) {
        std::ostringstream stream;
        stream << "Lambda Mass                   : " << kLambdaMass << '\n';
        stream << "Proton Mass                   : " << kProtonMass << '\n';
        stream << "Pion Mass                     : " << kPionMass << '\n';
        stream << "Mass Difference               : " << kMassDiff << '\n';
        stream << "Mass Tolerance                : " << parameters.massTolerance << '\n';
        stream << "Theta Tolerance               : " << parameters.ThetaTolerance << '\n';
        return stream.str();
    }
}
