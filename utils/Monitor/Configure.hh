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

namespace Monitor {

    namespace detail {

        inline void rejectMovedMonitorKey(const toml::table& monitor,
                                          const char* key,
                                          const char* replacement)
        {
            if (!monitor.contains(key)) return;
            throw std::runtime_error(
                std::string("[Config] '[monitor].") + key +
                "' was removed; use '" + replacement + "'");
        }

        inline void validateMonitorSchema(const toml::table& config) {
            const auto* monitor = config["monitor"].as_table();
            if (!monitor) return;

            rejectMovedMonitorKey(*monitor, "print_interval",
                                  "[monitor.intervals].print_interval");
            if (monitor->contains("check_interval"))
                throw std::runtime_error(
                    "[Config] '[monitor.intervals].check_interval' was removed; "
                    "stall detection is time-based via program_stall_threshold");
            rejectMovedMonitorKey(*monitor, "heartbeat_interval",
                                  "[monitor.intervals].heartbeat_interval");
            rejectMovedMonitorKey(*monitor, "terminal_refresh_interval",
                                  "[monitor.intervals].terminal_refresh_interval");
            rejectMovedMonitorKey(*monitor, "program_stall_threshold",
                                  "[monitor.intervals].program_stall_threshold");
            rejectMovedMonitorKey(*monitor, "checkpoint_interval",
                                  "[monitor.intervals].checkpoint_interval");

            rejectMovedMonitorKey(*monitor, "save_heartbeat",
                                  "[monitor.logs].save_heartbeat");
            rejectMovedMonitorKey(*monitor, "save_checkpoints",
                                  "[monitor.logs].save_checkpoints");
            rejectMovedMonitorKey(*monitor, "save_log_threads",
                                  "[monitor.logs].save_log_threads");
            rejectMovedMonitorKey(*monitor, "save_final_log",
                                  "[monitor.logs].save_final_log");

            rejectMovedMonitorKey(*monitor, "bin_count", "[record].bin_count");
            rejectMovedMonitorKey(*monitor, "hist_scaling", "[record].hist_scaling");
        }

    } // namespace detail

    inline void configureMonitor(AsyncLogger& logger,
                                 const std::string& configPath,
                                 const std::string& /*project*/)
    {
        toml::table config = Config::parseConfig(configPath);

        // Only [monitor] is supported; legacy [log] / [logging] aliases were
        // removed for consistency with the rest of the TOML layout.
        if (config.contains("log") || config.contains("logging")) {
            throw std::runtime_error(
                "[Config] '[log]' / '[logging]' sections were removed; use "
                "'[monitor]' instead (see docs/WriterMT.md)");
        }

        detail::validateMonitorSchema(config);

        const auto* monitor  = config["monitor"].as_table();
        const auto* intervals = monitor ? (*monitor)["intervals"].as_table() : nullptr;
        const auto* logs      = monitor ? (*monitor)["logs"].as_table()      : nullptr;

        const bool trueTimeAtConfig = monitor
            ? (*monitor)["true_time_at_config"].value_or(false)
            : false;
        logger.markConfiguring(configPath, trueTimeAtConfig);

        PacingInfo p = logger.pacingInfo();  // start from current defaults

        if (intervals) {
            if (intervals->contains("check_interval"))
                throw std::runtime_error(
                    "[Config] '[monitor.intervals].check_interval' was removed; "
                    "stall detection is time-based via program_stall_threshold");

            p.printInterval = static_cast<std::size_t>(
                (*intervals)["print_interval"].value_or(static_cast<int64_t>(p.printInterval)));
            const std::size_t hb = static_cast<std::size_t>(
                (*intervals)["heartbeat_interval"].value_or(
                    static_cast<int64_t>(p.heartbeatMs.count())/1000));
            p.heartbeatMs = Config::uSeconds(hb*1000);

            const double tr = (*intervals)["terminal_refresh_interval"].value_or(
                static_cast<double>(p.terminalRefresh.count()) / 60.0);
            p.terminalRefresh = Config::Seconds(static_cast<int>(60 * tr));

            const double ps = (*intervals)["program_stall_threshold"].value_or(
                static_cast<double>(p.stallThreshold.count()) / 60.0);
            p.stallThreshold = Config::Seconds(static_cast<int>(60 * ps));
        }

        // Derive barInterval from window width and event count.
        struct winsize windowSize{};
        ioctl(STDOUT_FILENO, TIOCGWINSZ, &windowSize);
        const int wsCol = static_cast<int>(windowSize.ws_col);
        const std::size_t nEvents = logger.watch().nEvents;
        if (nEvents > 0) {
            const std::size_t divisor  = static_cast<std::size_t>(std::max(1, wsCol - 6));
            const std::size_t interval = nEvents / divisor;
            p.barInterval = interval > 1 ? interval : 1;
        }
        p.printInterval = std::max<std::size_t>(1, p.printInterval);

        logger.configurePacing(std::move(p));

        // docs/WriterMT.md Phase 1/5: the four [monitor.logs].save_* flags drive
        // which optional artifacts the logger produces.
        //
        //   save_heartbeat   — emit Heartbeat WatchRequests at print_interval
        //   save_checkpoints — emit Checkpoint WatchRequests at checkpoint_interval
        //   save_log_threads — accept publishThreadStats and write per-thread logs
        //   save_final_log   — write the final summary log at Writer::finish
        //
        // When a flag is false the corresponding code path becomes a no-op
        // (publishThreadStats early-returns, outputLog is skipped, etc.).
        if (monitor) {
            const bool        saveHeartbeat   = logs ? (*logs)["save_heartbeat"].value_or(false)   : false;
            const bool        saveCheckpoints = logs ? (*logs)["save_checkpoints"].value_or(false) : false;
            const bool        saveLogThreads  = logs ? (*logs)["save_log_threads"].value_or(false) : false;
            const bool        saveFinalLog    = logs ? (*logs)["save_final_log"].value_or(true)    : true;
            const std::size_t cpInterval      = static_cast<std::size_t>(
                intervals ? (*intervals)["checkpoint_interval"].value_or(static_cast<int64_t>(kDefaultCheckpointInterval))
                          : static_cast<int64_t>(100000));
            logger.configureWatchEmission(saveHeartbeat, saveCheckpoints, cpInterval);
            logger.configureArtifactEmission(saveLogThreads, saveFinalLog);
        }
    }

} // namespace Monitor
