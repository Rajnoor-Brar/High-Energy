#pragma once

#include <cstddef>
#include <chrono>
#include <cmath>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <type_traits>
#include <vector>

#include <sys/ioctl.h>
#include <unistd.h>

#include "Pythia8/Pythia.h"

#include "Config.hh"

namespace Record {

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
        std::ostringstream stream;
        stream << std::put_time(
            std::localtime(&timeValue),
            highlightClock ? "%F \033[34;1m%T\033[0m " : "%F %T"
        );
        return stream.str();
    }

    inline std::string timeString(const Config::TimePoint& timePoint, bool highlightClock = true) {
        const time_t localTime = std::chrono::system_clock::to_time_t(timePoint);
        return timeString(localTime, highlightClock);
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
                              : (!(expectedDays || expectedHours || expectedMinutes) ? " about now" : "")));

        return stream.str();
    }

    inline std::string updatedETA(std::size_t iEvent, std::size_t nEvents, Config::uSeconds duration) {
        using SysClock = std::chrono::system_clock;

        if (nEvents < iEvent || iEvent == 0) {
            return "ETA: --";
        }

        const double remainder = (nEvents - iEvent) / static_cast<double>(iEvent);
        const auto waitTime    = std::chrono::duration_cast<Config::uSeconds>(remainder * duration);

        std::ostringstream eta;
        const time_t expectedTime = SysClock::to_time_t(SysClock::now() + waitTime);

        eta << "\033[2K\tETA : " << timeString(expectedTime)
            << " in " << durationString(waitTime);
        return eta.str();
    }

    inline void printProgressStat(
        std::size_t iEvent,
        std::size_t nEvents,
        std::size_t nDigits,
        const std::string& eta
    ) {
        static_cast<void>(nDigits);
        const std::size_t percent = nEvents > 0
            ? static_cast<std::size_t>((100.0 * static_cast<double>(iEvent)) / static_cast<double>(nEvents))
            : 0;
        const std::size_t eventWidth = numberFormat(nEvents, 0).size();

        std::cout << std::setfill(' ') << "\033[2A\r"
                  << "\t Events processed : " << "\033[32;1m" << numberFormat(iEvent, eventWidth) << "\033[0m"
                  << " out of " << numberFormat(nEvents, 0) << "  |  "
                  << std::setw(2) << percent << "% \033[B\r" << eta << "\033[B\r" << std::flush;
    }

    inline void printProgressBar(double progress) {
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

    template <typename PythiaT>
    void terminalReport(PythiaT& pythia, const Config::Root& root, Config::Log& logging, bool stats=false) {

        std::cout << "\n\n\n";
        if (stats){
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

    template <typename PythiaT>
    void outputLog(
        PythiaT& pythia,
        const Config::Root& root,
        const Config::Log& logging,
        const std::string& programLog = {},
        const TString& logPath = ""
    ) {
        const char* targetLogPath = logPath.Length() > 0 ? logPath.Data() : root.logName.Data();
        std::ofstream logStream(targetLogPath, std::ios::trunc);
        const time_t localStart = std::chrono::system_clock::to_time_t(logging.start);

        logStream << "Serial                        : " << std::setw(2) << std::setfill('0') << logging.serial << std::endl;
        logStream << "Beam Energy                   : " << root.beamEnergy.Data() << std::endl;
        logStream << "Event Count                   : " << numberFormat(logging.nEvents, 0) << std::endl;
        logStream << "Real Event Count              : " << numberFormat(logging.nRealEvents, 0) << std::endl;
        logStream << "Last Run                      : " << timeString(localStart,false) << std::endl;
        logStream << "Time Taken                    : " << durationString(logging.elapsed) << std::endl;
        logStream << "Time Taken / 1000 Events      : " << durationString((1000 * logging.elapsed) / logging.nEvents, true) << std::endl;
        logStream << "Histogram Scale               : " << root.histScale << std::endl;
        logStream << "Progress Bar Update Interval  : " << numberFormat(logging.barInterval, 0) << std::endl;
        logStream << "Check Interval                : " << numberFormat(logging.checkInterval, 0) << std::endl;

        if (!programLog.empty()) {
            logStream << programLog;
            if (programLog.back() != '\n') {
                logStream << '\n';
            }
        }

        std::streambuf* oldStream = std::cout.rdbuf();
        std::cout.rdbuf(logStream.rdbuf());
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
}
