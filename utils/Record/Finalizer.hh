#pragma once

#include <chrono>
#include <cstdlib>
#include <exception>
#include <memory>
#include <utility>

#include "Monitor.hh"
#include "Record/Writer.hh"

namespace Record {

    namespace {
        constexpr auto kFatalGracePeriod = std::chrono::seconds(10);
    }

    inline void Writer::bind(Monitor::AsyncLogger&        logger,
                             std::function<std::string()> programLog,
                             std::function<void()>         printStats,
                             std::function<void()>         listChanged,
                             std::function<void()>         preCloseHook)
    {
        logger_       = &logger;
        logging_      = &(logger.watch());
        programLog_   = std::move(programLog);
        printStats_   = std::move(printStats);
        listChanged_  = std::move(listChanged);
        preCloseHook_ = std::move(preCloseHook);

        logger_->setFatalStallHandler([this](const Monitor::RunSnapshot& snapshot) {
            fatalShutdown(snapshot);
        });
    }

    inline void Writer::finish(std::size_t eventCount) {
        auto barrier = std::make_shared<BarrierState>();
        std::exception_ptr error;

        try {
            pushFinish(FinishRequest{eventCount, barrier});
            waitBarrier(barrier);
        } catch (...) {
            error = std::current_exception();
        }

        if (scribe_.joinable()) scribe_.join();
        started_.store(false, std::memory_order_release);

        if (error) std::rethrow_exception(error);

        if (logging_ != nullptr && logger_ != nullptr) {
            logging_->elapsed = std::chrono::duration_cast<Config::uSeconds>(
                std::chrono::system_clock::now() - logging_->start);
            logger_->finish(*logging_, logging_->iEvent.load(std::memory_order_relaxed));
            Monitor::terminalReport(*this, *logging_, printStats_);
            Monitor::outputLog(*this, *logging_, programLog_ ? programLog_() : std::string{},
                               {}, printStats_, listChanged_, &logger_->pacingInfo());
        }
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

        const std::string programLog = programLog_ ? programLog_() : std::string{};
        Monitor::writeEmergencyLog(*this, *frozenLog, frozenSnapshot, programLog,
                                   "fatal-stall detected");

        bool completed = false;
        try {
            completed = fatalWrite(frozenLog->nEvents,
                                   std::chrono::duration_cast<std::chrono::milliseconds>(kFatalGracePeriod));
            if (completed && scribe_.joinable()) scribe_.join();
        } catch (...) {
            completed = false;
        }

        if (completed) {
            Monitor::outputLog(*this, *frozenLog, programLog, {}, printStats_, listChanged_,
                               &logger_->pacingInfo());
            std::_Exit(EXIT_FAILURE);
        }

        Monitor::writeEmergencyLog(*this, *frozenLog, frozenSnapshot, programLog,
                                   "fatal-stall fallback after timed-out write/log attempt");
        std::_Exit(EXIT_FAILURE);
    }

} // namespace Record
