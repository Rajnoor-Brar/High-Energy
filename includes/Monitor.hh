#pragma once

#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstddef>
#include <ctime>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <map>
#include <optional>
#include <sstream>
#include <set>
#include <string>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>

#include <sys/ioctl.h>
#include <unistd.h>
#include <termios.h>

#include "Pythia8/Pythia.h"

#include "Config.hh"

namespace Monitor {
    inline constexpr std::size_t FatalStallMultiplier = 5;
    termios oldt;

    inline void disable_input_echo() {
        termios newt;
        tcgetattr(STDIN_FILENO, &oldt);
        newt = oldt;

        newt.c_lflag &= ~(ECHO | ICANON);  // no echo, no line buffering
        tcsetattr(STDIN_FILENO, TCSANOW, &newt);
    }

    inline void restore_terminal() {
        tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
    }

    constexpr bool RenderStatus = true;
    constexpr bool RenderBar = true;
    constexpr bool WriteRunStat = true;

    constexpr bool DontRenderStatus = false;
    constexpr bool DontRenderBar = false;
    constexpr bool DontWriteRunStat = false;

    constexpr bool HasParticleCounts = true;
    constexpr bool NoParticleCounts = false;

    constexpr bool CallbackCompleted = true;
    constexpr bool NoCallbackCompleted = false;

    constexpr bool SlowCallback = true;
    constexpr bool NotSlowCallback = false;

    Config::Seconds programStallThreshold  = Config::Seconds(300);

    constexpr size_t NoEvents = 0;

    enum class RunPhase {
        Starting,
        Generation,
        Analysis,
        Logging,
        Finished
    };

    enum class ThreadPhase {
        Analysis,
        Simulation,
        Finished
    };

    struct RunSnapshot {
        std::size_t       eventIndex = 0;
        std::size_t       nEvents = 0;
        std::size_t       nRealEvents = 0;
        Config::uSeconds  elapsed = Config::uSeconds(0);
        std::string       eta = "--";
        double            progress = 0.0;
        RunPhase          phase = RunPhase::Starting;
        Config::TimePoint lastUpdateTime = Config::TimePoint{};
        std::size_t       barInterval = 0;
        std::size_t       checkInterval = 0;
        std::size_t       protonCount = 0;
        std::size_t       pionCount = 0;
        bool              hasParticleCounts = false;
        bool              fatalStall = false;
        Config::uSeconds  stallDuration = Config::uSeconds(0);
        Config::Seconds   stallThreshold = Config::Seconds(0);
        std::size_t       stallMultiplier = FatalStallMultiplier;
        std::string       fatalReason = "";
    };

    struct PendingActions {
        bool renderStatus = false;
        bool renderBar    = false;
        bool writeRunStat = false;

        bool any() const { return renderStatus || renderBar || writeRunStat; }

        void merge(const PendingActions& other) {
            renderStatus |= other.renderStatus;
            renderBar    |= other.renderBar;
            writeRunStat |= other.writeRunStat;
        }
    };

    struct ThreadSnapshot {
        int               workerIndex = -1;
        ThreadPhase       phase = ThreadPhase::Simulation;
        std::size_t       eventIndex = 0;
        std::size_t       callbacksCompleted = 0;
        Config::TimePoint lastUpdateTime = Config::TimePoint{};
        std::size_t       protonCount = 0;
        std::size_t       pionCount = 0;
        bool              hasParticleCounts = false;
    };
    struct WorkBatch {
        std::optional<PendingActions> actions;
        std::optional<RunSnapshot>    actionSnapshot;
        std::optional<RunSnapshot>    periodicSnapshot;
        std::optional<RunSnapshot>    fatalSnapshot;
        std::vector<ThreadSnapshot>   threadSnapshots;
        bool runStatDeadlineReached  = false;
        bool terminalDeadlineReached = false;
        bool shouldExit              = false;
        std::function<void(const RunSnapshot&)> fatalHandler;
    };

    inline std::mutex& terminalMutex() {
        static std::mutex mutex;
        return mutex;
    }

    inline std::tm localTime(const time_t& timeValue) {
        std::tm localTimeValue{};
        localtime_r(&timeValue, &localTimeValue);
        return localTimeValue;
    }

