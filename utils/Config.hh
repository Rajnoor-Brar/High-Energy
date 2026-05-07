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

    inline void configuration(const std::string& configPath,
                              const std::string& project,
                              Events&   events,
                              Watch&    watch,
                              Register& reg)
    {
        loadMonitorDefaults(watch, reg);
        limitExtractor(configPath, reg);

        toml::table config = toml::parse_file(configPath);

        readEventsSection(config, events, watch);
        readRecordSection(config, watch, reg);
        readLogSection   (config, watch, reg);
        readPathsAndFile(config, project, watch, reg);
    }

    inline void configuration(const std::string& configPath,
                              const std::string& project,
                              Watch&    watch,
                              Register& reg)
    {
        Events events;
        configuration(configPath, project, events, watch, reg);
    }

    inline void extractConfiguration(const std::string& configPath,
                                     const std::string& project,
                                     Watch&    watch,
                                     Register& reg)
    {
        configuration(configPath, project, watch, reg);
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
        configuration(configPath, project, py.eventConfig, watch, reg);

        toml::table config = toml::parse_file(configPath);
        readPythiaSection(config, py);

        if (!py.cmndFile.empty()) pythia.readFile(py.cmndFile);
        if (py.seed != 0) pythia.readString("Random:seed = " + std::to_string(py.seed));
        
        if (py.beamEnergy > 0) {
            pythia.readString("Beams:eCM = " + std::to_string(py.beamEnergy));
            reg.beamEnergy = Form("%.0f", py.beamEnergy);
        }
    }

    inline void configureProbe(const std::string& configPath,
                               const std::string& project,
                               Watch&       watch,
                               Register&    reg,
                               ProbeConfig& probe)
    {
        configuration(configPath, project, probe.eventConfig, watch, reg);

        toml::table config = toml::parse_file(configPath);
        readProbeSection(config, probe);
    }

} // namespace Config