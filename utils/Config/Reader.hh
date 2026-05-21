#pragma once

#include <algorithm>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "TString.h"
#include <toml++/toml.hpp>

#include "Types.hh"
#include "Utility.hh"
#include "Defaults.hh"
#include "Probe/ConfigAid.hh"

namespace fs = std::filesystem;

namespace Config {

    namespace detail {

        // mergeTables — recursive TOML table merge (src into dst).
        // Sub-tables are merged key-by-key; all other node types overwrite.
        // Arrays are replaced wholesale (not element-merged) so that
        //   results = ["a","b"]  in a later file replaces  results = ["x"]
        // from an earlier file.
        inline void mergeTables(toml::table& dst, const toml::table& src) {
            for (const auto& [key, val] : src) {
                const std::string k{key.str()};
                toml::node* existing = dst.get(k);
                if (existing && existing->is_table() && val.is_table())
                    mergeTables(*existing->as_table(), *val.as_table());
                else
                    dst.insert_or_assign(k, val);
            }
        }

    } // namespace detail

    // parseConfig — unified config loader used everywhere instead of bare
    // toml::parse_file().
    //
    // If configPath is a regular file: equivalent to toml::parse_file(configPath).
    //
    // If configPath is a directory: reads every *.toml file in the directory
    // (non-recursive, alphabetical by filename) and merges them left-to-right
    // into a single master table.  Sub-tables are merged recursively, so
    // splitting a config across files works naturally:
    //
    //   config/00_events.toml  -> [events] event_count = 100000
    //   config/01_probe.toml   -> [probe] input_file = "..."  [probe.events.particles.*]
    //   config/02_record.toml  -> [record] serial = 5  [record.paths] ...
    //   config/03_lambda.toml  -> [lambda] delta_mass_gev = 0.15
    //
    // Keys in later files (alphabetically) overwrite the same keys from earlier
    // files, allowing targeted per-run overrides without editing the base files.
    inline toml::table parseConfig(const std::string& configPath) {
        if (!fs::is_directory(configPath))
            return toml::parse_file(configPath);

        std::vector<std::string> paths;
        for (const auto& entry : fs::directory_iterator(configPath)) {
            if (entry.is_regular_file() && entry.path().extension() == ".toml")
                paths.push_back(entry.path().string());
        }

        if (paths.empty())
            throw std::runtime_error(
                "[Config] directory '" + configPath + "' contains no .toml files");

        std::sort(paths.begin(), paths.end());

        toml::table master;
        for (const auto& p : paths) {
            toml::table t = toml::parse_file(p);
            detail::mergeTables(master, t);
        }
        return master;
    }

    // resolveThreadCount — used by drivers that take a manual thread count.
    // Leaves 2 cores for OS / interactive tasks.
    inline std::size_t resolveThreadCount(std::size_t requested) {
        if (requested > 0) return requested;
        const unsigned hw = std::thread::hardware_concurrency();
        return hw > 2 ? static_cast<std::size_t>(hw - 2) : 1;
    }

    // resolveSectionThreadCount — per-section default.
    // Each of [probe], [record], [pythia] gets one third of (hw-2) cores. Floored at 1.
    inline std::size_t resolveSectionThreadCount(std::size_t requested) {
        if (requested > 0) return requested;
        const unsigned hw = std::thread::hardware_concurrency();
        if (hw <= 2) return 1;
        return std::max<std::size_t>(1, static_cast<std::size_t>((hw - 2) / 3));
    }

    // resolveThreadKey — looks up a thread count with two-level precedence:
    //   1. [threads].<globalKey>   (shared defaults block, checked first)
    //   2. [<section>].<sectionKey> (per-section override)
    //   3. auto (hardware / 3)
    inline std::size_t resolveThreadKey(const toml::table& config,
                                        const char* globalKey,
                                        const char* section,
                                        const char* sectionKey) {
        if (const auto v = config["threads"][globalKey].value<int64_t>(); v && *v > 0)
            return resolveSectionThreadCount(static_cast<std::size_t>(*v));
        return resolveSectionThreadCount(
            static_cast<std::size_t>(config[section][sectionKey].value_or(0)));
    }

    // ── Section helpers ──────────────────────────────────────────────────────

