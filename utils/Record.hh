#pragma once

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <array>
#include <cstddef>
#include <memory>
#include <thread>
#include <utility>
#include <vector>
#include <string>

#include "Config.hh"
#include "Meta.hh"
#include "Monitor.hh"
#include "Analysis.hh"
#include "TFile.h"
#include "TDirectory.h"
#include "TH1.h"
#include "TH1D.h"
#include "TH2.h"
#include "TGraph.h"
#include "TProfile.h"
#include "TTree.h"
#include "TString.h"

namespace Record {
    using Lorentz = Analysis::Lorentz;

    struct NoBasis {};

    // Per-particle histogram/tree records keyed by ParticleProperty
    struct TH1Record {
        TH1D*                    hist{};
        Config::ParticleProperty property{};
    };
    struct TH2Record {
        TH2*                     hist{};
        Config::ParticleProperty propertyX{};
        Config::ParticleProperty propertyY{};
    };

    struct TreeRecord {
        TTree* tree{};
        std::vector<Config::ParticleProperty>   properties{};
        std::unique_ptr<std::vector<Double_t>>  branchValues{std::make_unique<std::vector<Double_t>>()};
    };

    // Per-event histogram record keyed by EventProperty
    struct EventTH1Record {
        TH1D*                 hist{};
        Config::EventProperty property{};
    };

    template <std::size_t N>
    inline TreeRecord declareTree(
        TDirectory* dir,
        const std::string& name,
        const std::string& title,
        const std::array<Config::ParticleProperty, N>& properties
    ) {
        if (dir == nullptr)
            throw std::invalid_argument("Tree directory must not be null");

        TreeRecord record{};
        record.properties.assign(properties.begin(), properties.end());
        record.branchValues = std::make_unique<std::vector<Double_t>>(record.properties.size(), 0.0);

        dir->cd();
        record.tree = new TTree(name.c_str(), title.c_str());

        for (std::size_t i = 0; i < record.properties.size(); ++i) {
            const std::string branchName = Analysis::particlePropertyName(record.properties[i]);
            const std::string branchType = branchName + "/D";
            record.tree->Branch(branchName.c_str(), record.branchValues->data() + i, branchType.c_str());
        }

        return record;
    }

    template <typename Basis = NoBasis>
    struct RootObjects {
        Basis basis{};
        TDirectory* dir{};
        TH1D* count{};
        Int_t candidateCount{};
        std::vector<TH1Record>      hists1D;
        std::vector<EventTH1Record> eventHists1D;   // per-event observables
        std::vector<TH2*>           hists2D;
        std::vector<TGraph*>        graphs;
        std::vector<TProfile*>      profiles;
        std::vector<TreeRecord>     trees;
    };

    template <typename Basis = NoBasis>
    using RootArray = std::vector<RootObjects<Basis>>;

    template <typename Basis>
    inline void count(RootObjects<Basis>& object) {
        if (object.count != nullptr) {
            object.count->Fill(object.candidateCount);
        }
    }

    template <typename Basis>
    inline void countAll(RootArray<Basis>& objects) {
        for (auto& object : objects) {
            count(object);
        }
    }

    template <typename Basis>
    inline void resetCount(RootObjects<Basis>& object) {
        object.candidateCount = 0;
    }

    template <typename Basis>
    inline void resetAllCounts(RootArray<Basis>& objects) {
        for (auto& object : objects) {
            resetCount(object);
        }
    }

    inline void fill(TH1Record& record, const Lorentz& particle) {
        if (record.hist != nullptr)
            record.hist->Fill(Analysis::valueOf(particle, record.property));
    }

    inline void fill(EventTH1Record& record, const std::vector<Lorentz>& particles) {
        if (record.hist != nullptr)
            record.hist->Fill(Analysis::valueOf(particles, record.property));
    }

