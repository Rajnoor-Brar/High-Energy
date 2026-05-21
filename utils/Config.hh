#pragma once

// ── Config.hh ────────────────────────────────────────────────────────────────
// Dependency direction rules for the utils layer:
//
//   Config → Probe / Record / Monitor   ✓ allowed (Config owns runtime types)
//   Probe / Record / Monitor → Config   ✓ allowed (they read config state)
//   utils → Lambda module               ✗ disallowed (modules depend on utils)
//
// When a Config-owned type would duplicate a runtime type
// (e.g. the old ProbeParticle ≈ Probe::CollectionSpec), prefer to import
// the runtime type into Config rather than duplicate it.
//
// Config/Configure.hh is excluded from this header (circular via Probe.hh);
// drivers include it explicitly.

#include <stdexcept>
#include <string>

#include <toml++/toml.hpp>

#include "Config/Types.hh"
#include "Config/TypeAid.hh"
#include "Config/LimitAid.hh"
#include "Config/Defaults.hh"
#include "Config/Reader.hh"

namespace Config {

    namespace detail {
        // Applies all value-reading passes to an already-parsed table.
        // Shared by readConfigValues, configuration, configurePythia, configureProbe
        // so each entry point calls parseConfig exactly once.
        inline void applyConfigValues(const toml::table& config,
                                      Events& events, Watch& watch, Register& reg)
        {
            limitExtractor(config, reg);
            readEventsSection(config, events, watch);
            readRecordSection(config, watch, reg);
        }
    } // namespace detail

    // readConfigValues — parse and populate Watch/Register/Events without
    // creating any output directories.  Call readPathsAndFile separately once
    // the event count is fully resolved (e.g. after probe.configureProbe()).
    inline void readConfigValues(const std::string& configPath,
                                  const std::string& /*project*/,
                                  Events&   events,
                                  Watch&    watch,
                                  Register& reg)
    {
        toml::table config = parseConfig(configPath);
        rejectSectionAliases(config);
        detail::applyConfigValues(config, events, watch, reg);
    }

    // configuration — convenience wrapper for pipelines where the event count
    // is fixed at parse time (e.g. Pythia generation).
    inline void configuration(const std::string& configPath,
                              const std::string& project,
                              Events&   events,
                              Watch&    watch,
                              Register& reg)
    {
        toml::table config = parseConfig(configPath);
        rejectSectionAliases(config);
        detail::applyConfigValues(config, events, watch, reg);
        readPathsAndFile(config, project, watch, reg);
    }

    // PythiaT accepts both Pythia8::Pythia and Pythia8::PythiaParallel.
    template<typename PythiaT>
    inline void configurePythia(const std::string& configPath,
                                const std::string& project,
                                Watch&    watch,
                                Register& reg,
                                PythiaT&  pythia)
    {
        PythiaConfig py;
        toml::table config = parseConfig(configPath);
        rejectSectionAliases(config);
        detail::applyConfigValues(config, py.eventConfig, watch, reg);
        readPathsAndFile(config, project, watch, reg);
        readPythiaSection(config, py);

        if (!py.cmndFile.empty()) pythia.readFile(py.cmndFile);
        if (py.seed != 0) pythia.readString("Random:seed = " + std::to_string(py.seed));
        if (py.beamEnergy > 0) {
            pythia.readString("Beams:eCM = " + std::to_string(py.beamEnergy));
            reg.beamEnergy = Form("%.0f", py.beamEnergy);
        }
        if (py.pythia_threads > 0)
            pythia.readString("Parallelism:numThreads = " + std::to_string(py.pythia_threads));

        watch.n_threads = py.pythia_threads;
    }

    // configureProbe — populates Watch, Register, and ProbeConfig from TOML
    // without creating output directories.  The caller (Configure.hh) resolves
    // probe.eventCount() and then calls readPathsAndFile exactly once.
    inline void configureProbe(const std::string& configPath,
                               const std::string& project,
                               Watch&       watch,
                               Register&    reg,
                               ProbeConfig& probe)
    {
        toml::table config = parseConfig(configPath);
        rejectSectionAliases(config);
        detail::applyConfigValues(config, probe.eventConfig, watch, reg);
        readProbeSection(config, probe);
    }

} // namespace Config
