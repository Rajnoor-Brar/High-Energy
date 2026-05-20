#pragma once

// Config/Configure.hh — single-call configure() facade for Probe/Writer/Logger; included explicitly by drivers (not by Config.hh, to avoid circular deps).

#include <type_traits>
#include <utility>

#include "Config.hh"
#include "Probe.hh"
#include "Record.hh"
#include "Monitor.hh"

namespace Config {

    // SFINAE tag: distinguishes Probe pipeline (ProbeParallel/ProbeIMT) from Pythia pipeline.
    namespace detail {
        template<typename T>
        constexpr bool is_probe_runtime_v =
               std::is_same_v<T, Probe::ProbeParallel>
            || std::is_same_v<T, Probe::ProbeIMT>;
    }

    // Probe pipeline — resolves event count before opening the writer so output filenames embed actual counts.
    template<typename ProbeT,
             std::enable_if_t<detail::is_probe_runtime_v<ProbeT>, int> = 0>
    inline void configure(const std::string&     configPath,
                          const std::string&     project,
                          ProbeT&                probe,
                          Record::Writer&        writer,
                          Monitor::AsyncLogger&  logger)
    {
        Register    reg;
        ProbeConfig probeConfig;
        configureProbe(configPath, project, logger.watch(), reg, probeConfig);

        probe.configureProbe(probeConfig.inputFile,
                             std::move(probeConfig.collections),
                             probeConfig.probe_threads,
                             probeConfig.eventConfig.eventCount,
                             probeConfig.eventConfig.userEvents);
        probe.setAnalysisThreadCount(probeConfig.analysis_threads);
        probe.setCallbackMode(probeConfig.callback_mode);
        if (probeConfig.queue_capacity > 0)
            probe.setQueueCapacity(probeConfig.queue_capacity);

        logger.watch().nEvents   = probe.eventCount();
        logger.watch().n_threads = probe.threadCount();

        // configureMonitor after event count is resolved so barInterval is correct.
        Monitor::configureMonitor(logger, configPath, project);

        toml::table config = toml::parse_file(configPath);
        readPathsAndFile(config, project, logger.watch(), reg);

        Record::configureWriter(writer, project, configPath, logger.watch(), reg, probe.inputFile());
        writer.setRecordThreadCount(reg.writer_threads);
        if (reg.writer_queue_capacity > 0)
            writer.setQueueCapacity(reg.writer_queue_capacity);
    }

    // Pythia pipeline — falls back to Beams:eCM when [pythia].beam_energy is absent from TOML.
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
        writer.setRecordThreadCount(reg.writer_threads);
        if (reg.writer_queue_capacity > 0)
            writer.setQueueCapacity(reg.writer_queue_capacity);
    }

} // namespace Config
