#pragma once

#include <cstddef>
#include <string>

#include "Config.hh"

namespace Monitor {

    struct PacingInfo {
        std::size_t      printInterval   = 10;
        std::size_t      barInterval     = 50;
        std::size_t      checkInterval   = 10000;
        Config::uSeconds heartbeatMs     = Config::uSeconds(1000);
        Config::Seconds  terminalRefresh = Config::Seconds(300);
        Config::Seconds  stallThreshold  = Config::Seconds(300);
    };

    constexpr bool RenderStatus    = true;
    constexpr bool RenderBar       = true;
    constexpr bool WriteRunStat    = true;
    constexpr bool DontRenderStatus = false;
    constexpr bool DontRenderBar    = false;
    constexpr bool DontWriteRunStat = false;
    constexpr bool CallbackCompleted   = true;
    constexpr bool NoCallbackCompleted = false;
    constexpr std::size_t NoEvents = 0;

    enum class RunPhase    { Starting, Configuring, Initialisation, Analysis, Finished };
    enum class ThreadPhase { Analysis, Simulation, Finished };

    struct RunSnapshot {
        std::size_t       eventIndex    = 0;
        std::size_t       nEvents       = 0;
        std::size_t       nRealEvents   = 0;
        Config::uSeconds  elapsed       = Config::uSeconds(0);
        std::string       eta           = "--";
        double            progress      = 0.0;
        RunPhase          phase         = RunPhase::Starting;
        Config::TimePoint lastUpdateTime = Config::TimePoint{};
        bool              fatalStall    = false;
        Config::uSeconds  stallDuration = Config::uSeconds(0);
        Config::Seconds   stallThreshold = Config::Seconds(0);
        std::size_t       stallMultiplier = 5;
        std::string       fatalReason   = "";
    };

    struct PendingActions {
        bool renderStatus = false;
        bool renderBar    = false;
        bool writeRunStat = false;

    };

    struct ThreadSnapshot {
        int               workerIndex       = -1;
        ThreadPhase       phase             = ThreadPhase::Simulation;
        std::size_t       eventIndex        = 0;
        std::size_t       callbacksCompleted = 0;
        Config::TimePoint lastUpdateTime    = Config::TimePoint{};
    };
}