    inline std::string numberFormat(std::size_t number, std::size_t padding) {
        std::ostringstream stream;
        std::vector<std::size_t> groups;

        if (number == 0) {
            stream << '0';
            const std::string result = stream.str();
            return result.size() < padding ? std::string(padding - result.size(), ' ') + result : result;
        }

        while (number > 0) {
            groups.push_back(number % 1000); // get chunks of last three digits
            number /= 1000;                  // remove those digits
        }

        for (std::size_t i = groups.size(); i > 0; --i) {
            if (i == groups.size()) {
                stream << groups[i - 1];
            } else {
                stream << ',' << std::setw(3) << std::setfill('0') << groups[i - 1];
            }
        }

        const std::string result = stream.str();
        return result.size() < padding ? std::string(padding - result.size(), ' ') + result : result;
    }

    inline std::string timeString(const time_t& timeValue, bool highlightClock = true) {
        const std::tm localTimeValue = localTime(timeValue);
        std::ostringstream stream;
        stream << std::put_time(
            &localTimeValue,
            highlightClock ? "%F \033[34;1m%T\033[0m " : "%F %T"
        );
        return stream.str();
    }

    inline std::string timeString(const Config::TimePoint& timePoint, bool highlightClock = true) {
        return timeString(std::chrono::system_clock::to_time_t(timePoint), highlightClock);
    }

    inline std::string durationString(Config::uSeconds duration, bool preciseSecond = false) {
        using Seconds = std::chrono::seconds;

        std::ostringstream stream;
        const int totalSeconds        = std::chrono::duration_cast<Seconds>(duration).count();
        const int expectedSeconds     = totalSeconds % 60;
        const int expectedMinutes     = (totalSeconds / 60) % 60;
        const int expectedHours       = (totalSeconds / 3600) % 24;
        const int expectedDays        = totalSeconds / 86400;
        const double totalSecondsPrecise =
            std::chrono::duration_cast<std::chrono::duration<double>>(duration).count();
        const double expectedSecondsPrecise = std::fmod(totalSecondsPrecise, 60.0);
        const double roundedSeconds         = std::round(expectedSecondsPrecise * 100.0) / 100.0;
        const bool singularPreciseSecond    = std::abs(roundedSeconds - 1.0) < 0.005;

        stream << (expectedDays ? std::to_string(expectedDays) + " day" + (expectedDays == 1 ? " " : "s ") : "")
               << (expectedHours ? std::to_string(expectedHours) + " hour" + (expectedHours == 1 ? " " : "s ") : "")
               << (expectedMinutes ? std::to_string(expectedMinutes) + " minute" + (expectedMinutes == 1 ? " " : "s ") : "")
               << (preciseSecond
                       ? ((roundedSeconds > 0.0 || !(expectedDays || expectedHours || expectedMinutes))
                              ? (static_cast<std::ostringstream&&>(
                                     std::ostringstream{} << std::fixed << std::setprecision(2) << roundedSeconds
                                 ).str() +
                                 " second" + (singularPreciseSecond ? " " : "s "))
                              : "")
                       : (expectedSeconds
                              ? std::to_string(expectedSeconds) + " second" + (expectedSeconds == 1 ? " " : "s ")
                              : (!(expectedDays || expectedHours || expectedMinutes) ? "about now" : "")));

        return stream.str();
    }

    inline std::string updatedETA(std::size_t iEvent, std::size_t nEvents, Config::uSeconds duration, bool highlightClock = true) {
        using SysClock = std::chrono::system_clock;

        if (nEvents < iEvent || iEvent == 0) {
            return "--";
        }

        const double remainder = (nEvents - iEvent) / static_cast<double>(iEvent);
        const auto waitTime    = std::chrono::duration_cast<Config::uSeconds>(remainder * duration);

        std::ostringstream eta;
        eta << timeString(SysClock::to_time_t(SysClock::now() + waitTime), highlightClock)
            << " in " << durationString(waitTime);
        return eta.str();
    }

    inline const char* phaseString(RunPhase phase) {
        switch (phase) {
            case RunPhase::Starting:  return "Starting";
            case RunPhase::Generation: return "Generation";
            case RunPhase::Analysis: return "Analysis";
            case RunPhase::Logging:   return "Logging";
            case RunPhase::Finished:  return "Finished";
        }

        return "Unknown";
    }

