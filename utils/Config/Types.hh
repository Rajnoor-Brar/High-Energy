#pragma once

#include <atomic>
#include <chrono>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "TFile.h"
#include "TString.h"

#include "Physics/Types.hh"

namespace Config {

    // ── Property / level enums ────────────────────────────────────────────────
    // ParticleProperty / EventProperty live in Physics. Limits stay here
    // because RangeSize and Bounds are configuration concerns, not physics.
    struct Bounds {
        Double_t low{};
        Double_t high{};
    };

    enum class RangeSize : std::size_t {
        Minute,
        Small,
        Moderate,
        Large,
        Extreme
    };

    using TimePoint = std::chrono::system_clock::time_point;
    using uSeconds  = std::chrono::microseconds;
    using Seconds   = std::chrono::seconds;

    using LevelBounds    = std::map<RangeSize, Bounds>;
    using ParticleLimits = std::map<Physics::ParticleProperty, LevelBounds>;
    using EventLimits    = std::map<Physics::EventProperty,    LevelBounds>;

    // ── [events] ─────────────────────────────────────────────────────────────
    // Run-mode toggle plus shared event-loop sizing. The driver picks which
    // configure*() entry point to call based on Events::isPythia.
    struct Events {
        bool        isPythia    = true;
        std::size_t nThreads    = 0;     // 0 → resolveThreadCount() picks
        std::size_t eventCount  = 1000;
    };

    // ── [pythia] ─────────────────────────────────────────────────────────────
    struct PythiaConfig {
        Double_t    beamEnergy = 0.0;
        std::string cmndFile;
        int         seed       = 0;
    };

    // ── [probe] ──────────────────────────────────────────────────────────────
    // event_particles entry: [label, spec, tree_name, [branch_list]]
    struct ProbeParticle {
        std::string              label;
        int                      spec = 0;
        std::string              treeName;
        std::vector<std::string> branches;
    };

    struct ProbeConfig {
        std::string                inputFile;
        std::vector<ProbeParticle> particles;
    };

    // ── Monitor's running state (was Log) ────────────────────────────────────
    // Holds the live counters / pacing intervals the AsyncLogger watches.
    // Not copyable or movable (contains std::mutex + std::atomic).
    // Use freeze() for an intentional point-in-time snapshot.
    struct Watch {
        std::atomic<std::size_t> iEvent{0};
        Int_t                    serial = 0;
        std::size_t              srPadding = 2;
        std::size_t              nEvents = 100;
        std::size_t              nRealEvents = 0;
        std::size_t              nDigits = 0;
        std::size_t              nThreads = 0;
        std::size_t              printInterval = 10;
        uSeconds                 heartbeat_interval = uSeconds(1000);
        Seconds                  terminal_refresh_interval = Seconds(300);
        Seconds                  program_stall_threshold = Seconds(300);
        std::size_t              barInterval = 50;
        std::size_t              checkInterval = 10000;
        TimePoint                start = TimePoint{};
        uSeconds                 elapsed = uSeconds(0);

        Watch() = default;
        Watch(const Watch&)             = delete;
        Watch& operator=(const Watch&)  = delete;
        Watch(Watch&&)                  = delete;
        Watch& operator=(Watch&&)       = delete;

        // Thread-safe per-event accounting (defined in TypeAid.hh).
        // Increments nRealEvents and records elapsed time under eventMutex_.
        void recordEvent(TimePoint now);

        // Returns a heap-allocated point-in-time snapshot (defined in TypeAid.hh).
        // The returned Watch is completely independent of *this.
        std::unique_ptr<Watch> freeze() const;

      private:
        mutable std::mutex eventMutex_;
    };

    // ── Record output (was Root) ─────────────────────────────────────────────
    struct Register {
        TFile*      outFile         = nullptr;
        std::string inputPath;          // [events].input_file / legacy [input].root_file
        TString rootDirectory       = "output/";
        TString logDirectory        = "output/params/";
        TString checkpointDirectory = "output/checkpoints/";
        TString beamEnergy          = "";
        TString outName             = "";
        TString logName             = "";
        TString runStatName         = "";
        TString threadStatDirectory = "";
        TString checkpointOutName   = "";
        TString checkpointLogName   = "";
        TString fileTitle           = "";
        TString histLimitsFile      = "";
        ParticleLimits particleLimits{};
        EventLimits    eventLimits{};
        Int_t   binCount            = 100;
        Double_t histScale          = 100;
    };

    // ── Backwards-compat aliases ─────────────────────────────────────────────
    // Existing call sites use Config::Log / Config::Root; new code should use
    // Watch / Register. These aliases let the rename land without churning
    // every reference in Monitor/Record/Lambda at once.
    using Log  = Watch;
    using Root = Register;
}
