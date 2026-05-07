#pragma once

#include <atomic>
#include <chrono>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "TFile.h"
#include "TString.h"

#include "Physics/Types.hh"
#include "Probe/Types.hh"

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
    // Shared event-loop sizing. Driver selects the appropriate configure*()
    // overload directly (Probe or Pythia pipeline).
    struct Events {
        std::size_t nThreads    = 0;     // 0 → resolveThreadCount() picks
        std::size_t eventCount  = 1000;
        bool        userEvents  = false; // true when event_count was explicit in TOML
    };

    // ── [pythia] ─────────────────────────────────────────────────────────────
    struct PythiaConfig {
        Double_t    beamEnergy = 0.0;
        std::string cmndFile;
        int         seed       = 0;
        Events      eventConfig;
    };

    // ── [probe] ──────────────────────────────────────────────────────────────
    // ProbeConfig holds the parsed [probe] section.  Collections are stored as
    // Probe::CollectionSpec directly — no intermediate ProbeParticle type.
    // Populated by Config::configureProbe via Probe::parseCollectionsFromToml.
    struct ProbeConfig {
        std::string                           inputFile;
        std::vector<Probe::CollectionSpec>    collections;
        Events                                eventConfig;
    };

    // ── Monitor's live run counters ───────────────────────────────────────────
    // Holds hot-path counters the event loop and AsyncLogger share.
    // Not copyable or movable (contains std::atomic members).
    // Use freeze() for an intentional point-in-time snapshot.
    //
    // n_real_events and elapsed are both std::atomic; recordEvent() is
    // lock-free.  Configuration-identity fields (serial, sr_padding,
    // n_digits) were removed in W9 — they live in Record::Paths / Register.
    struct Watch {
        std::atomic<std::size_t> iEvent{0};
        std::size_t              nEvents   = 100;
        std::atomic<std::size_t> n_real_events{0};
        std::size_t              n_threads = 0;
        TimePoint                start     = TimePoint{};
        std::atomic<uSeconds>    elapsed{uSeconds(0)};

        Watch() = default;
        Watch(const Watch&)             = delete;
        Watch& operator=(const Watch&)  = delete;
        Watch(Watch&&)                  = delete;
        Watch& operator=(Watch&&)       = delete;

        // Lock-free per-event accounting (defined in TypeAid.hh).
        // Increments n_real_events and records elapsed time atomically.
        void recordEvent(TimePoint now);

        // Returns a heap-allocated point-in-time snapshot (defined in TypeAid.hh).
        // The returned Watch is completely independent of *this.
        std::unique_ptr<Watch> freeze() const;
    };

    // ── Record output staging buffer ─────────────────────────────────────────
    // Transitional working buffer for Config readers; consumed by
    // Record::configureWriter which mirrors fields into the Writer.
    // serial was added in W9 (moved from Watch).
    // Full Register deletion is the W9 endpoint; the residual paths/limits
    // live here only because Config::Reader.hh writes into them during parsing.
    struct Register {
        Int_t   serial              = 0;
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
        Int_t    binCount           = 100;
        Double_t histScale          = 100;
    };

}