    inline const char* threadPhaseString(ThreadPhase phase) {
        switch (phase) {
            case ThreadPhase::Analysis:   return "Analysis";
            case ThreadPhase::Simulation: return "Simulation";
            case ThreadPhase::Finished:   return "Finished";
        }

        return "Unknown";
    }

    inline const char* statusString(RunPhase phase) {
        switch (phase) {
            case RunPhase::Starting: return "Starting";
            case RunPhase::Finished: return "Finished";
            default:                 return "Running";
        }
    }

    inline RunSnapshot makeSnapshot(
        const Config::Log& logging,
        RunPhase phase,
        std::size_t eventIndex,
        std::size_t protonCount = 0,
        std::size_t pionCount = 0,
        bool hasParticleCounts = false
    ) {
        RunSnapshot snapshot;
        snapshot.eventIndex = eventIndex;
        snapshot.nEvents = logging.nEvents;
        snapshot.nRealEvents = logging.nRealEvents;
        snapshot.elapsed = logging.elapsed;
        snapshot.eta = updatedETA(eventIndex, logging.nEvents, logging.elapsed, false);
        snapshot.progress = logging.nEvents > 0
            ? static_cast<double>(eventIndex) / static_cast<double>(logging.nEvents)
            : 0.0;
        snapshot.phase = phase;
        snapshot.lastUpdateTime = std::chrono::system_clock::now();
        snapshot.barInterval = logging.barInterval;
        snapshot.checkInterval = logging.checkInterval;
        snapshot.protonCount = protonCount;
        snapshot.pionCount = pionCount;
        snapshot.hasParticleCounts = hasParticleCounts;
        return snapshot;
    }

    inline std::string runStatString(const RunSnapshot& snapshot, const Config::TimePoint& now) {
        std::ostringstream stream;
        const auto idleFor = std::chrono::duration_cast<Config::uSeconds>(now - snapshot.lastUpdateTime);
        const std::size_t percent = snapshot.nEvents > 0
            ? static_cast<std::size_t>(100.0 * snapshot.progress)
            : 0;

        stream << "Status                        : " << statusString(snapshot.phase) << '\n';
        stream << "Phase                         : " << phaseString(snapshot.phase) << '\n';
        stream << "Event                         : " << numberFormat(snapshot.eventIndex, 0)
               << " / " << numberFormat(snapshot.nEvents, 0) << '\n';
        stream << "Real Event Count              : " << numberFormat(snapshot.nRealEvents, 0) << '\n';
        stream << "Completion                    : " << percent << "%\n";
        stream << "Elapsed                       : " << durationString(snapshot.elapsed, true) << '\n';
        stream << "ETA                           : " << snapshot.eta << '\n';
        stream << "Last Update                   : " << timeString(snapshot.lastUpdateTime, false) << '\n';
        stream << "No Update For                 : " << durationString(idleFor) << '\n';
        stream << "Progress Bar Update Interval  : " << numberFormat(snapshot.barInterval, 0) << '\n';
        stream << "Check Interval                : " << numberFormat(snapshot.checkInterval, 0) << '\n';

        if (snapshot.fatalStall) {
            stream << "Fatal Stall                   : YES\n";
            stream << "Fatal Reason                  : " << snapshot.fatalReason << '\n';
            stream << "Stall Duration                : " << durationString(snapshot.stallDuration, true) << '\n';
            stream << "Stall Threshold               : "
                   << durationString(std::chrono::duration_cast<Config::uSeconds>(snapshot.stallThreshold), true) << '\n';
            stream << "Fatal Multiplier              : " << snapshot.stallMultiplier << "x\n";
        }

        if (snapshot.hasParticleCounts) {
            stream << "Proton Count                  : " << numberFormat(snapshot.protonCount, 0) << '\n';
            stream << "Pion Count                    : " << numberFormat(snapshot.pionCount, 0) << '\n';
        }

        return stream.str();
    }

