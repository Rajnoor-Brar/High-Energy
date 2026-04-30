#pragma once

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <functional>
#include <memory>
#include <optional>
#include <thread>

#include "Config.hh"
#include "Monitor.hh"
#include "Record/Histogram.hh"
#include "Record/Meta.hh"
#include "TString.h"

namespace Record {

    inline constexpr auto FatalGracePeriod = std::chrono::seconds(10);

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

    template <typename RootArrayT, typename ProgramLogBuilder>
    class FinalizerController {
      public:
        FinalizerController(RootArrayT& histogramSets,
                            Config::Register& root, Config::Watch& logging,
                            Monitor::AsyncLogger& logger,
                            ProgramLogBuilder programLogBuilder,
                            std::function<void()> printStats = {},
                            std::function<void()> listChangedSettings = {},
                            std::function<void()> preCloseHook = {})
            : histogramSets_(histogramSets),
              root_(root), logging_(logging), logger_(logger),
              programLogBuilder_(std::move(programLogBuilder)),
              printStats_(std::move(printStats)),
              listChangedSettings_(std::move(listChangedSettings)),
              preCloseHook_(std::move(preCloseHook)) {}

        void installFatalStallHandler() {
            logger_.setFatalStallHandler([this](const Monitor::RunSnapshot& snapshot) {
                fatalShutdown(snapshot);
            });
        }

        void setMeta(Record::Meta::Record meta) { meta_ = std::move(meta); }

        void normalShutdown() {
            writeAll(histogramSets_, root_.histScale, logging_.nEvents);
            if (meta_.has_value() && root_.outFile != nullptr)
                Record::Meta::writeAbout(root_.outFile, *meta_);
            if (root_.outFile != nullptr) {
                if (preCloseHook_) preCloseHook_();
                root_.outFile->Write("", TObject::kOverwrite);
                root_.outFile->Close();
            }
            logging_.elapsed = std::chrono::duration_cast<Config::uSeconds>(
                std::chrono::system_clock::now() - logging_.start);
            logger_.finish(logging_, logging_.iEvent.load());
            Monitor::terminalReport(root_, logging_, printStats_);
            Monitor::outputLog(root_, logging_, programLogBuilder_(), {}, printStats_, listChangedSettings_);
        }

      private:
        void fatalShutdown(const Monitor::RunSnapshot& snapshot) {
            if (fatalShutdownStarted_.exchange(true)) return;
            auto frozenLog = std::shared_ptr<Config::Watch>(logging_.freeze());
            frozenLog->elapsed = std::chrono::duration_cast<Config::uSeconds>(
                std::chrono::system_clock::now() - logging_.start);
            Monitor::RunSnapshot frozenSnapshot = snapshot;
            frozenSnapshot.elapsed = frozenLog->elapsed;

            const std::string programLog = programLogBuilder_();
            Monitor::writeEmergencyLog(root_, *frozenLog, frozenSnapshot, programLog, "fatal-stall detected");

            auto completed = std::make_shared<std::atomic<bool>>(false);
            std::thread([this, frozenLog, programLog, completed]() {
                wrapUp(histogramSets_, root_.outFile, root_.histScale, frozenLog->nEvents);
                Monitor::outputLog(root_, *frozenLog, programLog, {}, printStats_, listChangedSettings_);
                completed->store(true);
            }).detach();

            const auto deadline = std::chrono::steady_clock::now() + FatalGracePeriod;
            while (std::chrono::steady_clock::now() < deadline) {
                if (completed->load()) std::_Exit(EXIT_FAILURE);
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
            }
            Monitor::writeEmergencyLog(root_, *frozenLog, frozenSnapshot, programLog,
                                       "fatal-stall fallback after timed-out wrapUp/log attempt");
            std::_Exit(EXIT_FAILURE);
        }

        RootArrayT&           histogramSets_;
        Config::Register&     root_;
        Config::Watch&        logging_;
        Monitor::AsyncLogger& logger_;
        ProgramLogBuilder     programLogBuilder_;
        std::function<void()> printStats_;
        std::function<void()> listChangedSettings_;
        std::function<void()> preCloseHook_;
        std::atomic<bool>     fatalShutdownStarted_{false};
        std::optional<Record::Meta::Record> meta_;
    };
}
