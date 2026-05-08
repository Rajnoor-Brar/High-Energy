#pragma once

#include <algorithm>
#include <string>

#include <sys/ioctl.h>
#include <unistd.h>

#include <toml++/toml.hpp>

#include "Monitor/Logger.hh"

namespace Monitor {

    inline void configureMonitor(AsyncLogger& logger,
                                 const std::string& configPath,
                                 const std::string& /*project*/)
    {
        toml::table config = toml::parse_file(configPath);

        std::string logKey;
        if      (config.contains("monitor")) logKey = "monitor";
        else if (config.contains("log"))     logKey = "log";
        else if (config.contains("logging")) logKey = "logging";

        const bool trueTimeAtConfig = config["monitor"]["true_time_at_config"].value_or(false);
        logger.markConfiguring(configPath, trueTimeAtConfig);

        PacingInfo p = logger.pacingInfo();  // start from current defaults

        if (!logKey.empty()) {
            p.printInterval = static_cast<std::size_t>(
                config[logKey]["print_interval"].value_or(static_cast<int64_t>(p.printInterval)));
            p.checkInterval = static_cast<std::size_t>(
                config[logKey]["check_interval"].value_or(static_cast<int64_t>(p.checkInterval)));

            const std::size_t hb = static_cast<std::size_t>( config[logKey]["heartbeat_interval"].value_or( static_cast<int64_t>(p.heartbeatMs.count())));
            p.heartbeatMs = Config::uSeconds(hb);

            const double tr = config[logKey]["terminal_refresh_interval"].value_or( static_cast<double>(p.terminalRefresh.count()) / 60.0);
            p.terminalRefresh = Config::Seconds(static_cast<int>(60 * tr));

            const double ps = config[logKey]["program_stall_threshold"].value_or( static_cast<double>(p.stallThreshold.count()) / 60.0);
            p.stallThreshold = Config::Seconds(static_cast<int>(60 * ps));
        }

        // Derive barInterval from window width and event count (mirrors old sanitiseLoggingConfig)
        static const int wsCol = [] {
            struct winsize windowSize{};
            ioctl(STDOUT_FILENO, TIOCGWINSZ, &windowSize);
            return static_cast<int>(windowSize.ws_col);
        }();
        const std::size_t nEvents = logger.watch().nEvents;
        if (nEvents > 0) {
            const std::size_t divisor  = static_cast<std::size_t>(std::max(1, wsCol - 6));
            const std::size_t interval = nEvents / divisor;
            p.barInterval = interval > 1 ? interval : 1;
        }
        p.printInterval = std::max<std::size_t>(1, p.printInterval);

        logger.configurePacing(std::move(p));
    }

} // namespace Monitor