    inline std::string threadStatString(const ThreadSnapshot& snapshot, const Config::TimePoint& now) {
        std::ostringstream stream;
        const auto idleFor = std::chrono::duration_cast<Config::uSeconds>(now - snapshot.lastUpdateTime);

        stream << "Worker Index                  : " << std::setw(2) << std::setfill('0') << snapshot.workerIndex << '\n';
        stream << "Thread Phase                  : " << threadPhaseString(snapshot.phase) << '\n';
        stream << "Last Global Event             : " << numberFormat(snapshot.eventIndex, 0) << '\n';
        stream << "Events Completed              : " << numberFormat(snapshot.callbacksCompleted, 0) << '\n';
        stream << "Last Update                   : " << timeString(snapshot.lastUpdateTime, false) << '\n';
        stream << "No Update For                 : " << durationString(idleFor) << '\n';

        if (snapshot.hasParticleCounts) {
            stream << "Proton Count                  : " << numberFormat(snapshot.protonCount, 0) << '\n';
            stream << "Pion Count                    : " << numberFormat(snapshot.pionCount, 0) << '\n';
        }

        return stream.str();
    }

    inline Config::uSeconds terminalIdleFor(const RunSnapshot& snapshot) {
        return std::chrono::duration_cast<Config::uSeconds>(
            std::chrono::system_clock::now() - snapshot.lastUpdateTime
        );
    }

    inline Config::uSeconds terminalIdleFor(const RunSnapshot& snapshot, const Config::TimePoint& now) {
        return std::chrono::duration_cast<Config::uSeconds>(now - snapshot.lastUpdateTime);
    }

    inline bool isTerminalStalled(const RunSnapshot& snapshot) {
        return snapshot.phase != RunPhase::Starting
            && snapshot.phase != RunPhase::Finished
            && terminalIdleFor(snapshot)
                >= programStallThreshold;
    }

    inline bool isFatalStalled(const RunSnapshot& snapshot, const Config::TimePoint& now) {
        if (snapshot.phase == RunPhase::Starting || snapshot.phase == RunPhase::Finished) {
            return false;
        }

        const Config::Seconds fatalThreshold = programStallThreshold * FatalStallMultiplier;
        return terminalIdleFor(snapshot, now) >= std::chrono::duration_cast<Config::uSeconds>(fatalThreshold);
    }

    inline void writeTextFile(const TString& path, const std::string& text) {
        std::ofstream stream(path.Data(), std::ios::trunc);
        stream << text;
    }

    inline void renderStatus(const RunSnapshot& snapshot) {
        const std::size_t percent = snapshot.nEvents > 0
            ? static_cast<std::size_t>(100.0 * snapshot.progress)
            : 0;
        const std::size_t eventWidth = numberFormat(snapshot.nEvents, 0).size();

        std::cout << "\033[3F\033[2K";

            if (snapshot.fatalStall) {
                std::cout << "\033[E\r\033[2K"
                          << "\t\033[31;1m Fatal stall\033[0m after "
                          << durationString(snapshot.stallDuration, true)
                          << "\033[E\033[2K\t Last event: "
                          << numberFormat(snapshot.eventIndex, eventWidth)
                          << " / " << numberFormat(snapshot.nEvents, 0)
                          << "\033[E\033[2K\t " << snapshot.fatalReason;
            }
            else if (snapshot.phase == RunPhase::Starting) {
                std::cout<< "\033[E\033[2K"<< "\t\033[34;1m Initializing "<<snapshot.eta<<"... \033[0m\033[E\033[2K";
                //  << "\033[E\033[2K";
            } 
            else if (snapshot.phase == RunPhase::Finished){
                std::cout << "\033[E\r\033[2K" << "\t\033[32;1m Finished\033[0m"
                << "\033[E\033[2K";
            }
            else{
                const bool stalled = isTerminalStalled(snapshot);
                std::cout << "\t Events processed : " << "\033[32;1m"
                  << numberFormat(snapshot.eventIndex, eventWidth) << "\033[0m"
                  << " out of " << numberFormat(snapshot.nEvents, 0) << "  |  "
                  << std::setw(2) << percent << "% "
                  << "\033[E\033[2K\t "<<"ETA: " << snapshot.eta
                  << "\033[E\033[2K\t"
                  << (stalled
                          ? std::string("\033[31;1mStalled for ")
                                + durationString(terminalIdleFor(snapshot))
                                + "\033[0m"
                          : "");
            }
            std::cout<< "\033[E\r"<< std::flush;

        
    }

