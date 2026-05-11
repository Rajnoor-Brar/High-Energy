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

#include <type_traits>
#include <utility>

#include "Config.hh"
#include "Probe.hh"
#include "Record.hh"
#include "Monitor.hh"

namespace Config {

    // ── Pipeline-type tag ─────────────────────────────────────────────────────
    // SFINAE discriminator between the Probe pipeline (reads ROOT files via
    // ProbeParallel or ProbeIMT) and the Pythia pipeline (generates events
    // via Pythia8::Pythia or Pythia8::PythiaParallel).  Both pipeline
    // entry points share the name `configure` and the same signature shape;
    // this trait picks the right body at overload resolution.
    namespace detail {
        template<typename T>
        constexpr bool is_probe_runtime_v =
               std::is_same_v<T, Probe::ProbeParallel>
            || std::is_same_v<T, Probe::ProbeIMT>;
    }

    // ── Probe pipeline ────────────────────────────────────────────────────────
    // Reads the TOML once; populates probe, writer, and logger in the correct
    // order so that probe.eventCount() is resolved before the writer is opened
    // (allowing the output filename to embed the actual event count).
    //
    // Templated over ProbeT so both Probe::ProbeParallel (manual std::thread
    // pool, Phase 0/1) and Probe::ProbeIMT (TTreeProcessorMT-based, Phase 2)
    // work as drop-in substitutes.  Both expose identical configureProbe()
    // signatures and eventCount/threadCount/inputFile accessors.
    template<typename ProbeT,
             std::enable_if_t<detail::is_probe_runtime_v<ProbeT>, int> = 0>
    inline void configure(const std::string&     configPath,
                          const std::string&     project,
                          ProbeT&                probe,
                          Record::Writer&        writer,
                          Monitor::AsyncLogger&  logger)
    {

        Monitor::configureMonitor(logger, configPath, project);

        Register    reg;
        ProbeConfig probeConfig;
        configureProbe(configPath, project, logger.watch(), reg, probeConfig);

        // WriterMT.md Phase 0: per-section thread counts.  probe gets its own
        // count from [probe].thread_count; the Writer gets its own from
        // [record].thread_count (stored on reg).  Pythia overload below
        // applies its own [pythia].thread_count.
        probe.configureProbe(probeConfig.inputFile,
                             std::move(probeConfig.collections),
                             probeConfig.thread_count,
                             probeConfig.eventConfig.eventCount,
                             probeConfig.eventConfig.userEvents,
                             probeConfig.splitInput,
                             probeConfig.tempSpace,
                             probeConfig.keepShards,
                             reg.filePrefix);
        logger.watch().nEvents   = probe.eventCount();
        logger.watch().n_threads = probe.threadCount();   // Probe pipeline → Probe's count

        toml::table config = toml::parse_file(configPath);
        readPathsAndFile(config, project, logger.watch(), reg);

        Record::configureWriter(writer, project, configPath, logger.watch(), reg, probe.inputFile());
        // Hand the record thread count to the Writer.  Phase 0: stored only;
        // Phase 2 will spawn the worker pool sized to this value.
        writer.setRecordThreadCount(reg.recordThreadCount);
    }

    // ── Pythia pipeline ───────────────────────────────────────────────────────
    // PythiaT accepts both Pythia8::Pythia and Pythia8::PythiaParallel.
    // configurePythia reads [pythia].cmnd_file from TOML and calls readFile
    // internally. The fallback below captures Beams:eCM for the output filename
    // when [pythia].beam_energy was absent from the TOML.
    template<typename PythiaT,
             std::enable_if_t<!detail::is_probe_runtime_v<PythiaT>, int> = 0>
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
        // Hand the record thread count to the Writer; Phase 0 stub.
        writer.setRecordThreadCount(reg.recordThreadCount);
    }

} // namespace Config
