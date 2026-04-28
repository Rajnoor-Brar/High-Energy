#pragma once

#include <chrono>
#include <cstddef>
#include <sstream>
#include <string>

#include "Config.hh"
#include "Utility.hh"

namespace Monitor {

    inline std::string updatedETA(std::size_t iEvent, std::size_t nEvents, Config::uSeconds duration, bool highlightClock = true) {
        using SysClock = std::chrono::system_clock;
        if (nEvents < iEvent || iEvent == 0) return "--";
        const double remainder = (nEvents - iEvent) / static_cast<double>(iEvent);
        const auto waitTime    = std::chrono::duration_cast<Config::uSeconds>(remainder * duration);
        std::ostringstream eta;
        eta << Utility::timeString(SysClock::to_time_t(SysClock::now() + waitTime), highlightClock)
            << " in " << Utility::durationString(waitTime);
        return eta.str();
    }
}