    inline void renderProgressBar(double progress) {
        struct winsize windowSize{};
        ioctl(STDOUT_FILENO, TIOCGWINSZ, &windowSize);
        
        constexpr char done = '=';
        constexpr char toDo = '-';
        const int nCols      = windowSize.ws_col ? static_cast<int>(windowSize.ws_col) - 6 : 100;
        const int filledCols = static_cast<int>(progress * nCols);
        

        std::cout<<"\r\033[32;1m|" << std::string(filledCols, done) << "\033[0m"
                  << (progress < 1.0 ? ">\033[31m" : std::string("\033[32;1m") + done)
                  << std::string(nCols - filledCols, toDo) << "|\033[0m"
                  << "\033[J\r" << std::flush;
    }

    class AsyncLogger {
      public:
        using FatalStallHandler = std::function<void(const RunSnapshot&)>;

        AsyncLogger() = default;
        ~AsyncLogger() { stop();  }

        void start(const Config::Root& root, const Config::Log& logging) {
            stop();
            {
                std::lock_guard<std::mutex> lock(mutex_);
                runStatPath_         = root.runStatName;
                threadStatDirectory_ = root.threadStatDirectory;
                pendingActions_.reset();
                latestSnapshot_.reset();
                dirtyThreadWorkers_.clear();
                threadSnapshots_.clear();
                stopRequested_       = false;
                fatalStallTriggered_ = false;
                terminalInitialized_ = false;
                progressBarVisible_  = false;
                heartbeat_interval_    = logging.heartbeat_interval > Config::uSeconds(0) ? logging.heartbeat_interval : Config::uSeconds(1000);
                terminalRefreshInterval_ = logging.terminal_refresh_interval > Config::Seconds(0) ? logging.terminal_refresh_interval : Config::Seconds(60);
                programStallThreshold  = logging.program_stall_threshold > Config::Seconds(0) ? logging.program_stall_threshold : Config::Seconds(300);
            }
            worker_ = std::thread(&AsyncLogger::runLoop, this);
        }

        void publish(
            const Config::Log& logging,
            RunPhase phase,
            std::size_t eventIndex,
            bool renderStatus      = false,
            bool renderBar         = false,
            bool writeRunStat      = false,
            bool hasParticleCounts = false,
            std::size_t protonCount = 0,
            std::size_t pionCount   = 0,
            std::string extraString = ""
        ) {
            RunSnapshot snapshot = makeSnapshot(logging, phase, eventIndex, protonCount, pionCount, hasParticleCounts);
            if(phase == RunPhase::Starting){
                snapshot.eta = extraString;
            }
            std::lock_guard<std::mutex> lock(mutex_);
            latestSnapshot_ = std::move(snapshot);

            const PendingActions incoming{renderStatus, renderBar, writeRunStat};
            if (incoming.any()) {
                mergePending(incoming);
                condition_.notify_one();
            }
        }

        void publishThreadStats(
            int workerIndex,
            ThreadPhase phase,
            std::size_t eventIndex,
            bool callbackCompleted = false,
            bool hasParticleCounts = false,
            std::size_t protonCount = 0,
            std::size_t pionCount   = 0
        ) {
            if (workerIndex < 0) return;

            std::lock_guard<std::mutex> lock(mutex_);
            ThreadSnapshot& snapshot   = threadSnapshots_[workerIndex];
            snapshot.workerIndex       = workerIndex;
            snapshot.phase             = phase;
            snapshot.eventIndex        = eventIndex;
            snapshot.lastUpdateTime    = std::chrono::system_clock::now();
            snapshot.hasParticleCounts = hasParticleCounts;
            snapshot.protonCount       = hasParticleCounts ? protonCount : 0;
            snapshot.pionCount         = hasParticleCounts ? pionCount : 0;

            if (callbackCompleted) ++snapshot.callbacksCompleted;

            dirtyThreadWorkers_.insert(workerIndex);
            condition_.notify_one();
        }

