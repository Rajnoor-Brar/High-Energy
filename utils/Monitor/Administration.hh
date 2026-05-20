#pragma once

#include <atomic>
#include <chrono>
#include <mutex>
#include <string>
#include <thread>
#include <utility>

#include "Record/Writer.hh"
#include "Monitor/Logger.hh"
#include "Monitor/Methods.hh"
#include "Monitor/Render.hh"

namespace Monitor {

    inline AsyncLogger::AsyncLogger(bool print) { start(print); }

    inline AsyncLogger::~AsyncLogger() { stop(); }

    inline Config::Watch& AsyncLogger::watch() { return watch_; }

    inline const Config::Watch& AsyncLogger::watch() const { return watch_; }

    inline const PacingInfo& AsyncLogger::pacingInfo() const { return pacing_; }

    inline std::size_t AsyncLogger::checkInterval() const { return pacing_.checkInterval; }

    inline void AsyncLogger::configurePacing(PacingInfo pacing) { pacing_ = std::move(pacing); }

    inline void AsyncLogger::configureWatchEmission(bool saveHeartbeat,
                                                    bool saveCheckpoints,
                                                    std::size_t checkpointInterval)
    {
        saveHeartbeat_      = saveHeartbeat;
        saveCheckpoints_    = saveCheckpoints;
        checkpointInterval_ = checkpointInterval > 0 ? checkpointInterval : 100000;
    }

    inline void AsyncLogger::configureArtifactEmission(bool saveLogThreads, bool saveFinalLog) {
        saveLogThreads_ = saveLogThreads;
        saveFinalLog_   = saveFinalLog;
    }

    inline bool AsyncLogger::saveLogThreads() const { return saveLogThreads_; }

    inline bool AsyncLogger::saveFinalLog() const { return saveFinalLog_; }

    inline bool AsyncLogger::saveCheckpoints() const { return saveCheckpoints_; }

    inline bool AsyncLogger::saveHeartbeat() const { return saveHeartbeat_; }

    inline void AsyncLogger::bindWatchSink(WatchSink sink) { watchSink_ = std::move(sink); }

    inline void AsyncLogger::markConfiguring(const std::string& configPath, bool trueTimeAtConfig) {
        RunSnapshot snapshot;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            preserveConfigStart_ = trueTimeAtConfig;
            if (preserveConfigStart_) watch_.start = std::chrono::system_clock::now();

            snapshot = makeSnapshot(watch_, RunPhase::Configuring);
            snapshot.eta = configPath;
            latestSnapshot_ = snapshot;
        }

        std::lock_guard<std::mutex> terminalLock(terminalMutex());
        initializeTerminal();
        renderStatusLine(snapshot);
    }

    inline void AsyncLogger::start(bool print) {
        stop();
        RunSnapshot bootSnapshot;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            runStatPath_             = "";
            threadStatDirectory_     = "";
            actionQueue_.clear();
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

    inline void AsyncLogger::initialise(const Record::Writer& writer) {
        if (!worker_.joinable()) start(false);
        {
            std::lock_guard<std::mutex> lock(mutex_);
            const Record::Paths& paths = writer.paths();
            runStatPath_             = paths.runStatName;
            threadStatDirectory_     = paths.threadStatDirectory;
            actionQueue_.clear();
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
            pushAction(*latestSnapshot_, PendingActions{RenderStatus, DontRenderBar, WriteRunStat});
        }
        condition_.notify_one();
    }

    inline void AsyncLogger::finish(const Config::Watch& logging, std::size_t /*eventIndex*/) {
        RunSnapshot snapshot = makeSnapshot(logging, RunPhase::Finished);
        {
            std::lock_guard<std::mutex> lock(mutex_);
            latestSnapshot_ = std::move(snapshot);
            pushAction(*latestSnapshot_, PendingActions{RenderStatus, RenderBar, WriteRunStat});
            stopRequested_  = true;
        }
        condition_.notify_one();
        stop();
    }

    inline void AsyncLogger::setFatalStallHandler(FatalStallHandler handler) {
        std::lock_guard<std::mutex> lock(mutex_);
        fatalStallHandler_ = std::move(handler);
    }

    inline void AsyncLogger::stop() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stopRequested_ = true;
        }
        condition_.notify_one();
        if (worker_.joinable()) worker_.join();
    }

}
