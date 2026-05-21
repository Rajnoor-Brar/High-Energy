#pragma once

#include <chrono>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <string>

#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

#include "Config/Types.hh"
#include "Utility/Number.hh"
#include "Utility/Time.hh"
#include "Monitor/Logger.hh"
#include "Monitor/Methods.hh"

namespace Monitor {

    inline termios& savedTermios() {
        static termios oldt{};
        return oldt;
    }

    inline void disable_input_echo() {
        termios newt;
        tcgetattr(STDIN_FILENO, &savedTermios());
        newt = savedTermios();
        newt.c_lflag &= ~(ECHO | ICANON);
        tcsetattr(STDIN_FILENO, TCSANOW, &newt);
    }

    inline void restore_terminal() {
        tcsetattr(STDIN_FILENO, TCSANOW, &savedTermios());
    }

    inline std::mutex& terminalMutex() {
        static std::mutex mutex;
        return mutex;
    }

    inline void AsyncLogger::initializeTerminal() {
        if (terminalInitialized_) return;
        std::cout << "\n\n\n" << std::flush;
        terminalInitialized_ = true;
    }

    inline void renderProgressBar(double progress) {
        struct winsize windowSize{};
        ioctl(STDOUT_FILENO, TIOCGWINSZ, &windowSize);
        constexpr char done = '=';
        constexpr char toDo = '-';
        const int nCols      = windowSize.ws_col ? static_cast<int>(windowSize.ws_col) - 6 : 100;
        const int filledCols = static_cast<int>(progress * nCols);
        std::cout << "\r \033[32;1m|" << std::string(filledCols, done) << "\033[0m"
                  << (progress < 1.0 ? ">\033[31m" : std::string("\033[32;1m") + done)
                  << std::string(nCols - filledCols, toDo) << "|\033[0m"
                  << "\033[J\r" << std::flush;
    }

    inline void AsyncLogger::renderStatusLine(const RunSnapshot& snapshot) {
        const std::size_t percent = snapshot.nEvents > 0
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
                      << "\t\033[34;1m Configuring from " << snapshot.eta
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

}
