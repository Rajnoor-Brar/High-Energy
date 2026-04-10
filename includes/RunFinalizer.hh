#pragma once

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <memory>
#include <thread>
#include <utility>

#include "Analysis.hh"
#include "Config.hh"
#include "Record.hh"

namespace RunFinalizer {
    inline constexpr auto FatalGracePeriod = std::chrono::seconds(10);

    template <typename PythiaT, typename RootArrayT, typename ProgramLogBuilder>
    class Controller {
      public:
        Controller(
            PythiaT& pythia,
            RootArrayT& histogramSets,
            Config::Root& root,
            Config::Log& logging,
            Record::AsyncLogger& logger,
            ProgramLogBuilder programLogBuilder
        )
            : pythia_(pythia),
              histogramSets_(histogramSets),
              root_(root),
              logging_(logging),
              logger_(logger),
              programLogBuilder_(std::move(programLogBuilder)) {}

        void installFatalStallHandler() {
            logger_.setFatalStallHandler([this](const Record::RunSnapshot& snapshot) {
                fatalShutdown(snapshot);
            });
        }

        void normalShutdown() {
            Analysis::wrapUp(histogramSets_, root_.outFile, root_.histScale, logging_.nEvents);
            logging_.elapsed = std::chrono::duration_cast<Config::uSeconds>(
                std::chrono::system_clock::now() - logging_.start
            );
            logger_.finish(logging_, logging_.iEvent.load());
            Record::terminalReport(pythia_, root_, logging_);
            Record::outputLog(pythia_, root_, logging_, programLogBuilder_());
        }

      private:
        void fatalShutdown(const Record::RunSnapshot& snapshot) {
            if (fatalShutdownStarted_.exchange(true)) {
                return;
            }

            Config::Log frozenLog = logging_;
            frozenLog.elapsed = std::chrono::duration_cast<Config::uSeconds>(
                std::chrono::system_clock::now() - logging_.start
            );

            Record::RunSnapshot frozenSnapshot = snapshot;
            frozenSnapshot.elapsed = frozenLog.elapsed;

            const std::string programLog = programLogBuilder_();
            Record::writeEmergencyLog(root_, frozenLog, frozenSnapshot, programLog, "fatal-stall detected");

            auto completed = std::make_shared<std::atomic<bool>>(false);
            std::thread([this, frozenLog, programLog, completed]() {
                Analysis::wrapUp(histogramSets_, root_.outFile, root_.histScale, frozenLog.nEvents);
                Record::outputLog(pythia_, root_, frozenLog, programLog);
                completed->store(true);
            }).detach();

            const auto deadline = std::chrono::steady_clock::now() + FatalGracePeriod;
            while (std::chrono::steady_clock::now() < deadline) {
                if (completed->load()) {
                    std::_Exit(EXIT_FAILURE);
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
            }

            Record::writeEmergencyLog(
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
        Record::AsyncLogger& logger_;
        ProgramLogBuilder programLogBuilder_;
        std::atomic<bool> fatalShutdownStarted_{false};
    };
}
