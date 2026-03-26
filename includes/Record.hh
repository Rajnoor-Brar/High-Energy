#pragma once

#include <chrono>
#include <cmath>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <type_traits>

#include <sys/ioctl.h>
#include <unistd.h>

#include "Pythia8/Pythia.h"

#include "Config.hh"

namespace Record {

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

    inline std::string updatedETA(int iEvent, int nEvents, Config::uSeconds duration) {
        using SysClock = std::chrono::system_clock;

        if (nEvents < iEvent || iEvent <= 0) {
            return "ETA: --";
        }

        const double remainder = (nEvents - iEvent) / static_cast<double>(iEvent);
        const auto waitTime    = std::chrono::duration_cast<Config::uSeconds>(remainder * duration);

        std::ostringstream eta;
        const time_t expectedTime = SysClock::to_time_t(SysClock::now() + waitTime);

        eta << "\033[2K\tETA : " << std::put_time(std::localtime(&expectedTime), "%F %T ")
            << " in " << durationString(waitTime);
        return eta.str();
    }

    inline void printProgressStat(int iEvent, int nEvents, int nDigits, const std::string& eta) {
        std::cout << std::setfill(' ') << "\033[2A\r"
                  << "\t Events processed : " << std::setw(nDigits) << iEvent << " out of " << nEvents << "  |  "
                  << std::setw(2) << 100 * iEvent / nEvents << "% \033[B\r" << eta << "\033[B\r" << std::flush;
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
                  << ">"
                  << "\033[31m" << std::string(nCols - filledCols, toDo) << "|\033[0m"
                  << std::flush;
    }

    template <typename PythiaT>
    void terminalReport(PythiaT& pythia, const Config::Root& root, Config::Log& logging) {
        std::cout << "\n\n\n";
        pythia.stat();
        std::cout << "\n\n";

        const Config::TimePoint now = std::chrono::system_clock::now();
        const time_t localNow       = std::chrono::system_clock::to_time_t(now);
        logging.elapsed             = std::chrono::duration_cast<Config::uSeconds>(now - logging.start);

        std::cout << "Finished :\n" << std::string(10, ' ')
                  << std::put_time(std::localtime(&localNow), "%F %T")
                  << "\n" << std::string(10, ' ') << durationString(logging.elapsed) << std::endl;
        std::cout << "\nFile Title : " << root.fileTitle.Data() << std::endl << std::endl;
    }

    template <typename PythiaT>
    void outputLog(
        PythiaT& pythia,
        const Config::Root& root,
        const Config::Log& logging,
        const std::string& programLog = {}
    ) {
        std::ofstream logStream(root.logName.Data(), std::ios::trunc);
        const time_t localStart = std::chrono::system_clock::to_time_t(logging.start);

        logStream << "Serial                        : " << std::setw(2) << std::setfill('0') << logging.serial << std::endl;
        logStream << "Beam Energy                   : " << root.beamEnergy.Data() << std::endl;
        logStream << "Event Count                   : " << logging.nEvents << std::endl;
        logStream << "Real Event Count              : " << logging.nRealEvents << std::endl;
        logStream << "Last Run                      : " << std::put_time(std::localtime(&localStart), "%F %T") << std::endl;
        logStream << "Time Taken                    : " << durationString(logging.elapsed) << std::endl;
        logStream << "Time Taken / 1000 Events      : " << durationString((1000 * logging.elapsed) / logging.nEvents, true) << std::endl;
        logStream << "Histogram Scale               : " << root.histScale << std::endl;
        logStream << "Progress Bar Update Interval  : " << logging.barInterval << std::endl;

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
