#pragma once

#include <condition_variable>
#include <functional>
#include <map>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <vector>

#include "TString.h"
#include "Config.hh"
#include "Record/Writer.hh"
#include "Utility.hh"
#include "Monitor/Snapshot.hh"
#include "Monitor/Render.hh"

namespace Monitor {

    class AsyncLogger {
      public:
        using FatalStallHandler = std::function<void(const RunSnapshot&)>;

        explicit AsyncLogger(bool print = true) { start(print); }
        ~AsyncLogger() { stop(); }

        Config::Watch&       watch()       { return watch_; }
        const Config::Watch& watch() const { return watch_; }

        const PacingInfo& pacingInfo()    const { return pacing_; }
        std::size_t       checkInterval() const { return pacing_.checkInterval; }

        void configurePacing(PacingInfo pacing) { pacing_ = std::move(pacing); }

        void markConfiguring(const std::string& configPath, bool trueTimeAtConfig = false) {
            RunSnapshot snapshot;
            {
                std::lock_guard<std::mutex> lock(mutex_);
                preserveConfigStart_ = trueTimeAtConfig;
                if (preserveConfigStart_) watch_.start = std::chrono::system_clock::now();

                snapshot     = makeSnapshot(watch_, RunPhase::Configuring);
                snapshot.eta = configPath;
                latestSnapshot_ = snapshot;
            }

            std::lock_guard<std::mutex> terminalLock(terminalMutex());
            initializeTerminal();
            renderStatusLine(snapshot);
        }

        void start(bool print = true) {
            stop();
            RunSnapshot bootSnapshot;
            {
                std::lock_guard<std::mutex> lock(mutex_);
                runStatPath_             = "";
                threadStatDirectory_     = "";
                pendingActions_.reset();
                latestSnapshot_.reset();
                threadSnapshots_.clear();
                dirtyThreadSnapshots_.clear();
                initialized_             = false;
                preserveConfigStart_     = false;
                stopRequested_           = false;
                fatalStallTriggered_     = false;
                terminalInitialized_     = false;
                progressBarVisible_      = false;
                heartbeat_interval_      = pacing_.heartbeatMs     > Config::uSeconds(0)
                                            ? pacing_.heartbeatMs     : Config::uSeconds(1000);
                terminalRefreshInterval_ = pacing_.terminalRefresh > Config::Seconds(0)
                                            ? pacing_.terminalRefresh : Config::Seconds(300);
                programStallThreshold_   = pacing_.stallThreshold  > Config::Seconds(0)
                                            ? pacing_.stallThreshold  : Config::Seconds(300);
                watch_.start             = std::chrono::system_clock::now();

                RunSnapshot snapshot = makeSnapshot(watch_, RunPhase::Starting);
                snapshot.eta         = "Booting";
                bootSnapshot         = snapshot;
                latestSnapshot_      = std::move(snapshot);
            }
            if (print) {
                std::lock_guard<std::mutex> terminalLock(terminalMutex());
                initializeTerminal();
                renderStatusLine(bootSnapshot);
            }
            worker_ = std::thread(&AsyncLogger::runLoop, this);
            condition_.notify_one();
        }

        void initialise(const Record::Writer& writer) {
            if (!worker_.joinable()) start(false);
            {
                std::lock_guard<std::mutex> lock(mutex_);
                const Record::Paths& paths = writer.paths();
                runStatPath_             = paths.runStatName;
                threadStatDirectory_     = paths.threadStatDirectory;
                pendingActions_.reset();
                latestSnapshot_.reset();
                threadSnapshots_.clear();
                dirtyThreadSnapshots_.clear();
                initialized_             = true;
                stopRequested_           = false;
                fatalStallTriggered_     = false;
                heartbeat_interval_      = pacing_.heartbeatMs     > Config::uSeconds(0)
                                            ? pacing_.heartbeatMs     : Config::uSeconds(1000);
                terminalRefreshInterval_ = pacing_.terminalRefresh > Config::Seconds(0)
                                            ? pacing_.terminalRefresh : Config::Seconds(300);
                programStallThreshold_   = pacing_.stallThreshold  > Config::Seconds(0)
                                            ? pacing_.stallThreshold  : Config::Seconds(300);
                if (!preserveConfigStart_)
                    watch_.start = std::chrono::system_clock::now();
                RunSnapshot snapshot = makeSnapshot(watch_, RunPhase::Initialisation);
                snapshot.eta         = paths.fileTitle.Data();
                latestSnapshot_      = std::move(snapshot);
                pendingActions_      = PendingActions{RenderStatus, DontRenderBar, WriteRunStat};
            }
            condition_.notify_one();
        }

