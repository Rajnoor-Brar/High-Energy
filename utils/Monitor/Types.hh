#pragma once

#include <cstddef>
#include <string>

#include "Config.hh"

namespace Monitor {

    inline constexpr std::size_t FatalStallMultiplier = 5;

    constexpr bool RenderStatus    = true;
    constexpr bool RenderBar       = true;
    constexpr bool WriteRunStat    = true;
    constexpr bool DontRenderStatus = false;
    constexpr bool DontRenderBar    = false;
    constexpr bool DontWriteRunStat = false;
    constexpr bool CallbackCompleted   = true;
    constexpr bool NoCallbackCompleted = false;
    constexpr std::size_t NoEvents = 0;

    enum class RunPhase    { Starting, Analysis, Finished };
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
        std::size_t       stallMultiplier = FatalStallMultiplier;
        std::string       fatalReason   = "";
    };

    struct PendingActions {
        bool renderStatus = false;
        bool renderBar    = false;
        bool writeRunStat = false;

        bool any() const { return renderStatus || renderBar || writeRunStat; }

        void merge(const PendingActions& other) {
            renderStatus |= other.renderStatus;
            renderBar    |= other.renderBar;
            writeRunStat |= other.writeRunStat;
        }
    };

    struct ThreadSnapshot {
        int               workerIndex       = -1;
        ThreadPhase       phase             = ThreadPhase::Simulation;
        std::size_t       eventIndex        = 0;
        std::size_t       callbacksCompleted = 0;
        Config::TimePoint lastUpdateTime    = Config::TimePoint{};
    };
}
