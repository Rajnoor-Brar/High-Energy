#pragma once

#include <chrono>
#include <cmath>
#include <ctime>
#include <iomanip>
#include <sstream>
#include <string>

namespace Utility {

    // Canonical clock aliases for the whole utils layer. Config::Types.hh
    // re-exports these as Config::TimePoint etc. for existing call sites;
    // Utility itself must stay free of Config so it remains the bottom layer.
    using TimePoint = std::chrono::system_clock::time_point;
    using uSeconds  = std::chrono::microseconds;
    using Seconds   = std::chrono::seconds;
    // MonoPoint — monotonic clock for durations/stall detection. Wall-clock
    // TimePoint is for display only: NTP/DST steps must never look like
    // (or hide) a stall.
    using MonoPoint = std::chrono::steady_clock::time_point;

    constexpr bool highlightTime = true;
    constexpr bool preciseSeconds = true;

    inline std::tm localTime(const time_t& timeValue) {
        std::tm localTimeValue{};
        localtime_r(&timeValue, &localTimeValue);
        return localTimeValue;
    }

    inline std::string timeString(const time_t& timeValue, bool highlightClock = false) {
        const std::tm localTimeValue = localTime(timeValue);
        std::ostringstream stream;
        stream << std::put_time(
            &localTimeValue,
            highlightClock ? "%F \033[34;1m%T\033[0m " : "%F %T"
        );
        return stream.str();
    }

    inline std::string timeString(const TimePoint& timePoint, bool highlightClock = true) {
        return timeString(std::chrono::system_clock::to_time_t(timePoint), highlightClock);
    }

    inline std::string durationString(uSeconds duration, bool preciseSecond = false) {
        using Seconds = std::chrono::seconds;
        std::ostringstream stream;
        const int totalSeconds    = std::chrono::duration_cast<Seconds>(duration).count();
        const int expectedSeconds = totalSeconds % 60;
        const int expectedMinutes = (totalSeconds / 60) % 60;
        const int expectedHours   = (totalSeconds / 3600) % 24;
        const int expectedDays    = totalSeconds / 86400;
        const double totalSecondsPrecise =
            std::chrono::duration_cast<std::chrono::duration<double>>(duration).count();
        const double expectedSecondsPrecise = std::fmod(totalSecondsPrecise, 60.0);
        const double roundedSeconds         = std::round(expectedSecondsPrecise * 100.0) / 100.0;
        const bool singularPreciseSecond    = std::abs(roundedSeconds - 1.0) < 0.005;

        stream << (expectedDays    ? std::to_string(expectedDays)    + " day"    + (expectedDays    == 1 ? " " : "s ") : "")
               << (expectedHours   ? std::to_string(expectedHours)   + " hour"   + (expectedHours   == 1 ? " " : "s ") : "")
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
}