        void finish(const Config::Log& logging, std::size_t eventIndex) {
            RunSnapshot snapshot = makeSnapshot(logging, RunPhase::Finished, eventIndex);
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

            if (worker_.joinable())
                worker_.join();
        }

        void makeSpace(){
            std::cout << "\n\n\n\n" << std::flush;
        }

      private:
        void mergePending(const PendingActions& incoming) {
            if (pendingActions_.has_value())
                pendingActions_->merge(incoming);
            else
                pendingActions_ = incoming;
        }

        WorkBatch collectPendingWork(
            const Config::TimePoint& now,
            bool runStatDeadline,
            bool terminalDeadline
        ) {
            WorkBatch batch;
            batch.runStatDeadlineReached  = runStatDeadline;
            batch.terminalDeadlineReached = terminalDeadline;

            if (pendingActions_.has_value() && latestSnapshot_.has_value()) {
                batch.actions        = *pendingActions_;
                batch.actionSnapshot = *latestSnapshot_;
                pendingActions_.reset();
            }

            if (latestSnapshot_.has_value() && (runStatDeadline || terminalDeadline))
                batch.periodicSnapshot = *latestSnapshot_;

            if (!fatalStallTriggered_
                && latestSnapshot_.has_value()
                && fatalStallHandler_
                && (runStatDeadline || terminalDeadline)
                && isFatalStalled(*latestSnapshot_, now)) {
                batch.fatalSnapshot = *latestSnapshot_;
                batch.fatalSnapshot->fatalStall = true;
                batch.fatalSnapshot->fatalReason = "No progress update exceeded fatal stall threshold";
                batch.fatalSnapshot->stallDuration = terminalIdleFor(*latestSnapshot_, now);
                batch.fatalSnapshot->stallThreshold = programStallThreshold;
                batch.fatalSnapshot->stallMultiplier = FatalStallMultiplier;
                batch.fatalHandler = fatalStallHandler_;
                fatalStallTriggered_ = true;
            }

            if (runStatDeadline) {
                batch.threadSnapshots.reserve(threadSnapshots_.size());
                for (const auto& [_, snap] : threadSnapshots_)
                    batch.threadSnapshots.push_back(snap);
            } else if (!dirtyThreadWorkers_.empty()) {
                batch.threadSnapshots.reserve(dirtyThreadWorkers_.size());
                for (int idx : dirtyThreadWorkers_) {
                    auto it = threadSnapshots_.find(idx);
                    if (it != threadSnapshots_.end())
                        batch.threadSnapshots.push_back(it->second);
                }
            }
            dirtyThreadWorkers_.clear();

            batch.shouldExit = stopRequested_ && !batch.actions.has_value();
            return batch;
        }

        void dispatchWork(const WorkBatch& batch) {
            const bool wroteImmediateRunStat =
                batch.actions.has_value()
                && batch.actions->writeRunStat
                && batch.actionSnapshot.has_value();

            const bool renderedImmediately =
                batch.actions.has_value()
                && batch.actionSnapshot.has_value()
                && (batch.actions->renderStatus || batch.actions->renderBar);

            if (batch.actions.has_value() && batch.actionSnapshot.has_value())
                processUpdate(*batch.actionSnapshot, *batch.actions);

            if (batch.periodicSnapshot.has_value()) {
                if (batch.runStatDeadlineReached && !wroteImmediateRunStat)
                    flushRunStat(*batch.periodicSnapshot);
                if (batch.terminalDeadlineReached && !renderedImmediately)
                    heartbeatTerminal(*batch.periodicSnapshot);
            }

            if (batch.fatalSnapshot.has_value()) {
                flushRunStat(*batch.fatalSnapshot);
                std::lock_guard<std::mutex> terminalLock(terminalMutex());
                initializeTerminal();
                renderStatus(*batch.fatalSnapshot);
                if (progressBarVisible_) {
                    renderProgressBar(batch.fatalSnapshot->progress);
                }
            }

            for (const auto& snapshot : batch.threadSnapshots) writeThreadStats(snapshot);
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
                condition_.wait_until(
                    lock,
                    std::min(nextRunStatWrite, nextTerminalRefresh),
                    [&] { return stopRequested_ || pendingActions_.has_value(); }
                );

                const auto now               = SteadyClock::now();
                const auto wallNow           = std::chrono::system_clock::now();
                const bool runStatDeadline   = now >= nextRunStatWrite;
                const bool terminalDeadline  = now >= nextTerminalRefresh;

                WorkBatch batch = collectPendingWork(wallNow, runStatDeadline, terminalDeadline);
                lock.unlock();

                dispatchWork(batch);

                if (batch.fatalSnapshot.has_value() && batch.fatalHandler) {
                    batch.fatalHandler(*batch.fatalSnapshot);
                }

                if (batch.shouldExit) break;

                if (runStatDeadline)  advanceDeadline(nextRunStatWrite   , heartbeat_interval_);
                if (terminalDeadline) advanceDeadline(nextTerminalRefresh, terminalRefreshInterval_);

                lock.lock();
            }
        }

