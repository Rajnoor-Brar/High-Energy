#pragma once

#include <condition_variable>
#include <cstddef>
#include <deque>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "TString.h"

#include "Config/Types.hh"
#include "Record/Requests.hh"
#include "Monitor/Types.hh"

namespace Record {
    class Writer;
}

namespace Monitor {

    class AsyncLogger {
      public:
        using FatalStallHandler = std::function<void(const RunSnapshot&)>;
        // WatchSink — pluggable callback for WatchRequest emission; Phase 2 wires to Writer::signalWatch.
        using WatchSink = std::function<void(Record::WatchRequest)>;

        explicit AsyncLogger(bool print = true);
        ~AsyncLogger();

        Config::Watch&       watch();
        const Config::Watch& watch() const;

        const PacingInfo& pacingInfo() const;
        std::size_t       checkInterval() const;

        void configurePacing(PacingInfo pacing);

        // Configures which WatchRequest kinds are emitted and at what cadences.
        void configureWatchEmission(bool saveHeartbeat,
                                    bool saveCheckpoints,
                                    std::size_t checkpointInterval);

        // Configures non-watch artifact emission (thread stats, final log).
        void configureArtifactEmission(bool saveLogThreads, bool saveFinalLog);

        bool saveLogThreads() const;
        bool saveFinalLog() const;
        bool saveCheckpoints() const;
        bool saveHeartbeat() const;

        void bindWatchSink(WatchSink sink);

        // Atomically increments watch_.iEvent; emits WatchRequests at configured thresholds.
        std::size_t countEvent();

        void markConfiguring(const std::string& configPath, bool trueTimeAtConfig = false);
        void start(bool print = true);
        void initialise(const Record::Writer& writer);
        void publish(RunPhase phase,
                     bool writeRunStat = false,
                     bool forceRenderStatus = false,
                     bool forceRenderBar = false);
        void publishThreadStats(int workerIndex,
                                ThreadPhase phase,
                                std::size_t eventIndex,
                                bool callbackCompleted = false);
        void finish(const Config::Watch& logging, std::size_t eventIndex);
        void setFatalStallHandler(FatalStallHandler handler);
        void stop();

      private:

        void initializeTerminal();
        void runLoop();
        void heartbeatTerminal(const RunSnapshot& snapshot);

        Config::uSeconds terminalIdleFor(const RunSnapshot& snapshot, const Config::TimePoint& now) const;
        bool isTerminalStalled(const RunSnapshot& snapshot, const Config::TimePoint& now) const;
        bool isFatalStalled(const RunSnapshot& snapshot, const Config::TimePoint& now) const;

        void renderStatusLine(const RunSnapshot& snapshot);
        void processUpdate(const RunSnapshot& snapshot, const PendingActions& actions);

        void flushRunStat(const RunSnapshot& snapshot) const;

        void writeThreadStats(const ThreadSnapshot& snapshot) const;
        void pushAction(RunSnapshot snap, PendingActions acts);
        
        static void waitWatchBarrier(const std::shared_ptr<Record::BarrierState>& barrier);

        Config::Watch                 watch_;
        PacingInfo                    pacing_;

        // Phase 1 watch sink + emission config.
        WatchSink                     watchSink_;
        bool                          saveHeartbeat_      = false;
        bool                          saveCheckpoints_    = false;
        bool                          saveLogThreads_     = false;
        bool                          saveFinalLog_       = true;
        std::size_t                   checkpointInterval_ = 100000;

        TString                       runStatPath_             = "";
        TString                       threadStatDirectory_     = "";
        std::mutex                    mutex_;
        std::condition_variable       condition_;
        std::deque<std::pair<RunSnapshot, PendingActions>> actionQueue_;
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
