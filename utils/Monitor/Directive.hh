#pragma once

#include <algorithm>
#include <atomic>
#include <chrono>
#include <memory>
#include <mutex>
#include <optional>
#include <thread>
#include <utility>
#include <vector>

#include "TString.h"

#include "Monitor/Logger.hh"
#include "Monitor/Methods.hh"
#include "Monitor/Render.hh"
#include "Monitor/Report.hh"

namespace Monitor {

    inline std::size_t AsyncLogger::countEvent() {
        const std::size_t n = watch_.iEvent.fetch_add(1, std::memory_order_relaxed) + 1;

        // Phase 1 emits requests through the sink if set.  When unset,
        // this is a pure counter.  Phase 2 will wire Writer's watchdog
        // to consume the requests.
        if (watchSink_) {
            if (saveHeartbeat_ && pacing_.printInterval > 0
                    && (n % pacing_.printInterval) == 0)
            {
                Record::WatchRequest req;
                req.kind       = Record::WatchRequest::Kind::Heartbeat;
                req.eventIndex = n;
                watchSink_(std::move(req));
            }

            if (saveCheckpoints_ && checkpointInterval_ > 0
                    && (n % checkpointInterval_) == 0)
            {
                Record::WatchRequest req;
                req.kind       = Record::WatchRequest::Kind::Checkpoint;
                req.eventIndex = n;
                req.barrier    = std::make_shared<Record::BarrierState>();
                watchSink_(req);
                waitWatchBarrier(req.barrier);
            }
        }

        return n;
    }

    inline void AsyncLogger::publish(RunPhase phase,
                                     bool writeRunStat,
                                     bool forceRenderStatus,
                                     bool forceRenderBar)
    {
        RunSnapshot snapshot = makeSnapshot(watch_, phase);

        const std::size_t eventIndex = watch_.iEvent;
        const bool edgeEvent    = eventIndex == 1 || eventIndex == watch_.nEvents;
        const bool renderStatus = (pacing_.printInterval > 0 && eventIndex % pacing_.printInterval == 0)
                                  || edgeEvent || forceRenderStatus;
        const bool renderBar    = (pacing_.barInterval > 0 && eventIndex % pacing_.barInterval == 0)
                                  || edgeEvent || forceRenderBar;

        std::lock_guard<std::mutex> lock(mutex_);
        latestSnapshot_ = std::move(snapshot);

        const PendingActions incoming{renderStatus, renderBar, writeRunStat};
        if (renderStatus || renderBar || writeRunStat) {
            mergePending(incoming);
            condition_.notify_one();
        }
    }

    inline void AsyncLogger::publishThreadStats(int workerIndex,
                                                ThreadPhase phase,
                                                std::size_t eventIndex,
                                                bool callbackCompleted)
    {
        // docs/WriterMT.md: when [monitor].save_log_threads is false,
        // publishes are discarded and the calling thread continues.
        // Cheap path; no lock acquired.
        if (!saveLogThreads_) return;
        if (workerIndex < 0) return;

        std::lock_guard<std::mutex> lock(mutex_);
        ThreadSnapshot& snapshot     = threadSnapshots_[workerIndex];
        snapshot.workerIndex         = workerIndex;
        snapshot.phase               = phase;
        snapshot.eventIndex          = eventIndex;
        snapshot.lastUpdateTime      = std::chrono::system_clock::now();

        if (callbackCompleted) ++snapshot.callbacksCompleted;

        dirtyThreadSnapshots_.push_back(snapshot);
        condition_.notify_one();
    }

    inline Config::uSeconds AsyncLogger::terminalIdleFor(const RunSnapshot& snapshot,
                                                         const Config::TimePoint& now) const {
        return std::chrono::duration_cast<Config::uSeconds>(now - snapshot.lastUpdateTime);
    }