        void publish(
            const Config::Watch& logging,
            RunPhase           phase,
            bool               writeRunStat      = false,
            bool               forceRenderStatus = false,
            bool               forceRenderBar    = false
        ) {
            RunSnapshot snapshot = makeSnapshot(logging, phase);

            const std::size_t eventIndex = logging.iEvent;
            const bool edgeEvent    = eventIndex == 1 || eventIndex == logging.nEvents;
            const bool renderStatus = (pacing_.printInterval > 0 && eventIndex % pacing_.printInterval == 0)
                                      || edgeEvent || forceRenderStatus;
            const bool renderBar    = (pacing_.barInterval   > 0 && eventIndex % pacing_.barInterval   == 0)
                                      || edgeEvent || forceRenderBar;

            std::lock_guard<std::mutex> lock(mutex_);
            latestSnapshot_ = std::move(snapshot);

            const PendingActions incoming{renderStatus, renderBar, writeRunStat};
            if (incoming.any()) {
                mergePending(incoming);
                condition_.notify_one();
            }
        }

        void publishThreadStats(
            int         workerIndex,
            ThreadPhase phase,
            std::size_t eventIndex,
            bool        callbackCompleted = false
        ) {
            if (workerIndex < 0) return;

            std::lock_guard<std::mutex> lock(mutex_);
            ThreadSnapshot& snapshot    = threadSnapshots_[workerIndex];
            snapshot.workerIndex        = workerIndex;
            snapshot.phase              = phase;
            snapshot.eventIndex         = eventIndex;
            snapshot.lastUpdateTime     = std::chrono::system_clock::now();

            if (callbackCompleted) ++snapshot.callbacksCompleted;

            dirtyThreadSnapshots_.push_back(snapshot);
            condition_.notify_one();
        }

        void finish(const Config::Watch& logging, std::size_t /*eventIndex*/) {
            RunSnapshot snapshot = makeSnapshot(logging, RunPhase::Finished);
            {
                std::lock_guard<std::mutex> lock(mutex_);
                latestSnapshot_ = std::move(snapshot);
                mergePending(PendingActions{RenderStatus, RenderBar, WriteRunStat});
                stopRequested_  = true;
            }
            condition_.notify_one();
            stop();
        }

        void setFatalStallHandler(FatalStallHandler handler) {
            std::lock_guard<std::mutex> lock(mutex_);
            fatalStallHandler_ = std::move(handler);
        }

        void stop() {
            {
                std::lock_guard<std::mutex> lock(mutex_);
                stopRequested_ = true;
            }
            condition_.notify_one();
            if (worker_.joinable()) worker_.join();
        }

      private:
        Config::uSeconds terminalIdleFor(const RunSnapshot& snapshot, const Config::TimePoint& now) const {
            return std::chrono::duration_cast<Config::uSeconds>(now - snapshot.lastUpdateTime);
        }

        bool isTerminalStalled(const RunSnapshot& snapshot, const Config::TimePoint& now) const {
            return snapshot.phase != RunPhase::Starting
                && snapshot.phase != RunPhase::Finished
                && terminalIdleFor(snapshot, now)
                       >= std::chrono::duration_cast<Config::uSeconds>(programStallThreshold_);
        }

        bool isFatalStalled(const RunSnapshot& snapshot, const Config::TimePoint& now) const {
            if (snapshot.phase == RunPhase::Starting || snapshot.phase == RunPhase::Finished) return false;
            const Config::uSeconds fatalThreshold =
                std::chrono::duration_cast<Config::uSeconds>(programStallThreshold_) * FatalStallMultiplier;
            return terminalIdleFor(snapshot, now) >= fatalThreshold;
        }