    inline void fill(TreeRecord& record, const Lorentz& particle) {
        if (record.tree == nullptr || record.branchValues == nullptr) return;
        for (std::size_t i = 0; i < record.properties.size(); ++i)
            (*record.branchValues)[i] = Analysis::valueOf(particle, record.properties[i]);
        record.tree->Fill();
    }

    inline void scaleAndWrite(TObject* object, Double_t histScale, std::size_t nEvents, bool width = true) {
        if (object == nullptr) return;

        if (object->InheritsFrom(TH1::Class())) {
            TH1* hist = static_cast<TH1*>(object);
            std::unique_ptr<TH1> snapshot(static_cast<TH1*>(hist->Clone(hist->GetName())));
            if (!snapshot) return;

            if (nEvents > 0) {
                const Double_t scale = histScale / static_cast<Double_t>(nEvents);
                if (width && !object->InheritsFrom(TH2::Class())) snapshot->Scale(scale, "width");
                else snapshot->Scale(scale);
            }

            snapshot->Write("", TObject::kOverwrite);
            return;
        }

        object->Write("", TObject::kOverwrite);
    }

    inline void scaleAndWriteToDir(TDirectory* dir, TObject* object, Double_t histScale, std::size_t nEvents, bool width = true) {
        if (dir == nullptr || object == nullptr) return;
        dir->cd();
        scaleAndWrite(object, histScale, nEvents, width);
    }

    template <typename Basis>
    inline void write(RootObjects<Basis>& object, Double_t histScale, std::size_t nEvents, bool checkpoint = false) {
        if (object.dir == nullptr) return;
        object.dir->cd();
        scaleAndWrite(object.count, histScale, nEvents, false);
        for (auto& hist : object.hists1D)      scaleAndWrite(hist.hist,  histScale, nEvents, true);
        for (auto& hist : object.eventHists1D) scaleAndWrite(hist.hist,  histScale, nEvents, false);
        for (TH2* hist : object.hists2D)       scaleAndWrite(hist,       histScale, nEvents, false);
        for (TGraph* graph : object.graphs)    scaleAndWrite(graph,      histScale, nEvents, false);
        for (TProfile* p : object.profiles)    scaleAndWrite(p,          histScale, nEvents, false);
        if (!checkpoint) {
            for (auto& tree : object.trees) scaleAndWrite(tree.tree, histScale, nEvents, false);
        }
    }

    template <typename Basis>
    inline void writeToDir(RootObjects<Basis>& object, TDirectory* dir, Double_t histScale, std::size_t nEvents, bool checkpoint = false) {
        if (dir == nullptr) return;
        scaleAndWriteToDir(dir, object.count, histScale, nEvents, false);
        for (auto& hist : object.hists1D)      scaleAndWriteToDir(dir, hist.hist,  histScale, nEvents, true);
        for (auto& hist : object.eventHists1D) scaleAndWriteToDir(dir, hist.hist,  histScale, nEvents, false);
        for (TH2* hist : object.hists2D)       scaleAndWriteToDir(dir, hist,       histScale, nEvents, false);
        for (TGraph* graph : object.graphs)    scaleAndWriteToDir(dir, graph,      histScale, nEvents, false);
        for (TProfile* p : object.profiles)    scaleAndWriteToDir(dir, p,          histScale, nEvents, false);
        if (!checkpoint) {
            for (auto& tree : object.trees) scaleAndWriteToDir(dir, tree.tree, histScale, nEvents, false);
        }
    }

    template <typename Basis>
    inline void writeAll(RootArray<Basis>& objects, Double_t histScale, std::size_t nEvents) {
        for (auto& object : objects) write(object, histScale, nEvents);
    }

    template <typename Basis>
    inline void checkpointWrite(RootArray<Basis>& objects, const TString& checkpointOutName, Double_t histScale, std::size_t nEvents) {
        TFile checkpointFile(checkpointOutName.Data(), "RECREATE");
        if (!checkpointFile.IsOpen()) return;
        for (auto& object : objects) {
            if (object.dir == nullptr) continue;
            TDirectory* checkpointDir = checkpointFile.mkdir(object.dir->GetName());
            writeToDir(object, checkpointDir, histScale, nEvents, true);
        }
        checkpointFile.Write("", TObject::kOverwrite);
        checkpointFile.Close();
    }

