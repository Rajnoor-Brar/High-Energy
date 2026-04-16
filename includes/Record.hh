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

#include "Config.hh"
#include "Monitor.hh"
#include "TFile.h"
#include "TDirectory.h"
#include "TH1.h"
#include "TH1D.h"
#include "TH1I.h"
#include "TString.h"

namespace Record {
    template <typename Enum>
    constexpr std::size_t toIndex(Enum value) {
        return static_cast<std::size_t>(value);
    }

    template <typename Basis, std::size_t HistCount>
    struct RootObjects {
        Basis basis{};
        TDirectory* dir{};
        TH1D* count{};
        Int_t validatedCount{};
        std::array<TH1D*, HistCount> hists{};
    };

    template <typename Basis, std::size_t HistCount>
    using RootArray = std::vector<RootObjects<Basis, HistCount>>;

    template <typename Basis, std::size_t HistCount>
    inline void count(RootObjects<Basis, HistCount>& object) {
        if (object.count != nullptr) {
            object.count->Fill(object.validatedCount);
        }
    }

    template <typename Basis, std::size_t HistCount>
    inline void countAll(RootArray<Basis, HistCount>& objects) {
        for (auto& object : objects) {
            count(object);
        }
    }

    template <typename Basis, std::size_t HistCount>
    inline void resetCount(RootObjects<Basis, HistCount>& object) {
        object.validatedCount = 0;
    }

    template <typename Basis, std::size_t HistCount>
    inline void resetAllCounts(RootArray<Basis, HistCount>& objects) {
        for (auto& object : objects) {
            resetCount(object);
        }
    }

    inline void scaleAndWrite(TH1* hist, Double_t histScale, std::size_t nEvents, bool width = true) {
        if (hist == nullptr) {
            return;
        }

        std::unique_ptr<TH1> snapshot(static_cast<TH1*>(hist->Clone(hist->GetName())));
        if (!snapshot) {
            return;
        }

        if (nEvents > 0) {
            const Double_t scale = histScale / static_cast<Double_t>(nEvents);
            if (width) {
                snapshot->Scale(scale, "width");
            } else {
                snapshot->Scale(scale);
            }
        }

        snapshot->Write("", TObject::kOverwrite);
    }

    inline void scaleAndWriteToDir(
        TDirectory* dir,
        TH1* hist,
        Double_t histScale,
        std::size_t nEvents,
        bool width = true
    ) {
        if (dir == nullptr || hist == nullptr) {
            return;
        }

        dir->cd();
        scaleAndWrite(hist, histScale, nEvents, width);
    }

    template <typename Basis, std::size_t HistCount>
    inline void write(RootObjects<Basis, HistCount>& object, Double_t histScale, std::size_t nEvents) {
        if (object.dir == nullptr) {
            return;
        }

        object.dir->cd();
        scaleAndWrite(object.count, histScale, nEvents, false);

        for (TH1D* hist : object.hists) {
            scaleAndWrite(hist, histScale, nEvents, true);
        }
    }

    template <typename Basis, std::size_t HistCount>
    inline void writeToDir(
        RootObjects<Basis, HistCount>& object,
        TDirectory* dir,
        Double_t histScale,
        std::size_t nEvents
    ) {
        if (dir == nullptr) {
            return;
        }

        scaleAndWriteToDir(dir, object.count, histScale, nEvents, false);

        for (TH1D* hist : object.hists) {
            scaleAndWriteToDir(dir, hist, histScale, nEvents, true);
        }
    }

    template <typename Basis, std::size_t HistCount>
    inline void writeAll(RootArray<Basis, HistCount>& objects, Double_t histScale, std::size_t nEvents) {
        for (auto& object : objects) {
            write(object, histScale, nEvents);
        }
    }

    template <typename Basis, std::size_t HistCount>
    inline void checkpointWrite(
        RootArray<Basis, HistCount>& objects,
        const TString& mainOutName,
        Double_t histScale,
        std::size_t nEvents
    ) {
        std::string checkpointName = mainOutName.Data();
        const std::string rootSuffix = ".root";
        if (checkpointName.size() >= rootSuffix.size() &&
            checkpointName.substr(checkpointName.size() - rootSuffix.size()) == rootSuffix) {
            checkpointName.erase(checkpointName.size() - rootSuffix.size());
        }
        checkpointName += ".root";

        TFile checkpointFile(checkpointName.c_str(), "RECREATE");
        if (!checkpointFile.IsOpen()) {
            return;
        }

        for (auto& object : objects) {
            if (object.dir == nullptr) {
                continue;
            }

            TDirectory* checkpointDir = checkpointFile.mkdir(object.dir->GetName());
            writeToDir(object, checkpointDir, histScale, nEvents);
        }

        checkpointFile.Write("", TObject::kOverwrite);
        checkpointFile.Close();
    }

    template <typename Basis, std::size_t HistCount>
    inline void wrapUp(
        RootArray<Basis, HistCount>& objects,
        TFile* outFile,
        Double_t histScale,
        std::size_t nEvents
    ) {
        writeAll(objects, histScale, nEvents);
        if (outFile != nullptr) {
            outFile->Close();
        }
    }

    inline constexpr auto FatalGracePeriod = std::chrono::seconds(10);

    template <typename PythiaT, typename RootArrayT, typename ProgramLogBuilder>
    class FinalizerController {
      public:
        FinalizerController(
            PythiaT& pythia,
            RootArrayT& histogramSets,
            Config::Root& root,
            Config::Log& logging,
            Monitor::AsyncLogger& logger,
            ProgramLogBuilder programLogBuilder
        )
            : pythia_(pythia),
              histogramSets_(histogramSets),
              root_(root),
              logging_(logging),
              logger_(logger),
              programLogBuilder_(std::move(programLogBuilder)) {}

        void installFatalStallHandler() {
            logger_.setFatalStallHandler([this](const Monitor::RunSnapshot& snapshot) {
                fatalShutdown(snapshot);
            });
        }

        void normalShutdown() {
            wrapUp(histogramSets_, root_.outFile, root_.histScale, logging_.nEvents);
            logging_.elapsed = std::chrono::duration_cast<Config::uSeconds>(
                std::chrono::system_clock::now() - logging_.start
            );
            logger_.finish(logging_, logging_.iEvent.load());
            Monitor::terminalReport(pythia_, root_, logging_);
            Monitor::outputLog(pythia_, root_, logging_, programLogBuilder_());
        }

      private:
        void fatalShutdown(const Monitor::RunSnapshot& snapshot) {
            if (fatalShutdownStarted_.exchange(true)) {
                return;
            }

            Config::Log frozenLog = logging_;
            frozenLog.elapsed = std::chrono::duration_cast<Config::uSeconds>(
                std::chrono::system_clock::now() - logging_.start
            );

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
                if (completed->load()) {
                    std::_Exit(EXIT_FAILURE);
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
            }

            Monitor::writeEmergencyLog(
                root_,
                frozenLog,
                frozenSnapshot,
                programLog,
                "fatal-stall fallback after timed-out wrapUp/log attempt"
            );
            std::_Exit(EXIT_FAILURE);
        }

        PythiaT& pythia_;
        RootArrayT& histogramSets_;
        Config::Root& root_;
        Config::Log& logging_;
        Monitor::AsyncLogger& logger_;
        ProgramLogBuilder programLogBuilder_;
        std::atomic<bool> fatalShutdownStarted_{false};
    };
}
