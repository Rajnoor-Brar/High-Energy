#pragma once

#include <algorithm>
#include <stdexcept>
#include <string>
#include <utility>

#include <sys/ioctl.h>
#include <unistd.h>

#include <toml++/toml.hpp>

#include "Config/Types.hh"
#include "Monitor/Administration.hh"
#include "Monitor/Directive.hh"

namespace Monitor {

    inline void configureMonitor(AsyncLogger& logger,
                                 const std::string& configPath,
                                 const std::string& /*project*/)
    {
        toml::table config = toml::parse_file(configPath);

        // Only [monitor] is supported; legacy [log] / [logging] aliases were
        // removed for consistency with the rest of the TOML layout.
        if (config.contains("log") || config.contains("logging")) {
            throw std::runtime_error(
                "[Config] '[log]' / '[logging]' sections were removed; use "
                "'[monitor]' instead (see docs/WriterMT.md)");
        }

        const bool trueTimeAtConfig = config["monitor"]["true_time_at_config"].value_or(false);
        logger.markConfiguring(configPath, trueTimeAtConfig);

        PacingInfo p = logger.pacingInfo();  // start from current defaults

        if (config.contains("monitor")) {
            p.printInterval = static_cast<std::size_t>(
                config["monitor"]["print_interval"].value_or(static_cast<int64_t>(p.printInterval)));
            p.checkInterval = static_cast<std::size_t>(
                config["monitor"]["check_interval"].value_or(static_cast<int64_t>(p.checkInterval)));

            const std::size_t hb = static_cast<std::size_t>(
                config["monitor"]["heartbeat_interval"].value_or(
                    static_cast<int64_t>(p.heartbeatMs.count())/1000));
            p.heartbeatMs = Config::uSeconds(hb*1000);

            const double tr = config["monitor"]["terminal_refresh_interval"].value_or(
                static_cast<double>(p.terminalRefresh.count()) / 60.0);
            p.terminalRefresh = Config::Seconds(static_cast<int>(60 * tr));

            const double ps = config["monitor"]["program_stall_threshold"].value_or(
                static_cast<double>(p.stallThreshold.count()) / 60.0);
            p.stallThreshold = Config::Seconds(static_cast<int>(60 * ps));
        }

        // Derive barInterval from window width and event count.
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

        // docs/WriterMT.md Phase 1/5: the four [monitor].save_* flags drive
        // which optional artifacts the logger produces.
        //
        //   save_heartbeat   — emit Heartbeat WatchRequests at print_interval
        //   save_checkpoints — emit Checkpoint WatchRequests at checkpoint_interval
        //   save_log_threads — accept publishThreadStats and write per-thread logs
        //   save_final_log   — write the final summary log at Writer::finish
        //
        // When a flag is false the corresponding code path becomes a no-op
        // (publishThreadStats early-returns, outputLog is skipped, etc.).
        if (config.contains("monitor")) {
            const bool        saveHeartbeat   = config["monitor"]["save_heartbeat"].value_or(false);
            const bool        saveCheckpoints = config["monitor"]["save_checkpoints"].value_or(false);
            const bool        saveLogThreads  = config["monitor"]["save_log_threads"].value_or(false);
            const bool        saveFinalLog    = config["monitor"]["save_final_log"].value_or(true);
            const std::size_t cpInterval      = static_cast<std::size_t>(
                config["monitor"]["checkpoint_interval"].value_or(static_cast<int64_t>(100000)));
            logger.configureWatchEmission(saveHeartbeat, saveCheckpoints, cpInterval);
            logger.configureArtifactEmission(saveLogThreads, saveFinalLog);
        }
    }

} // namespace Monitor