    inline bool AsyncLogger::isTerminalStalled(const RunSnapshot& snapshot,
                                               const Config::TimePoint& now) const {
        return snapshot.phase != RunPhase::Starting
            && snapshot.phase != RunPhase::Finished
            && terminalIdleFor(snapshot, now)
                   >= std::chrono::duration_cast<Config::uSeconds>(programStallThreshold_);
    }

    inline bool AsyncLogger::isFatalStalled(const RunSnapshot& snapshot,
                                            const Config::TimePoint& now) const {
        if (snapshot.phase == RunPhase::Starting || snapshot.phase == RunPhase::Finished) return false;
        const Config::uSeconds fatalThreshold =
            std::chrono::duration_cast<Config::uSeconds>(programStallThreshold_) * 5;
        return terminalIdleFor(snapshot, now) >= fatalThreshold;
    }

    inline void AsyncLogger::runLoop() {
        using SteadyClock = std::chrono::steady_clock;

        auto advanceDeadline = [](auto& next, auto interval) {
            const auto now = SteadyClock::now();
            while (next <= now) next += interval;
        };

        std::unique_lock<std::mutex> lock(mutex_);
        auto nextRunStatWrite    = SteadyClock::now() + heartbeat_interval_;
        auto nextTerminalRefresh = SteadyClock::now() + terminalRefreshInterval_;

        while (true) {
            const auto hasPendingWork = [&] {
                return stopRequested_ || pendingActions_.has_value() || !dirtyThreadSnapshots_.empty();
            };

            if (initialized_) {
                condition_.wait_until(lock, std::min(nextRunStatWrite, nextTerminalRefresh), hasPendingWork);
            } else {
                condition_.wait(lock, [&] { return initialized_ || hasPendingWork(); });
            }

            const auto now              = SteadyClock::now();
            const auto wallNow          = std::chrono::system_clock::now();
            const bool runStatDeadline  = now >= nextRunStatWrite;
            const bool terminalDeadline = now >= nextTerminalRefresh;

            std::optional<PendingActions> actions;
            std::optional<RunSnapshot>    actionSnapshot;
            std::optional<RunSnapshot>    periodicSnapshot;
            std::optional<RunSnapshot>    fatalSnapshot;
            std::vector<ThreadSnapshot>   dirtyThreadSnapshots;
            Config::uSeconds              heartbeatInterval       = heartbeat_interval_;
            Config::Seconds               terminalRefreshInterval = terminalRefreshInterval_;
            bool                          shouldExit = false;
            FatalStallHandler             fatalHandler;

            if (pendingActions_.has_value() && latestSnapshot_.has_value()) {
                actions        = *pendingActions_;
                actionSnapshot = *latestSnapshot_;
                pendingActions_.reset();
            }

            if (initialized_ && latestSnapshot_.has_value() && (runStatDeadline || terminalDeadline))
                periodicSnapshot = *latestSnapshot_;

            if (initialized_
                && !fatalStallTriggered_
                && latestSnapshot_.has_value()
                && fatalStallHandler_
                && (runStatDeadline || terminalDeadline)
                && isFatalStalled(*latestSnapshot_, wallNow))
            {
                fatalSnapshot = *latestSnapshot_;
                fatalSnapshot->fatalStall      = true;
                fatalSnapshot->fatalReason     = "No progress update exceeded fatal stall threshold";
                fatalSnapshot->stallDuration   = terminalIdleFor(*latestSnapshot_, wallNow);
                fatalSnapshot->stallThreshold  = programStallThreshold_;
                fatalSnapshot->stallMultiplier = 5;
                fatalHandler                   = fatalStallHandler_;
                fatalStallTriggered_           = true;
            }

            dirtyThreadSnapshots.swap(dirtyThreadSnapshots_);
            shouldExit = stopRequested_ && !actions.has_value() && dirtyThreadSnapshots.empty();
            lock.unlock();

            const bool wroteImmediateRunStat = actions.has_value() && actions->writeRunStat && actionSnapshot.has_value();
            const bool renderedImmediately   = actions.has_value() && actionSnapshot.has_value()
                                               && (actions->renderStatus || actions->renderBar);

            if (actions.has_value() && actionSnapshot.has_value())
                processUpdate(*actionSnapshot, *actions);

            if (periodicSnapshot.has_value()) {
                if (runStatDeadline && !wroteImmediateRunStat) flushRunStat(*periodicSnapshot);
                if (terminalDeadline && !renderedImmediately) heartbeatTerminal(*periodicSnapshot);
            }

            if (fatalSnapshot.has_value()) {
                flushRunStat(*fatalSnapshot);
                std::lock_guard<std::mutex> terminalLock(terminalMutex());
                initializeTerminal();
                renderStatusLine(*fatalSnapshot);
                if (progressBarVisible_) renderProgressBar(fatalSnapshot->progress);
            }

            for (const auto& snap : dirtyThreadSnapshots) writeThreadStats(snap);

            if (fatalSnapshot.has_value() && fatalHandler)
                fatalHandler(*fatalSnapshot);

            if (shouldExit) break;

            if (runStatDeadline)  advanceDeadline(nextRunStatWrite,    heartbeatInterval);
            if (terminalDeadline) advanceDeadline(nextTerminalRefresh, terminalRefreshInterval);

            lock.lock();
        }
    }

