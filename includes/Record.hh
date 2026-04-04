#pragma once

#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstddef>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <optional>
#include <sstream>
#include <string>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>

#include <sys/ioctl.h>
#include <unistd.h>

#include "Pythia8/Pythia.h"

#include "Config.hh"

namespace Record {

    constexpr bool RenderStatus = true;
    constexpr bool RenderBar = true;
    constexpr bool WriteRunStat = true;

    constexpr bool DontRenderStatus = false;
    constexpr bool DontRenderBar = false;
    constexpr bool DontWriteRunStat = false;

    constexpr bool HasParticleCounts = true;
    constexpr bool NoParticleCounts = false;

    enum class RunPhase {
        Starting,
        Running,
        SelectionLoop,
        CheckpointWrite,
        CheckpointLog,
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
    };

    struct PendingActions {
        bool renderStatus = false;
        bool renderBar = false;
        bool writeRunStat = false;
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
            groups.push_back(number % 1000);
            number /= 1000;
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

    inline std::string updatedETA(
        std::size_t iEvent,
        std::size_t nEvents,
        Config::uSeconds duration,
        bool highlightClock = true
    ) {
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
            case RunPhase::Starting:        return "Starting";
            case RunPhase::Running:         return "Running";
            case RunPhase::SelectionLoop:   return "SelectionLoop";
            case RunPhase::CheckpointWrite: return "CheckpointWrite";
            case RunPhase::CheckpointLog:   return "CheckpointLog";
            case RunPhase::Finished:        return "Finished";
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

        if (snapshot.hasParticleCounts) {
            stream << "Proton Count                  : " << numberFormat(snapshot.protonCount, 0) << '\n';
            stream << "Pion Count                    : " << numberFormat(snapshot.pionCount, 0) << '\n';
        }

        return stream.str();
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

        std::cout << "\033[2A\r\033[2K";

            if (snapshot.phase == RunPhase::Starting) {
                std::cout<< "\t\033[34;1m Initializing... \033[0m"
                << "\033[B\r\033[2K\t ";
            } 
            else if (snapshot.phase == RunPhase::Finished){
                std::cout << "\t\033[32;1m Finished\033[0m"
                << "\033[B\r\033[2K\t ";
            }
            else{
                std::cout << "\t Events processed : " << "\033[32;1m"
                  << numberFormat(snapshot.eventIndex, eventWidth) << "\033[0m"
                  << " out of " << numberFormat(snapshot.nEvents, 0) << "  |  "
                  << std::setw(2) << percent << "% "
                  << "\033[B\r\033[2K\t "
                  << "ETA: " << snapshot.eta;
            }
            std::cout<< "\033[B\r"<< std::flush;

        
    }

    inline void renderProgressBar(double progress) {
        struct winsize windowSize{};
        ioctl(STDOUT_FILENO, TIOCGWINSZ, &windowSize);

        constexpr char done = '=';
        constexpr char toDo = '-';

        const int nCols      = windowSize.ws_col ? static_cast<int>(windowSize.ws_col) - 6 : 100;
        const int filledCols = static_cast<int>(progress * nCols);

        std::cout << "\r\033[2K"
                  << "\033[32;1m|" << std::string(filledCols, done) << "\033[0m"
                  << (progress < 1.0 ? ">\033[31m" : std::string("\033[32;1m") + done)
                  << std::string(nCols - filledCols, toDo) << "|\033[0m"
                  << std::flush;
    }

    class AsyncLogger {
    public:
        AsyncLogger() = default;

        ~AsyncLogger() {
            stop();
        }

        void start(const Config::Root& root, std::size_t statusIntervalMs) {
            stop();
            {
                std::lock_guard<std::mutex> lock(mutex_);
                runStatPath_ = root.runStatName;
                pendingActions_.reset();
                latestSnapshot_.reset();
                stopRequested_ = false;
                terminalInitialized_ = false;
                statusIntervalMs_ = statusIntervalMs > 0 ? statusIntervalMs : 1000;
            }
            worker_ = std::thread(&AsyncLogger::runLoop, this);
        }

        void publish(
            const Config::Log& logging,
            RunPhase phase,
            std::size_t eventIndex,
            bool renderStatus = false,
            bool renderBar = false,
            bool writeRunStat = false,
            bool hasParticleCounts = false,
            std::size_t protonCount = 0,
            std::size_t pionCount = 0
        ) {
            RunSnapshot snapshot =
                makeSnapshot(logging, phase, eventIndex, protonCount, pionCount, hasParticleCounts);

            std::lock_guard<std::mutex> lock(mutex_);
            latestSnapshot_ = std::move(snapshot);

            if (!(renderStatus || renderBar || writeRunStat)) {
                return;
            }

            if (pendingActions_.has_value()) {
                pendingActions_->renderStatus = pendingActions_->renderStatus || renderStatus;
                pendingActions_->renderBar = pendingActions_->renderBar || renderBar;
                pendingActions_->writeRunStat = pendingActions_->writeRunStat || writeRunStat;
            } else {
                pendingActions_ = PendingActions{renderStatus, renderBar, writeRunStat};
            }
            condition_.notify_one();
        }