    inline void rejectSectionAliases(const toml::table& config) {
        if (config.contains("run")) {
            throw std::runtime_error(
                "[Config] '[run]' was removed; use '[events]' for event_count "
                "and '[record]' for record serial/path settings");
        }
        if (config.contains("paths")) {
            throw std::runtime_error(
                "[Config] top-level '[paths]' was removed; use '[record.paths]'");
        }
        if (config.contains("file")) {
            throw std::runtime_error(
                "[Config] top-level '[file]' was removed; use '[record.file]'");
        }
        if (config.contains("metadata")) {
            throw std::runtime_error(
                "[Config] top-level '[metadata]' was removed; use '[record.metadata]'");
        }
        if (config.contains("log") || config.contains("logging")) {
            throw std::runtime_error(
                "[Config] '[log]' / '[logging]' sections were removed; use "
                "'[monitor]' instead");
        }
    }

    inline void readEventsSection(const toml::table& config, Events& events, Watch& watch) {
        const auto evNode = config["events"]["event_count"];
        if (evNode) {
            events.eventCount = static_cast<std::size_t>(evNode.value_or<int64_t>(1000));
            events.userEvents = true;
        } else {
            events.eventCount = 1000;
            events.userEvents = false;
        }

        if (config["events"]["nThreads"]) {
            throw std::runtime_error(
                "[Config] '[events].nThreads' was removed; set "
                "'[probe].probe_threads', '[record].writer_threads', or "
                "'[pythia].pythia_threads' instead "
                "(see docs/WriterMT.md Phase 0)");
        }

        watch.nEvents   = events.eventCount;
        // watch.n_threads is set later by the pipeline-specific configure()
        // overload to that pipeline's primary thread count.
    }


    inline void readRecordSection(const toml::table& config, Watch& /*watch*/, Register& reg) {
        const bool hasRecord = config.contains("record");
        reg.serial = hasRecord ? config["record"]["serial"].value_or(0) : 0;
        // sr_padding is a local in readPathsAndFile — not stored on Watch.

        if (hasRecord) {
            reg.binCount  = config["record"]["bin_count"].value_or(reg.binCount);
            reg.histScale = config["record"]["hist_scaling"].value_or(reg.histScale);
            if (config["record"]["thread_count"]) {
                throw std::runtime_error(
                    "[Config] '[record].thread_count' was renamed; use '[record].writer_threads'");
            }
            reg.writer_threads = resolveThreadKey(config, "writer", "record", "writer_threads");
            reg.writer_queue_capacity = static_cast<std::size_t>(
                config["record"]["writer_queue_capacity"].value_or(0));
        } else {
            reg.writer_threads = resolveThreadKey(config, "writer", "record", "writer_threads");
        }
    }