        void processUpdate(const RunSnapshot& snapshot, const PendingActions& actions) {
            if (actions.writeRunStat)
                flushRunStat(snapshot);

            if (!(actions.renderStatus || actions.renderBar))
                return;

            std::lock_guard<std::mutex> terminalLock(terminalMutex());
            initializeTerminal();
            if (actions.renderStatus)   
                renderStatus(snapshot);
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
            renderStatus(snapshot);
            if (progressBarVisible_) renderProgressBar(snapshot.progress);
        }

        void writeThreadStats(const ThreadSnapshot& snapshot) const {
            if (threadStatDirectory_.Length() == 0 || snapshot.workerIndex < 0) return;
            const TString threadPath =
                Form("%sThread_%02d.log", threadStatDirectory_.Data(), snapshot.workerIndex);
            writeTextFile(threadPath, threadStatString(snapshot, std::chrono::system_clock::now()));
        }

        void initializeTerminal() {
            if (terminalInitialized_) return;
            std::cout << "\n\n\n" << std::flush;
            terminalInitialized_ = true;
        }

        TString runStatPath_         = "";
        TString threadStatDirectory_ = "";
        std::mutex mutex_;
        std::condition_variable condition_;
        std::optional<PendingActions> pendingActions_;
        std::optional<RunSnapshot>    latestSnapshot_;
        std::set<int>                 dirtyThreadWorkers_;
        std::map<int, ThreadSnapshot> threadSnapshots_;
        std::thread                   worker_;
        Config::uSeconds              heartbeat_interval_    = Config::uSeconds(1000);
        Config::Seconds               terminalRefreshInterval_ = Config::Seconds(60);
        bool                          stopRequested_       = false;
        bool                          fatalStallTriggered_ = false;
        bool                          terminalInitialized_ = false;
        bool                          progressBarVisible_  = false;
        FatalStallHandler             fatalStallHandler_;
    };

    template <typename PythiaT>
    std::string buildLogText(
        PythiaT& pythia,
        const Config::Root& root,
        const Config::Log& logging,
        const std::string& programLog = {}
    ) {
        std::ostringstream logStream;
        const time_t localStart = std::chrono::system_clock::to_time_t(logging.start);

        logStream << "Serial                        : " << std::setw(2) << std::setfill('0') << logging.serial << '\n';
        logStream << "Beam Energy                   : " << root.beamEnergy.Data() << '\n';
        logStream << "Event Count                   : " << numberFormat(logging.nEvents, 0) << '\n';
        logStream << "Real Event Count              : " << numberFormat(logging.nRealEvents, 0) << '\n';
        logStream << "Last Run                      : " << timeString(localStart, false) << '\n';
        logStream << "Time Taken                    : " << durationString(logging.elapsed) << '\n';
        logStream << "Time Taken / 1000 Events      : " << durationString((1000 * logging.elapsed) / logging.nEvents, true) << '\n';
        logStream << "Histogram Scale               : " << root.histScale << '\n';
        logStream << "Status Snapshot Interval (ms) : " << numberFormat(logging.heartbeat_interval.count(), 0) << '\n';
        logStream << "Progress Bar Update Interval  : " << numberFormat(logging.barInterval, 0) << '\n';
        logStream << "Check Interval                : " << numberFormat(logging.checkInterval, 0) << '\n';

        if (!programLog.empty()) {
            logStream << programLog;
            if (programLog.back() != '\n') {
                logStream << '\n';
            }
        }

        std::ostringstream capturedOutput;
        {
            std::lock_guard<std::mutex> terminalLock(terminalMutex());
            std::streambuf* oldStream = std::cout.rdbuf(capturedOutput.rdbuf());
            std::cout << "\n\n\n";
            pythia.settings.listChanged();
            std::cout << "\n\n\n";

            if constexpr (std::is_same_v<PythiaT, Pythia8::Pythia>) {
                pythia.info.list();
                std::cout << "\n\n\n";
            }

            pythia.stat();
            std::cout.rdbuf(oldStream);
        }

        logStream << capturedOutput.str();
        return logStream.str();
    }

    template <typename PythiaT>
    void outputLog(
        PythiaT& pythia,
        const Config::Root& root,
        const Config::Log& logging,
        const std::string& programLog = {},
        const TString& logPath = ""
    ) {
        const TString targetLogPath = logPath.Length() > 0 ? logPath : root.logName;
        writeTextFile(targetLogPath, buildLogText(pythia, root, logging, programLog));
    }

    inline std::string buildEmergencyLogText(
        const Config::Root& root,
        const Config::Log& logging,
        const RunSnapshot& snapshot,
        const std::string& programLog = {},
        const std::string& reason = {}
    ) {
        std::ostringstream stream;

        stream << "Emergency Shutdown            : fatal stall\n";
        if (!reason.empty()) {
            stream << "Emergency Detail              : " << reason << '\n';
        }
        stream << "Serial                        : " << std::setw(2) << std::setfill('0') << logging.serial << '\n';
        stream << "Beam Energy                   : " << root.beamEnergy.Data() << '\n';
        stream << "File Title                    : " << root.fileTitle.Data() << '\n';
        stream << "Root Output                   : " << root.outName.Data() << '\n';
        stream << "Main Log                      : " << root.logName.Data() << '\n';
        stream << "RunStat Log                   : " << root.runStatName.Data() << '\n';
        stream << "Last Event                    : " << numberFormat(snapshot.eventIndex, 0)
               << " / " << numberFormat(snapshot.nEvents, 0) << '\n';
        stream << "Real Event Count              : " << numberFormat(snapshot.nRealEvents, 0) << '\n';
        stream << "Phase                         : " << phaseString(snapshot.phase) << '\n';
        stream << "Elapsed                       : " << durationString(logging.elapsed, true) << '\n';
        stream << "Last Update                   : " << timeString(snapshot.lastUpdateTime, false) << '\n';
        stream << "Fatal Reason                  : " << snapshot.fatalReason << '\n';
        stream << "Stall Duration                : " << durationString(snapshot.stallDuration, true) << '\n';
        stream << "Stall Threshold               : "
               << durationString(std::chrono::duration_cast<Config::uSeconds>(snapshot.stallThreshold), true) << '\n';
        stream << "Fatal Multiplier              : " << snapshot.stallMultiplier << "x\n";

        if (!programLog.empty()) {
            stream << programLog;
            if (programLog.back() != '\n') {
                stream << '\n';
            }
        }

        return stream.str();
    }

    inline void writeEmergencyLog(
        const Config::Root& root,
        const Config::Log& logging,
        const RunSnapshot& snapshot,
        const std::string& programLog = {},
        const std::string& reason = {}
    ) {
        writeTextFile(root.logName, buildEmergencyLogText(root, logging, snapshot, programLog, reason));
    }

    template <typename PythiaT>
    void terminalReport(PythiaT& pythia, const Config::Root& root, Config::Log& logging, bool stats = false) {
        std::lock_guard<std::mutex> terminalLock(terminalMutex());
        std::cout << "\n\n\n";
        if (stats) {
            pythia.stat();
            std::cout << "\n\n";
        }

        const Config::TimePoint now = std::chrono::system_clock::now();
        logging.elapsed             = std::chrono::duration_cast<Config::uSeconds>(now - logging.start);

        std::cout << "Finished :\n" << std::string(10, ' ')
                  << timeString(now)
                  << "\n" << std::string(10, ' ') << durationString(logging.elapsed) << std::endl;
        std::cout << "\nFile Title : " << root.fileTitle.Data() << std::endl << std::endl;
    }
}