        void finish(const Config::Log& logging, std::size_t eventIndex) {
            RunSnapshot snapshot = makeSnapshot(logging, RunPhase::Finished, eventIndex);
            {
                std::lock_guard<std::mutex> lock(mutex_);
                latestSnapshot_ = std::move(snapshot);

                if (pendingActions_.has_value()) {
                    pendingActions_->renderStatus = true;
                    pendingActions_->renderBar = true;
                    pendingActions_->writeRunStat = true;
                } else {
                    pendingActions_ = PendingActions{true, true, true};
                }
                stopRequested_ = true;
            }
            condition_.notify_one();
        }

        void stop() {
            {
                std::lock_guard<std::mutex> lock(mutex_);
                stopRequested_ = true;
            }
            condition_.notify_one();

            if (worker_.joinable()) {
                worker_.join();
            }
        }

    private:
        void runLoop() {
            using SteadyClock = std::chrono::steady_clock;

            std::unique_lock<std::mutex> lock(mutex_);
            auto nextRunStatWrite =
                SteadyClock::now() + std::chrono::milliseconds(statusIntervalMs_);

            while (true) {
                condition_.wait_until(
                    lock,
                    nextRunStatWrite,
                    [&] { return stopRequested_ || pendingActions_.has_value(); }
                );

                std::optional<PendingActions> actions;
                std::optional<RunSnapshot> actionSnapshot;
                if (pendingActions_.has_value() && latestSnapshot_.has_value()) {
                    actions = *pendingActions_;
                    actionSnapshot = *latestSnapshot_;
                    pendingActions_.reset();
                }

                const auto now = SteadyClock::now();
                const bool deadlineReached = now >= nextRunStatWrite;
                std::optional<RunSnapshot> heartbeatSnapshot;
                if (latestSnapshot_.has_value() && deadlineReached) {
                    heartbeatSnapshot = *latestSnapshot_;
                }

                const bool shouldExit = stopRequested_ && !actions.has_value();
                lock.unlock();

                const bool wroteImmediateRunStat =
                    actions.has_value() && actions->writeRunStat && actionSnapshot.has_value();
                if (actions.has_value() && actionSnapshot.has_value()) {
                    processUpdate(*actionSnapshot, *actions);
                }
                if (heartbeatSnapshot.has_value() && !wroteImmediateRunStat) {
                    heartbeatRunStat(*heartbeatSnapshot);
                }

                if (shouldExit) {
                    break;
                }

                if (deadlineReached) {
                    const auto current = SteadyClock::now();
                    const auto interval = std::chrono::milliseconds(statusIntervalMs_);
                    while (nextRunStatWrite <= current) {
                        nextRunStatWrite += interval;
                    }
                }

                lock.lock();
            }
        }

        void processUpdate(const RunSnapshot& snapshot, const PendingActions& actions) {
            if (actions.writeRunStat) {
                writeRunStat(snapshot);
            }

            if (!(actions.renderStatus || actions.renderBar)) {
                return;
            }

            std::lock_guard<std::mutex> terminalLock(terminalMutex());
            initializeTerminal();
            if (actions.renderStatus) {
                renderStatus(snapshot);
            }
            if (actions.renderBar) {
                renderProgressBar(snapshot.progress);
            }
        }

        void heartbeatRunStat(const RunSnapshot& snapshot) {
            if (runStatPath_.Length() == 0) {
                return;
            }

            writeTextFile(
                runStatPath_,
                runStatString(snapshot, std::chrono::system_clock::now())
            );
        }

        void writeRunStat(const RunSnapshot& snapshot) const {
            if (runStatPath_.Length() == 0) {
                return;
            }

            writeTextFile(runStatPath_, runStatString(snapshot, std::chrono::system_clock::now()));
        }

        void initializeTerminal() {
            if (terminalInitialized_) {
                return;
            }
            std::cout << "\n\n\n" << std::flush;
            terminalInitialized_ = true;
        }

        TString runStatPath_ = "";
        std::mutex mutex_;
        std::condition_variable condition_;
        std::optional<PendingActions> pendingActions_;
        std::optional<RunSnapshot> latestSnapshot_;
        std::thread worker_;
        std::size_t statusIntervalMs_ = 1000;
        bool stopRequested_ = false;
        bool terminalInitialized_ = false;
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
        logStream << "Status Snapshot Interval (ms) : " << numberFormat(logging.statusIntervalMs, 0) << '\n';
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
