#pragma once

// ── Config/Configure.hh ──────────────────────────────────────────────────────
// Defines Config::configure — the single-call facade that fully configures the
// three runtime objects (Probe::ProbeParallel or PythiaT, Record::Writer,
// Monitor::AsyncLogger) from a TOML config path and project name.
//
// This header is NOT included by Config.hh because it depends on Probe.hh,
// Record.hh, and Monitor.hh which themselves depend on Config.hh (circular).
// Drivers include it explicitly after their other umbrella includes.
//
// Dependency direction: Configure.hh → Config, Probe, Record, Monitor.

#include <utility>

#include "Config.hh"
#include "Probe.hh"
#include "Record.hh"
#include "Monitor.hh"

namespace Config {

    // ── Probe pipeline ────────────────────────────────────────────────────────
    // Reads the TOML once; populates probe, writer, and logger in the correct
    // order so that probe.eventCount() is resolved before the writer is opened
    // (allowing the output filename to embed the actual event count).
    inline void configure(const std::string&     configPath,
                          const std::string&     project,
                          Probe::ProbeParallel&  probe,
                          Record::Writer&        writer,
                          Monitor::AsyncLogger&  logger)
    {

        Monitor::configureMonitor(logger, configPath, project);

        Register    reg;
        ProbeConfig probeConfig;
        configureProbe(configPath, project, logger.watch(), reg, probeConfig);

        probe.configureProbe(probeConfig.inputFile,
                             std::move(probeConfig.collections),
                             probeConfig.eventConfig.nThreads,
                             probeConfig.eventConfig.eventCount,
                             probeConfig.eventConfig.userEvents);
        logger.watch().nEvents   = probe.eventCount();
        logger.watch().n_threads = probe.threadCount();

        toml::table config = toml::parse_file(configPath);
        readPathsAndFile(config, project, logger.watch(), reg);

        Record::configureWriter(writer, project, configPath, logger.watch(), reg, probe.inputFile());
    }

    // ── Pythia pipeline ───────────────────────────────────────────────────────
    // PythiaT accepts both Pythia8::Pythia and Pythia8::PythiaParallel.
    // configurePythia reads [pythia].cmnd_file from TOML and calls readFile
    // internally. The fallback below captures Beams:eCM for the output filename
    // when [pythia].beam_energy was absent from the TOML.
    template<typename PythiaT>
    inline void configure(const std::string&    configPath,
                          const std::string&    project,
                          PythiaT&              pythia,
                          Record::Writer&       writer,
                          Monitor::AsyncLogger& logger)
    {

        Monitor::configureMonitor(logger, configPath, project);
        Register reg;
        configurePythia(configPath, project, logger.watch(), reg, pythia);

        // Beam-energy fallback: if [pythia].beam_energy was absent from TOML,
        // read from the already-loaded Pythia settings (set by readFile).
        if (reg.beamEnergy.IsNull() || reg.beamEnergy.IsWhitespace() || reg.beamEnergy == "") {
            const double ecm = pythia.settings.parm("Beams:eCM");
            if (ecm > 0) reg.beamEnergy = Form("%.0f", ecm);
        }

        Record::configureWriter(writer, project, configPath, logger.watch(), reg, "");
    }

} // namespace Config
