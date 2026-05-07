#pragma once

// ── Record/Finalizer.hh ──────────────────────────────────────────────────────
// Inline definitions for Writer::bind / shutdown / checkpoint /
// installFatalStallHandler / fatalShutdown.
//
// Lives in a separate header to break the include cycle:
//   Monitor/Logger.hh → Record/Writer.hh  (Logger::start takes const Writer&)
//   Record/Writer.hh  ↛ Monitor.hh        (would be circular)
//
// Include Record.hh (umbrella) to get these definitions in addition to the
// Writer class declarations. Writer.hh alone provides only declarations.

#include <chrono>
#include <cstdlib>
#include <thread>

#include "Monitor.hh"          // AsyncLogger, terminalReport, outputLog, writeEmergencyLog
#include "Record/Histogram.hh" // writeAll, writeToDir
#include "Record/Writer.hh"    // Writer class (already transitively included; explicit for clarity)
#include "TFile.h"

namespace Record {

    namespace {
        constexpr auto kFatalGracePeriod = std::chrono::seconds(10);
    }

    inline void Writer::bind(Monitor::AsyncLogger&        logger,
                              Config::Watch&               logging,
                              std::function<std::string()> programLog,
                              std::function<void()>         printStats,
                              std::function<void()>         listChanged,
                              std::function<void()>         preCloseHook)
    {
        logger_       = &logger;
        logging_      = &logging;
        programLog_   = std::move(programLog);
        printStats_   = std::move(printStats);
        listChanged_  = std::move(listChanged);
        preCloseHook_ = std::move(preCloseHook);
    }

    template <typename RootArrayT>
    inline void Writer::installFatalStallHandler(RootArrayT& sets) {
        emergencyWriteFn_ = [this, &sets](std::size_t nEvt) {
            writeAll(sets, hist_.histScale, nEvt);
            if (outFile_ != nullptr) {
                outFile_->Close();
                outFile_ = nullptr;
            }
        };
        if (logger_ != nullptr) {
            logger_->setFatalStallHandler([this](const Monitor::RunSnapshot& snapshot) {
                fatalShutdown(snapshot);
            });
        }
    }

    template <typename RootArrayT>
    inline void Writer::shutdown(RootArrayT& sets) {
        if (logging_ == nullptr || logger_ == nullptr) return;
        writeAll(sets, hist_.histScale, logging_->nEvents);
        if (outFile_ != nullptr) {
            Meta::writeAbout(outFile_, meta_);
            if (preCloseHook_) preCloseHook_();
            outFile_->Write("", TObject::kOverwrite);
            outFile_->Close();
            delete outFile_;
            outFile_ = nullptr;
        }
        logging_->elapsed = std::chrono::duration_cast<Config::uSeconds>(
            std::chrono::system_clock::now() - logging_->start);
        logger_->finish(*logging_, logging_->iEvent.load());
        Monitor::terminalReport(*this, *logging_, printStats_);
        Monitor::outputLog(*this, *logging_, programLog_(), {}, printStats_, listChanged_,
                           &logger_->pacingInfo());
    }

    template <typename RootArrayT>
    inline void Writer::checkpoint(RootArrayT& sets, std::size_t eventIndex) {
        if (logging_ == nullptr) return;
        TFile cpFile(paths_.checkpointOutName.Data(), "RECREATE");
        if (cpFile.IsOpen()) {
            for (auto& obj : sets) {
                if (obj.dir == nullptr) continue;
                TDirectory* cpDir = cpFile.mkdir(obj.dir->GetName());
                writeToDir(obj, cpDir, hist_.histScale, eventIndex, true);
            }
            cpFile.Write("", TObject::kOverwrite);
            cpFile.Close();
        }
        Monitor::outputLog(*this, *logging_, programLog_(),
                           paths_.checkpointLogName, printStats_, listChanged_,
                           &logger_->pacingInfo());
    }

    inline void Writer::fatalShutdown(const Monitor::RunSnapshot& snapshot) {
        if (fatalShutdownStarted_.exchange(true)) return;

        auto frozenLog = std::shared_ptr<Config::Watch>(logging_->freeze());
        frozenLog->elapsed.store(
            std::chrono::duration_cast<Config::uSeconds>(
                std::chrono::system_clock::now() - logging_->start),
            std::memory_order_relaxed);
        Monitor::RunSnapshot frozenSnapshot = snapshot;
        frozenSnapshot.elapsed = frozenLog->elapsed.load(std::memory_order_relaxed);

        const std::string programLog = programLog_();
        Monitor::writeEmergencyLog(*this, *frozenLog, frozenSnapshot, programLog,
                                   "fatal-stall detected");

        auto completed = std::make_shared<std::atomic<bool>>(false);
        std::thread([this, frozenLog, programLog, completed]() {
            if (emergencyWriteFn_) emergencyWriteFn_(frozenLog->nEvents);
            Monitor::outputLog(*this, *frozenLog, programLog, {}, printStats_, listChanged_,
                               &logger_->pacingInfo());
            completed->store(true);
        }).detach();

        const auto deadline = std::chrono::steady_clock::now() + kFatalGracePeriod;
        while (std::chrono::steady_clock::now() < deadline) {
            if (completed->load()) std::_Exit(EXIT_FAILURE);
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
        Monitor::writeEmergencyLog(*this, *frozenLog, frozenSnapshot, programLog,
                                   "fatal-stall fallback after timed-out write/log attempt");
        std::_Exit(EXIT_FAILURE);
    }

} // namespace Record