    inline void AsyncLogger::processUpdate(const RunSnapshot& snapshot, const PendingActions& actions) {
        if (actions.writeRunStat) flushRunStat(snapshot);

        if (!(actions.renderStatus || actions.renderBar)) return;

        std::lock_guard<std::mutex> terminalLock(terminalMutex());
        initializeTerminal();
        if (actions.renderStatus) renderStatusLine(snapshot);
        if (actions.renderBar) {
            renderProgressBar(snapshot.progress);
            progressBarVisible_ = true;
        }
    }

    inline void AsyncLogger::flushRunStat(const RunSnapshot& snapshot) const {
        if (runStatPath_.Length() == 0) return;
        writeTextFile(runStatPath_, runStatString(snapshot, std::chrono::system_clock::now()));
    }

    inline void AsyncLogger::heartbeatTerminal(const RunSnapshot& snapshot) {
        std::lock_guard<std::mutex> terminalLock(terminalMutex());
        if (!terminalInitialized_) return;
        renderStatusLine(snapshot);
        if (progressBarVisible_) renderProgressBar(snapshot.progress);
    }

    inline void AsyncLogger::writeThreadStats(const ThreadSnapshot& snapshot) const {
        if (threadStatDirectory_.Length() == 0 || snapshot.workerIndex < 0) return;
        const TString path =
            Form("%sThread_%02d.log", threadStatDirectory_.Data(), snapshot.workerIndex);
        writeTextFile(path, threadStatString(snapshot, std::chrono::system_clock::now()));
    }

    inline void AsyncLogger::mergePending(const PendingActions& incoming) {
        if (pendingActions_.has_value()) {
            pendingActions_->renderStatus |= incoming.renderStatus;
            pendingActions_->renderBar    |= incoming.renderBar;
            pendingActions_->writeRunStat |= incoming.writeRunStat;
        } else {
            pendingActions_ = incoming;
        }
    }

    // docs/WriterMT.md Phase 1: block the calling thread until the
    // watchdog signals completion of a Checkpoint/Finalize/Fatal
    // WatchRequest. Phase 1 only the Checkpoint path uses this.
    inline void AsyncLogger::waitWatchBarrier(const std::shared_ptr<Record::BarrierState>& barrier) {
        if (!barrier) return;
        std::unique_lock<std::mutex> lock(barrier->mutex);
        barrier->cv.wait(lock, [&] { return barrier->done; });
        if (barrier->exception) std::rethrow_exception(barrier->exception);
    }

}