    inline void readPathsAndFile(const toml::table& config,
                                 const std::string& project,
                                 Watch& watch, Register& reg) {
        const auto* pathsTbl = config["record"]["paths"].as_table();
        const auto* fileTbl  = config["record"]["file"].as_table();

        const auto fromPaths = [pathsTbl](const char* key, auto fallback) {
            if (!pathsTbl) return fallback;
            return (*pathsTbl)[key].value_or(fallback);
        };
        const auto fromFile = [fileTbl](const char* key, auto fallback) {
            if (!fileTbl) return fallback;
            return (*fileTbl)[key].value_or(fallback);
        };

        const bool logSubDir    = fromPaths("logInSubDir",           true);
        const bool checkSubDir  = fromPaths("checkpointsInSubDir",   true);
        const bool serialSubDir = fromPaths("serialDirectory",        true);
        const std::string baseRootDir   = fromPaths("directory",            "output/" + project + "/");
        const std::string logBasePath   = fromPaths("output_log_directory", std::string{"params/"});
        const std::string checkBasePath = fromPaths("checkpoint_directory", std::string{"checkpoints/"});

        const std::size_t sr_padding = static_cast<std::size_t>(
            config["record"]["sr_padding"].value_or(2));

        const std::string serialStr = Form(
            ("_%0" + std::to_string((int)sr_padding) + "d").c_str(), (int)reg.serial);
        const std::string rootDir = serialSubDir ? (baseRootDir + serialStr + "/") : baseRootDir;

        reg.rootDirectory       = rootDir;
        reg.logDirectory        = logSubDir   ? rootDir + logBasePath   : logBasePath;
        reg.checkpointDirectory = checkSubDir ? rootDir + checkBasePath : checkBasePath;

        const std::string filePrefix = fromFile("prefix", std::string{"Unspecified"});
        reg.filePrefix = filePrefix;   // stored for shard-dir derivation in Configure.hh
        const bool fileSerial = fromFile("serial", true);
        const bool fileEnergy = fromFile("energy", true);
        const bool fileEvents = fromFile("events", true);

        std::string fileTitle = filePrefix;
        if (fileSerial) fileTitle += serialStr;
        if (fileEnergy) fileTitle += "_" + reg.beamEnergy + "GeV";
        if (fileEvents) fileTitle += "_" + Utility::numberString(watch.nEvents);

        std::string threadDir = std::string("threads_") +
            (fileEnergy ? ("_" + reg.beamEnergy + "GeV") : "") +
            (fileEvents ? ("_" + Utility::numberString(watch.nEvents)) : "");

        reg.fileTitle = fileTitle;

        reg.outName             = reg.rootDirectory       + fileTitle + ".root";
        reg.logName             = reg.logDirectory        + fileTitle + ".log";
        reg.runStatName         = reg.logDirectory        + fileTitle + "_runstat.log";
        reg.threadStatDirectory = reg.logDirectory        + threadDir + "/";
        reg.checkpointOutName   = reg.checkpointDirectory + fileTitle + "_checkpoint.root";
        reg.checkpointLogName   = reg.checkpointDirectory + fileTitle + "_checkpoint.log";

        auto makeDir = [](const std::string& file) {
            fs::create_directories(fs::path(file).parent_path());
        };
        for (const std::string* path : {&reg.outName, &reg.logName, &reg.runStatName,
                                         &reg.checkpointOutName, &reg.checkpointLogName})
            makeDir(*path);
        fs::create_directories(reg.threadStatDirectory);
    }

    inline void readPythiaSection(const toml::table& config, PythiaConfig& py) {
        if (!config.contains("pythia")) {
            py.pythia_threads = resolveThreadKey(config, "pythia", "pythia", "pythia_threads");
            return;
        }
        py.beamEnergy = config["pythia"]["beam_energy"].value_or(py.beamEnergy);
        py.cmndFile   = config["pythia"]["cmnd_file"].value_or(py.cmndFile);
        py.seed       = config["pythia"]["seed"].value_or(py.seed);
        if (config["pythia"]["thread_count"]) {
            throw std::runtime_error(
                "[Config] '[pythia].thread_count' was renamed; use '[pythia].pythia_threads'");
        }
        py.pythia_threads = resolveThreadKey(config, "pythia", "pythia", "pythia_threads");
    }

    inline void readProbeSection(const toml::table& config, ProbeConfig& probe) {
        if (!config.contains("probe")) {
            probe.probe_threads    = resolveThreadKey(config, "probe",    "probe", "probe_threads");
            probe.analysis_threads = resolveThreadKey(config, "analysis", "probe", "analysis_threads");
            return;
        }
        probe.inputFile = config["probe"]["input_file"].value_or(probe.inputFile);

        // Phase 11: legacy event_particles=[...] format removed; always use parseProbeConfig.
        probe.probeSpec = Probe::parseProbeConfig(config);

        if (config["probe"]["thread_count"]) {
            throw std::runtime_error(
                "[Config] '[probe].thread_count' was renamed; use '[probe].probe_threads'");
        }
        probe.probe_threads    = resolveThreadKey(config, "probe",    "probe", "probe_threads");
        probe.analysis_threads = resolveThreadKey(config, "analysis", "probe", "analysis_threads");

        const std::string cbMode =
            config["probe"]["callback_mode"].value_or(std::string("CollectorThread"));
        probe.callback_mode = (cbMode == "WorkerThread")
            ? Probe::CallbackMode::WorkerThread
            : Probe::CallbackMode::CollectorThread;

        probe.queue_capacity = static_cast<std::size_t>(
            config["probe"]["queue_capacity"].value_or(0));
    }
}
