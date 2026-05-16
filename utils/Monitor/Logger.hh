#pragma once

#include <condition_variable>
#include <cstddef>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
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
        // docs/WriterMT.md Phase 1: pluggable sink for WatchRequest emission.
        // Set via bindWatchSink(); when unset, countEvent() only increments
        // and returns.  Phase 2 wires this to Record::Writer::signalWatch.
        using WatchSink = std::function<void(Record::WatchRequest)>;

        explicit AsyncLogger(bool print = true);
        ~AsyncLogger();

        Config::Watch&       watch();
        const Config::Watch& watch() const;

        const PacingInfo& pacingInfo() const;
        std::size_t       checkInterval() const;

        void configurePacing(PacingInfo pacing);

        // docs/WriterMT.md Phase 1.  Configure which WatchRequest kinds the
        // logger emits, and at what events-based cadences.  Called from
        // Monitor::configureMonitor after the [monitor] section is parsed.
        void configureWatchEmission(bool saveHeartbeat,
                                    bool saveCheckpoints,
                                    std::size_t checkpointInterval);

        // docs/WriterMT.md: configure non-watch-queue artifacts.
        //   saveLogThreads: if false, publishThreadStats() is a no-op
        //   saveFinalLog: if false, Writer::finish() skips outputLog()
        void configureArtifactEmission(bool saveLogThreads, bool saveFinalLog);

        bool saveLogThreads() const;
        bool saveFinalLog() const;
        bool saveCheckpoints() const;
        bool saveHeartbeat() const;

        void bindWatchSink(WatchSink sink);

        // docs/WriterMT.md Phase 1.  Atomic increment of watch_.iEvent.
        // Returns the new count.  When configured thresholds are crossed,
        // pushes a WatchRequest through the watch sink (heartbeat is
        // fire-and-forget; checkpoint blocks the caller on the barrier
        // until the watchdog completes the snapshot).
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
        void mergePending(const PendingActions& incoming);
        
        static void waitWatchBarrier(const std::shared_ptr<Record::BarrierState>& barrier);

        Config::Watch                 watch_;
        PacingInfo                    pacing_;

        // docs/WriterMT.md Phase 1: watchdog sink + emission config.
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
