#pragma once

#include <cstddef>
#include <iomanip>
#include <sstream>
#include <string>

#include "Config.hh"
#include "Utility.hh"
#include "Monitor/Types.hh"

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

    inline const char* phaseString(RunPhase phase) {
        switch (phase) {
            case RunPhase::Starting:       return "Starting";
            case RunPhase::Configuring:    return "Configuring";
            case RunPhase::Initialisation: return "Initialisation";
            case RunPhase::Analysis:       return "Analysis";
            case RunPhase::Finished:       return "Finished";
        }
        return "Unknown";
    }

    inline const char* threadPhaseString(ThreadPhase phase) {
        switch (phase) {
            case ThreadPhase::Analysis:   return "Analysis";
            case ThreadPhase::Simulation: return "Simulation";
            case ThreadPhase::Finished:   return "Finished";
        }
        return "Unknown";
    }

    inline const char* statusString(RunPhase phase) {
        switch (phase) {
            case RunPhase::Starting:       return "Starting";
            case RunPhase::Configuring:    return "Configuring";
            case RunPhase::Initialisation: return "Initialising";
            case RunPhase::Finished:       return "Finished";
            default:                       return "Running";
        }
    }

    inline RunSnapshot makeSnapshot(const Config::Watch& logging, RunPhase phase) {
        RunSnapshot snapshot;
        snapshot.eventIndex    = logging.iEvent;
        snapshot.nEvents       = logging.nEvents;
        snapshot.nRealEvents   = logging.n_real_events.load(std::memory_order_relaxed);
        snapshot.elapsed       = logging.elapsed.load(std::memory_order_relaxed);
        snapshot.eta           = updatedETA(logging.iEvent, logging.nEvents,
                                            logging.elapsed.load(std::memory_order_relaxed), false);
        snapshot.progress      = logging.nEvents > 0
            ? static_cast<double>(logging.iEvent) / static_cast<double>(logging.nEvents)
            : 0.0;
        snapshot.phase         = phase;
        snapshot.lastUpdateTime = std::chrono::system_clock::now();
        return snapshot;
    }

    inline std::string runStatString(const RunSnapshot& snapshot, const Config::TimePoint& now) {
        std::ostringstream stream;
        const auto idleFor  = std::chrono::duration_cast<Config::uSeconds>(now - snapshot.lastUpdateTime);
        const std::size_t percent = snapshot.nEvents > 0
            ? static_cast<std::size_t>(100.0 * snapshot.progress) : 0;

        stream << "Status                        : " << statusString(snapshot.phase) << '\n';
        stream << "Phase                         : " << phaseString(snapshot.phase) << '\n';
        stream << "Event                         : " << Utility::numberFormat(snapshot.eventIndex, 0)
               << " / " << Utility::numberFormat(snapshot.nEvents, 0) << '\n';
        stream << "Real Event Count              : " << Utility::numberFormat(snapshot.nRealEvents, 0) << '\n';
        stream << "Completion                    : " << percent << "%\n";
        stream << "Elapsed                       : " << Utility::durationString(snapshot.elapsed, true) << '\n';
        stream << "ETA                           : " << snapshot.eta << '\n';
        stream << "Last Update                   : " << Utility::timeString(snapshot.lastUpdateTime, false) << '\n';
        stream << "No Update For                 : " << Utility::durationString(idleFor) << '\n';

        if (snapshot.fatalStall) {
            stream << "Fatal Stall                   : YES\n";
            stream << "Fatal Reason                  : " << snapshot.fatalReason << '\n';
            stream << "Stall Duration                : " << Utility::durationString(snapshot.stallDuration, true) << '\n';
            stream << "Stall Threshold               : "
                   << Utility::durationString(std::chrono::duration_cast<Config::uSeconds>(snapshot.stallThreshold), true) << '\n';
            stream << "Fatal Multiplier              : " << snapshot.stallMultiplier << "x\n";
        }
        return stream.str();
    }

    inline std::string threadStatString(const ThreadSnapshot& snapshot, const Config::TimePoint& now) {
        std::ostringstream stream;
        const auto idleFor = std::chrono::duration_cast<Config::uSeconds>(now - snapshot.lastUpdateTime);
        stream << "Worker Index                  : " << std::setw(2) << std::setfill('0') << snapshot.workerIndex << '\n';
        stream << "Thread Phase                  : " << threadPhaseString(snapshot.phase) << '\n';
        stream << "Last Global Event             : " << Utility::numberFormat(snapshot.eventIndex, 0) << '\n';
        stream << "Events Completed              : " << Utility::numberFormat(snapshot.callbacksCompleted, 0) << '\n';
        stream << "Last Update                   : " << Utility::timeString(snapshot.lastUpdateTime, false) << '\n';
        stream << "Idle For                      : " << Utility::durationString(idleFor) << '\n';
        return stream.str();
    }
}
