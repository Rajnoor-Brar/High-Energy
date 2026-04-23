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

    // ── Part 4: Input branch configuration ───────────────────────────────────
    struct InputConfig {
        std::string indexBranch = "event_index";
        std::string energy      = "Energy";
        std::string px          = "pX";
        std::string py          = "pY";
        std::string pz          = "pZ";
        // Per-collection tree name overrides: label → tree name
        // Default: capitalize first letter of label ("protons" → "Protons")
        std::map<std::string, std::string> treeNames;
    };

    // ── Part 4: Per-candidate-type configuration ──────────────────────────────
    struct CandidateConfig {
        std::string label;
        bool        enabled   = true;
        bool        writeTree = true;
        int         pidAbs    = 0;     // optional PID cut hint (0 = unused)
    };

    struct Parameters {
        Double_t massTolerance     = 0.1;
        Double_t ThetaTolerance    = 0.1;
        Double_t cosThetaTolerance = 0.0;
        std::map<HistogramSet, std::map<Config::ParticleProperty, Config::Bounds>> setParticleLimits;
        std::map<HistogramSet, std::map<Config::EventProperty,    Config::Bounds>> setEventLimits;
        // Part 4
        InputConfig                input;
        std::vector<CandidateConfig> candidates = {
            {"protons", true, true, 2212},
            {"pions",   true, true,  211}
        };
    };

    inline constexpr std::array<Config::ParticleProperty, 6> Recorded_ParticleProperties = {
        Config::ParticleProperty::Mass_Invariant,
        Config::ParticleProperty::Energy_Net,
        Config::ParticleProperty::Momentum_Net,
        Config::ParticleProperty::Momentum_Transverse,
        Config::ParticleProperty::Momentum_Z,
        Config::ParticleProperty::Pseudorapidity
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

    inline std::string particlePropertyAlias(Config::ParticleProperty p) {
        switch (p) {
            case Config::ParticleProperty::Mass_Invariant: return "Mass";
            case Config::ParticleProperty::Energy_Net:     return "Energy";
            default:                                       return Analysis::particlePropertyName(p);
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

    inline const Config::Bounds& levelBounds(const Config::Root& root,
                                              Config::ParticleProperty p,
                                              Config::RangeSize level) {
        const auto qit = root.particleLimits.find(p);
        if (qit == root.particleLimits.end())
            throw std::runtime_error("No configured limits for particle property " +
                                     Analysis::particlePropertyName(p));
        const auto lit = qit->second.find(level);
        if (lit == qit->second.end())
            throw std::runtime_error("No configured " + particlePropertyAlias(p) +
                                     " limit for level " + levelName(level));
        return lit->second;
    }

    inline const Config::Bounds& levelBounds(const Config::Root& root,
                                              Config::EventProperty p,
                                              Config::RangeSize level) {
        const auto qit = root.eventLimits.find(p);
        if (qit == root.eventLimits.end())
            throw std::runtime_error("No configured limits for event property " +
                                     Analysis::eventPropertyName(p));
        const auto lit = qit->second.find(level);
        if (lit == qit->second.end())
            throw std::runtime_error("No configured " + Analysis::eventPropertyName(p) +
                                     " limit for level " + levelName(level));
        return lit->second;
    }

    inline std::optional<Config::Bounds> boundsFromValue(const toml::node& node) {
        if (!node.is_array()) return std::nullopt;
        const toml::array& array = *node.as_array();
        if (array.size() != 2)
            throw std::runtime_error("Expected exactly 2 numeric values in explicit histogram bounds");
        const auto low  = array[0].value<Double_t>();
        const auto high = array[1].value<Double_t>();
        if (!low || !high)
            throw std::runtime_error("Expected numeric histogram bounds");
        return Config::Bounds{*low, *high};
    }

    inline std::optional<Config::Bounds> boundsFromValue(const toml::node& node,
                                                          const Config::Root& root,
                                                          Config::ParticleProperty p) {
        if (const auto b = boundsFromValue(node)) return b;
        if (!node.is_string()) return std::nullopt;
        return levelBounds(root, p, Config::stringToLevel(node.value<std::string>().value_or("")));
    }

    inline std::optional<Config::Bounds> boundsFromValue(const toml::node& node,
                                                          const Config::Root& root,
                                                          Config::EventProperty p) {
        if (const auto b = boundsFromValue(node)) return b;
        if (!node.is_string()) return std::nullopt;
        return levelBounds(root, p, Config::stringToLevel(node.value<std::string>().value_or("")));
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

        // Whether any enabled candidate has writeTree=true
        const bool anyWriteTree = std::any_of(
            parameters.candidates.begin(), parameters.candidates.end(),
            [](const CandidateConfig& c){ return c.enabled && c.writeTree; });

        for (const auto& histogramSet : kHistogramSetMap) {
            RootObjects object{};

            object.basis = histogramSet.id;
            object.dir   = root.outFile->mkdir(histogramSet.directoryName);

            // ── Multiplicity (event-level) ────────────────────────────────────
            if (!parameters.setEventLimits.count(histogramSet.id) ||
                !parameters.setEventLimits.at(histogramSet.id).count(Config::EventProperty::Multiplicity)) {
                throw std::runtime_error("No Multiplicity limit defined for set " +
                                         std::string(histogramSet.tag));
            }
            const Config::Bounds mBounds =
                parameters.setEventLimits.at(histogramSet.id).at(Config::EventProperty::Multiplicity);

            object.count = new TH1D(
                (std::string(histogramSet.tag) + "CountHist").c_str(),
                "Count of Reconstructed Candidates",
                static_cast<int>(mBounds.high - mBounds.low + 1),
                mBounds.low - 0.5,
                mBounds.high + 0.5
            );

            // ── Per-particle kinematic histograms ─────────────────────────────
            for (const auto& prop : Recorded_ParticleProperties) {
                if (!parameters.setParticleLimits.count(histogramSet.id) ||
                    !parameters.setParticleLimits.at(histogramSet.id).count(prop)) {
                    throw std::runtime_error(
                        "No limit defined for set " + std::string(histogramSet.tag) +
                        " and property " + Analysis::particlePropertyName(prop));
                }
                const Config::Bounds bounds =
                    parameters.setParticleLimits.at(histogramSet.id).at(prop);
                const std::string propName = Analysis::particlePropertyName(prop);
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

            // ── Candidate tree (per-candidate writeTree toggle) ───────────────
            if (hasTree(histogramSet.id) && anyWriteTree) {
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

    struct Candidates {
        std::vector<Lorentz> unvalidated;
        std::vector<Lorentz> validated;
        std::vector<Lorentz> selected;
    };

    inline Candidates reconstructCandidates(const std::vector<Lorentz>& protons,
                                             const std::vector<Lorentz>& pions,
                                             const Parameters& parameters)
    {
        Candidates result;
        std::vector<bool> pionTaken(pions.size(), false);

        for (std::size_t iProton = 0; iProton < protons.size(); ++iProton) {
            const Lorentz& proton = protons[iProton];
            bool hasCandidate   = false;
            std::size_t bestIdx = 0;
            Double_t leastDelta = 0.0;
            Lorentz bestLambda;

            for (std::size_t iPion = 0; iPion < pions.size(); ++iPion) {
                const Lorentz& pion = pions[iPion];
                const Lorentz lambda = proton + pion;

                result.unvalidated.push_back(lambda);

                if (pionTaken[iPion]) continue;

                const Double_t theta = cosTheta(proton, pion, lambda);
                if (!(massAccepted(lambda, parameters) && thetaAccepted(theta, parameters))) continue;

                result.validated.push_back(lambda);

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
                result.selected.push_back(bestLambda);
            }
        }
        return result;
    }

    inline void fillCandidates(RootArray& histogramSets, const Candidates& c) {
        Record::resetAllCounts(histogramSets);
        for (const auto& l : c.unvalidated) fill(histogramSets, HistogramSet::Unvalidated, l);
        for (const auto& l : c.validated)   fill(histogramSets, HistogramSet::Validated,   l);
        for (const auto& l : c.selected)    fill(histogramSets, HistogramSet::Selected,     l);
        Record::countAll(histogramSets);
    }

    inline void publishProgress(Monitor::AsyncLogger& asyncLogger,
                                 const Config::Log& logging,
                                 std::size_t eventIndex,
                                 int workerIndex)
    {
        const bool renderStatus = (eventIndex % logging.printInterval == 0) || (eventIndex == 1) || (eventIndex == logging.nEvents);
        const bool renderBar    = (eventIndex % logging.barInterval == 0)   || (eventIndex == 1) || (eventIndex == logging.nEvents);
        asyncLogger.publish(logging, Monitor::RunPhase::Analysis, eventIndex, renderStatus, renderBar, Monitor::DontWriteRunStat);
        asyncLogger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Simulation, eventIndex, Monitor::CallbackCompleted);
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

        if (eventIndex == 1) {
            std::lock_guard<std::mutex> terminalLock(Monitor::terminalMutex());
            pythia.info.list();
            std::cout << "\n\n\n" << std::endl;
        }

        std::vector<Lorentz> protonList, pionList;
        protonList.reserve(pythia.event.size());
        pionList.reserve(pythia.event.size());
        for (std::size_t i = 0; i < static_cast<std::size_t>(pythia.event.size()); ++i) {
            const auto& p = pythia.event[i];
            if (p.id() == 2212)      protonList.emplace_back(p.px(), p.py(), p.pz(), p.e());
            else if (p.id() == -211) pionList.emplace_back(p.px(), p.py(), p.pz(), p.e());
        }

        asyncLogger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Analysis, eventIndex, Monitor::NoCallbackCompleted);

        fillCandidates(histogramSets, reconstructCandidates(protonList, pionList, parameters));

        logging.elapsed = std::chrono::duration_cast<Config::uSeconds>(std::chrono::system_clock::now() - logging.start);
        publishProgress(asyncLogger, logging, eventIndex, workerIndex);

        if (logging.checkInterval > 0 && eventIndex % logging.checkInterval == 0) {
            Record::checkpointWrite(histogramSets, root.checkpointOutName, root.histScale, eventIndex);
            Monitor::outputLog(pythia, root, logging, logString(parameters), root.checkpointLogName);
        }

        asyncLogger.publishThreadStats( workerIndex, Monitor::ThreadPhase::Simulation, eventIndex, Monitor::CallbackCompleted );
    }

    // Schema declaration — built from Parameters so branch names and candidate
    // list are config-driven. Callers should prefer the Parameters overload.
    inline std::vector<Explore::CollectionSpec> inputSchema(const Parameters& params) {
        std::vector<Explore::CollectionSpec> schema;
        const auto& inp = params.input;
        for (const auto& cand : params.candidates) {
            if (!cand.enabled) continue;
            // Default tree name: capitalize first letter of label
            std::string treeName = cand.label;
            if (!treeName.empty())
                treeName[0] = static_cast<char>(std::toupper(
                                  static_cast<unsigned char>(treeName[0])));
            // Per-collection override
            auto it = inp.treeNames.find(cand.label);
            if (it != inp.treeNames.end()) treeName = it->second;

            schema.push_back({
                cand.label,
                treeName,
                Explore::CartesianSpec{inp.px, inp.py, inp.pz, inp.energy},
                {inp.indexBranch},
                {}
            });
        }
        return schema;
    }

    // Backward-compatible free function — uses all defaults (same as hardcoded behavior)
    inline std::vector<Explore::CollectionSpec> inputSchema() {
        return inputSchema(Parameters{});
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
        std::vector<Lorentz> unvalidated, validated, selected;
        std::vector<bool> pionTaken(ev["Pions"].size(), false);

        for (std::size_t iProton = 0; iProton < ev["Protons"].size(); ++iProton) {
            const Lorentz& proton = ev["Protons"][iProton];
            bool hasCandidate     = false;
            std::size_t bestIdx   = 0;
            Double_t leastDelta   = 0.0;
            Lorentz bestLambda;

            for (std::size_t iPion = 0; iPion < ev["Pions"].size(); ++iPion) {
                const Lorentz& pion = ev["Pions"][iPion];
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

            Candidates candidates;
            candidates.unvalidated = std::move(unvalidated);
            candidates.validated   = std::move(validated);
            candidates.selected    = std::move(selected);

            fillCandidates(histogramSets, candidates);
            logging.elapsed = std::chrono::duration_cast<Config::uSeconds>(std::chrono::system_clock::now() - logging.start);
        }

        publishProgress(asyncLogger, logging, eventIndex, threadId);
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

    // ── Part 4: load [input] section ─────────────────────────────────────────
    inline void loadInputSection(const toml::table& config, InputConfig& input) {
        const auto* sec = config["input"].as_table();
        if (!sec) return;
        input.indexBranch = (*sec)["index_branch"].value_or(input.indexBranch);
        input.energy      = (*sec)["energy"].value_or(input.energy);
        input.px          = (*sec)["px"].value_or(input.px);
        input.py          = (*sec)["py"].value_or(input.py);
        input.pz          = (*sec)["pz"].value_or(input.pz);
        // Per-collection tree name overrides: [input.<label>].tree_name
        for (auto&& [key, val] : *sec) {
            if (!val.is_table()) continue;
            const auto* sub = val.as_table();
            if (auto tn = (*sub)["tree_name"].value<std::string>())
                input.treeNames[std::string(key.str())] = *tn;
        }
    }

    // ── Part 4: load [candidates] section ────────────────────────────────────
    inline void loadCandidatesSection(const toml::table& config,
                                      std::vector<CandidateConfig>& candidates) {
        const auto* sec = config["candidates"].as_table();
        if (!sec || sec->empty()) return;   // keep defaults from Parameters ctor
        candidates.clear();
        for (auto&& [key, val] : *sec) {
            if (!val.is_table()) continue;
            const auto* sub = val.as_table();
            CandidateConfig c;
            c.label     = std::string(key.str());
            c.enabled   = (*sub)["enabled"].value_or(true);
            c.writeTree = (*sub)["write_tree"].value_or(true);
            c.pidAbs    = (*sub)["pid_abs"].value_or(0);
            candidates.push_back(c);
        }
    }

    inline void extractPhysics(const std::string& configPath, Parameters& parameters, const Config::Root& root) {
        toml::table config = toml::parse_file(configPath);

        parameters.massTolerance     = config["lambda"]["delta_mass_gev"].value_or(0.1);
        parameters.ThetaTolerance    = config["lambda"]["delta_theta_rad"].value_or(0.1);
        parameters.cosThetaTolerance = std::cos(parameters.ThetaTolerance);

        // Part 4 — input schema + candidate config
        loadInputSection(config, parameters.input);
        loadCandidatesSection(config, parameters.candidates);

        if (!std::filesystem::exists(root.histLimitsFile.Data())) {
            throw std::runtime_error("Histogram limits file does not exist: " +
                                     std::string(root.histLimitsFile.Data()));
        }

        toml::table lTbl = toml::parse_file(root.histLimitsFile.Data());
        for (const auto& histogramSet : kHistogramSetMap) {
            if (!lTbl.contains(histogramSet.tag) || !lTbl[histogramSet.tag].is_table())
                throw std::runtime_error("Missing histogram set table: " +
                                         std::string(histogramSet.tag));

            toml::table& subTbl = *lTbl[histogramSet.tag].as_table();
            Config::RangeSize defaultLevel = Config::RangeSize::Moderate;
            if (const auto dn = subTbl["default"]; dn.is_string())
                defaultLevel = Config::stringToLevel(dn.value<std::string>().value_or("Moderate"));

            // ── Particle properties ───────────────────────────────────────────
            for (const Config::ParticleProperty prop : Recorded_ParticleProperties) {
                std::optional<Config::Bounds> resolved;
                const std::string primaryKey = Analysis::particlePropertyName(prop);
                const std::string aliasKey   = particlePropertyAlias(prop);

                if (toml::node* node = subTbl.get(primaryKey))
                    resolved = boundsFromValue(*node, root, prop);
                if (!resolved && aliasKey != primaryKey)
                    if (toml::node* node = subTbl.get(aliasKey))
                        resolved = boundsFromValue(*node, root, prop);
                if (!resolved)
                    resolved = levelBounds(root, prop, defaultLevel);

                parameters.setParticleLimits[histogramSet.id][prop] = *resolved;
            }

            // ── Event properties ──────────────────────────────────────────────
            const std::array<Config::EventProperty, 1> toResolveEvent = {
                Config::EventProperty::Multiplicity
            };
            for (const Config::EventProperty ep : toResolveEvent) {
                std::optional<Config::Bounds> resolved;
                const std::string key = Analysis::eventPropertyName(ep);

                if (toml::node* node = subTbl.get(key))
                    resolved = boundsFromValue(*node, root, ep);
                if (!resolved)
                    resolved = levelBounds(root, ep, defaultLevel);

                parameters.setEventLimits[histogramSet.id][ep] = *resolved;
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