        void renderStatusLine(const RunSnapshot& snapshot) {
            const std::size_t percent    = snapshot.nEvents > 0
                ? static_cast<std::size_t>(100.0 * snapshot.progress) : 0;
            const std::size_t eventWidth = Utility::numberFormat(snapshot.nEvents, 0).size();

            std::cout << "\033[3F\033[2K";

            if (snapshot.fatalStall) {
                std::cout << "\033[E\r\033[2K"
                          << "\t\033[31;1m Fatal stall\033[0m after "
                          << Utility::durationString(snapshot.stallDuration, true)
                          << "\033[E\033[2K\t Last event: "
                          << Utility::numberFormat(snapshot.eventIndex, eventWidth)
                          << " / " << Utility::numberFormat(snapshot.nEvents, 0)
                          << "\033[E\033[2K\t " << snapshot.fatalReason;
            } else if (snapshot.phase == RunPhase::Starting) {
                std::cout << "\033[E\033[2K"
                          << "\t\033[34;1m Booting... \033[0m\033[E\033[2K";
            } else if (snapshot.phase == RunPhase::Configuring) {
                std::cout << "\033[E\033[2K"
                          << "\t\033[34;1m Configurig from " << snapshot.eta
                          << " \033[0m\033[E\033[2K";
            } else if (snapshot.phase == RunPhase::Initialisation) {
                std::cout << "\033[E\033[2K"
                          << "\t\033[34;1m Initializing " << snapshot.eta << "... \033[0m\033[E\033[2K";
            } else if (snapshot.phase == RunPhase::Finished) {
                std::cout << "\033[E\r\033[2K"
                          << "\t\033[32;1m Finished\033[0m"
                          << "\033[E\033[2K";
            } else {
                const auto now     = std::chrono::system_clock::now();
                const bool stalled = isTerminalStalled(snapshot, now);
                std::cout << "\t Events processed : \033[32;1m"
                          << Utility::numberFormat(snapshot.eventIndex, eventWidth) << "\033[0m"
                          << " out of " << Utility::numberFormat(snapshot.nEvents, 0) << "  |  "
                          << std::setw(2) << percent << "% "
                          << "\033[E\033[2K\t ETA: " << snapshot.eta
                          << "\033[E\033[2K\t"
                          << (stalled
                                  ? std::string("\033[31;1mStalled for ")
                                        + Utility::durationString(terminalIdleFor(snapshot, now))
                                        + "\033[0m"
                                  : "");
            }
            std::cout << "\033[E\r" << std::flush;
        }

        void runLoop() {
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
                Config::uSeconds  heartbeatInterval      = heartbeat_interval_;
                Config::Seconds   terminalRefreshInterval = terminalRefreshInterval_;
                bool              shouldExit = false;
                FatalStallHandler fatalHandler;

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
                    fatalSnapshot->fatalStall     = true;
                    fatalSnapshot->fatalReason    = "No progress update exceeded fatal stall threshold";
                    fatalSnapshot->stallDuration  = terminalIdleFor(*latestSnapshot_, wallNow);
                    fatalSnapshot->stallThreshold = programStallThreshold_;
                    fatalSnapshot->stallMultiplier = FatalStallMultiplier;
                    fatalHandler           = fatalStallHandler_;
                    fatalStallTriggered_   = true;
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
                    if (runStatDeadline  && !wroteImmediateRunStat) flushRunStat(*periodicSnapshot);
                    if (terminalDeadline && !renderedImmediately)   heartbeatTerminal(*periodicSnapshot);
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

        void processUpdate(const RunSnapshot& snapshot, const PendingActions& actions) {
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

        void flushRunStat(const RunSnapshot& snapshot) const {
            if (runStatPath_.Length() == 0) return;
            writeTextFile(runStatPath_, runStatString(snapshot, std::chrono::system_clock::now()));
        }

        void heartbeatTerminal(const RunSnapshot& snapshot) {
            std::lock_guard<std::mutex> terminalLock(terminalMutex());
            if (!terminalInitialized_) return;
            renderStatusLine(snapshot);
            if (progressBarVisible_) renderProgressBar(snapshot.progress);
        }

        void writeThreadStats(const ThreadSnapshot& snapshot) const {
            if (threadStatDirectory_.Length() == 0 || snapshot.workerIndex < 0) return;
            const TString path =
                Form("%sThread_%02d.log", threadStatDirectory_.Data(), snapshot.workerIndex);
            writeTextFile(path, threadStatString(snapshot, std::chrono::system_clock::now()));
        }

        void initializeTerminal() {
            if (terminalInitialized_) return;
            std::cout << "\n\n\n" << std::flush;
            terminalInitialized_ = true;
        }

        void mergePending(const PendingActions& incoming) {
            if (pendingActions_.has_value()) pendingActions_->merge(incoming);
            else                             pendingActions_ = incoming;
        }

        Config::Watch                 watch_;
        PacingInfo                    pacing_;

        TString                       runStatPath_             = "";
        TString                       threadStatDirectory_     = "";
        std::mutex                    mutex_;
        std::condition_variable       condition_;
        std::optional<PendingActions> pendingActions_;
        std::optional<RunSnapshot>    latestSnapshot_;
        std::map<int, ThreadSnapshot> threadSnapshots_;
        std::vector<ThreadSnapshot>   dirtyThreadSnapshots_;
        std::thread                   worker_;
        Config::uSeconds              heartbeat_interval_      = Config::uSeconds(1000);
        Config::Seconds               terminalRefreshInterval_ = Config::Seconds(300);
        Config::Seconds               programStallThreshold_   = Config::Seconds(300);
        bool                          stopRequested_           = false;
        bool                          initialized_             = false;
        bool                          preserveConfigStart_     = false;
        bool                          fatalStallTriggered_     = false;
        bool                          terminalInitialized_     = false;
        bool                          progressBarVisible_      = false;
        FatalStallHandler             fatalStallHandler_;
    };
}
