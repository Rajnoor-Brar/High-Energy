#pragma once

#include <functional>
#include <fstream>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>

#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

#include "Config.hh"
#include "TString.h"
#include "Utility.hh"
#include "Monitor/Snapshot.hh"

namespace Monitor {

    inline termios oldt;

    inline void disable_input_echo() {
        termios newt;
        tcgetattr(STDIN_FILENO, &oldt);
        newt = oldt;
        newt.c_lflag &= ~(ECHO | ICANON);
        tcsetattr(STDIN_FILENO, TCSANOW, &newt);
    }

    inline void restore_terminal() {
        tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
    }

    inline std::mutex& terminalMutex() {
        static std::mutex mutex;
        return mutex;
    }

    inline void writeTextFile(const TString& path, const std::string& text) {
        std::ofstream stream(path.Data(), std::ios::trunc);
        stream << text;
    }

    inline void renderProgressBar(double progress) {
        struct winsize windowSize{};
        ioctl(STDOUT_FILENO, TIOCGWINSZ, &windowSize);
        constexpr char done = '=';
        constexpr char toDo = '-';
        const int nCols      = windowSize.ws_col ? static_cast<int>(windowSize.ws_col) - 6 : 100;
        const int filledCols = static_cast<int>(progress * nCols);
        std::cout << "\r\033[32;1m|" << std::string(filledCols, done) << "\033[0m"
                  << (progress < 1.0 ? ">\033[31m" : std::string("\033[32;1m") + done)
                  << std::string(nCols - filledCols, toDo) << "|\033[0m"
                  << "\033[J\r" << std::flush;
    }

    inline std::string buildLogText(const Config::Register& root,
                                    const Config::Watch& logging,
                                    const std::string& programLog = {},
                                    const std::function<void()>& printStats = {},
                                    const std::function<void()>& listChangedSettings = {})
    {
        std::ostringstream logStream;
        const time_t localStart = std::chrono::system_clock::to_time_t(logging.start);

        logStream << "Serial                        : " << std::setw(2) << std::setfill('0') << logging.serial << '\n';
        logStream << "Beam Energy                   : " << root.beamEnergy.Data() << '\n';
        logStream << "Event Count                   : " << Utility::numberFormat(logging.nEvents, 0) << '\n';
        logStream << "Real Event Count              : " << Utility::numberFormat(logging.n_real_events, 0) << '\n';
        logStream << "Last Run                      : " << Utility::timeString(localStart, false) << '\n';
        logStream << "Time Taken                    : " << Utility::durationString(logging.elapsed) << '\n';
        logStream << "Time Taken / 1000 Events      : " << Utility::durationString((1000 * logging.elapsed) / logging.nEvents, true) << '\n';
        logStream << "Histogram Scale               : " << root.histScale << '\n';
        logStream << "Status Snapshot Interval (ms) : " << Utility::numberFormat(logging.heartbeat_interval.count(), 0) << '\n';
        logStream << "Progress Bar Update Interval  : " << Utility::numberFormat(logging.bar_interval, 0) << '\n';
        logStream << "Check Interval                : " << Utility::numberFormat(logging.check_interval, 0) << '\n';

        if (!programLog.empty()) {
            logStream << programLog;
            if (programLog.back() != '\n') logStream << '\n';
        }

        std::ostringstream capturedOutput;
        {
            std::lock_guard<std::mutex> terminalLock(terminalMutex());
            std::streambuf* oldStream = std::cout.rdbuf(capturedOutput.rdbuf());
            std::cout << "\n\n\n";
            if (listChangedSettings) listChangedSettings();
            std::cout << "\n\n\n";
            if (printStats) printStats();
            std::cout.rdbuf(oldStream);
        }

        logStream << capturedOutput.str();
        return logStream.str();
    }

    inline void outputLog(const Config::Register& root,
                          const Config::Watch& logging,
                          const std::string& programLog = {},
                          const TString& logPath = "",
                          const std::function<void()>& printStats = {},
                          const std::function<void()>& listChangedSettings = {})
    {
        const TString targetLogPath = logPath.Length() > 0 ? logPath : root.logName;
        writeTextFile(targetLogPath, buildLogText(root, logging, programLog, printStats, listChangedSettings));
    }

    inline std::string buildEmergencyLogText(const Config::Register& root,
                                             const Config::Watch& logging,
                                              const RunSnapshot& snapshot,
                                              const std::string& programLog = {},
                                              const std::string& reason = {})
    {
        std::ostringstream stream;
        stream << "Emergency Shutdown            : fatal stall\n";
        if (!reason.empty()) stream << "Emergency Detail              : " << reason << '\n';
        stream << "Serial                        : " << std::setw(2) << std::setfill('0') << logging.serial << '\n';
        stream << "Beam Energy                   : " << root.beamEnergy.Data() << '\n';
        stream << "File Title                    : " << root.fileTitle.Data() << '\n';
        stream << "Root Output                   : " << root.outName.Data() << '\n';
        stream << "Main Log                      : " << root.logName.Data() << '\n';
        stream << "RunStat Log                   : " << root.runStatName.Data() << '\n';
        stream << "Last Event                    : " << Utility::numberFormat(snapshot.eventIndex, 0)
               << " / " << Utility::numberFormat(snapshot.nEvents, 0) << '\n';
        stream << "Real Event Count              : " << Utility::numberFormat(snapshot.nRealEvents, 0) << '\n';
        stream << "Phase                         : " << phaseString(snapshot.phase) << '\n';
        stream << "Elapsed                       : " << Utility::durationString(logging.elapsed, true) << '\n';
        stream << "Last Update                   : " << Utility::timeString(snapshot.lastUpdateTime, false) << '\n';
        stream << "Fatal Reason                  : " << snapshot.fatalReason << '\n';
        stream << "Stall Duration                : " << Utility::durationString(snapshot.stallDuration, true) << '\n';
        stream << "Stall Threshold               : "
               << Utility::durationString(std::chrono::duration_cast<Config::uSeconds>(snapshot.stallThreshold), true) << '\n';
        stream << "Fatal Multiplier              : " << snapshot.stallMultiplier << "x\n";
        if (!programLog.empty()) {
            stream << programLog;
            if (programLog.back() != '\n') stream << '\n';
        }
        return stream.str();
    }

    inline void writeEmergencyLog(const Config::Register& root,
                                  const Config::Watch& logging,
                                   const RunSnapshot& snapshot,
                                   const std::string& programLog = {},
                                   const std::string& reason = {})
    {
        writeTextFile(root.logName, buildEmergencyLogText(root, logging, snapshot, programLog, reason));
    }

    inline void terminalReport(const Config::Register& root, Config::Watch& logging,
                               const std::function<void()>& printStats = {}, bool stats = false) {
        std::lock_guard<std::mutex> terminalLock(terminalMutex());
        std::cout << "\n\n\n";
        if (stats && printStats) { printStats(); std::cout << "\n\n"; }
        const Config::TimePoint now = std::chrono::system_clock::now();
        logging.elapsed = std::chrono::duration_cast<Config::uSeconds>(now - logging.start);
        std::cout << "Finished :\n" << std::string(10, ' ')
                  << Utility::timeString(now)
                  << "\n" << std::string(10, ' ') << Utility::durationString(logging.elapsed) << std::endl;
        std::cout << "\nFile : " << root.outName.Data() << std::endl << std::endl;
    }
}