    template <typename Basis>
    inline void wrapUp(RootArray<Basis>& objects, TFile* outFile, Double_t histScale, std::size_t nEvents) {
        writeAll(objects, histScale, nEvents);
        if (outFile != nullptr) outFile->Close();
    }

    inline constexpr auto FatalGracePeriod = std::chrono::seconds(10);

    template <typename PythiaT, typename RootArrayT, typename ProgramLogBuilder>
    class FinalizerController {
      public:
        FinalizerController(PythiaT& pythia, RootArrayT& histogramSets, Config::Root& root, Config::Log& logging, Monitor::AsyncLogger& logger, ProgramLogBuilder programLogBuilder)
            : pythia_(pythia), histogramSets_(histogramSets), root_(root), logging_(logging), logger_(logger), programLogBuilder_(std::move(programLogBuilder)) {}

        void installFatalStallHandler() {
            logger_.setFatalStallHandler([this](const Monitor::RunSnapshot& snapshot) { fatalShutdown(snapshot); });
        }

        void setMeta(Meta::Record meta) { meta_ = std::move(meta); }

        void normalShutdown() {
            // Write all histograms/trees
            writeAll(histogramSets_, root_.histScale, logging_.nEvents);
            // Write metadata before closing
            if (meta_.has_value() && root_.outFile != nullptr)
                Meta::writeAbout(root_.outFile, *meta_);
            // Now close
            if (root_.outFile != nullptr) {
                root_.outFile->Write("", TObject::kOverwrite);
                root_.outFile->Close();
            }
            logging_.elapsed = std::chrono::duration_cast<Config::uSeconds>(
                std::chrono::system_clock::now() - logging_.start);
            logger_.finish(logging_, logging_.iEvent.load());
            Monitor::terminalReport(pythia_, root_, logging_);
            Monitor::outputLog(pythia_, root_, logging_, programLogBuilder_());
        }

      private:
        void fatalShutdown(const Monitor::RunSnapshot& snapshot) {
            if (fatalShutdownStarted_.exchange(true)) return;
            Config::Log frozenLog = logging_;
            frozenLog.elapsed = std::chrono::duration_cast<Config::uSeconds>(std::chrono::system_clock::now() - logging_.start);
            Monitor::RunSnapshot frozenSnapshot = snapshot;
            frozenSnapshot.elapsed = frozenLog.elapsed;

            const std::string programLog = programLogBuilder_();
            Monitor::writeEmergencyLog(root_, frozenLog, frozenSnapshot, programLog, "fatal-stall detected");

            auto completed = std::make_shared<std::atomic<bool>>(false);
            std::thread([this, frozenLog, programLog, completed]() {
                wrapUp(histogramSets_, root_.outFile, root_.histScale, frozenLog.nEvents);
                Monitor::outputLog(pythia_, root_, frozenLog, programLog);
                completed->store(true);
            }).detach();
            const auto deadline = std::chrono::steady_clock::now() + FatalGracePeriod;
            while (std::chrono::steady_clock::now() < deadline) {
                if (completed->load()) std::_Exit(EXIT_FAILURE);
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
            }
            Monitor::writeEmergencyLog(root_, frozenLog, frozenSnapshot, programLog, "fatal-stall fallback after timed-out wrapUp/log attempt");
            std::_Exit(EXIT_FAILURE);
        }
        PythiaT& pythia_;
        RootArrayT& histogramSets_;
        Config::Root& root_;
        Config::Log& logging_;
        Monitor::AsyncLogger& logger_;
        ProgramLogBuilder programLogBuilder_;
        std::atomic<bool> fatalShutdownStarted_{false};
        std::optional<Meta::Record> meta_;
    };
}
