#pragma once

#include <algorithm>
#include <filesystem>
#include <string>
#include <thread>

#include "TString.h"
#include <toml++/toml.hpp>

#include "Types.hh"
#include "Utility.hh"
#include "Defaults.hh"
#include "Probe/ConfigAid.hh"

namespace fs = std::filesystem;

namespace Config {

    // resolveThreadCount — used by drivers that take a manual thread count.
    // Leaves 2 cores for OS / interactive tasks.
    inline std::size_t resolveThreadCount(std::size_t requested) {
        if (requested > 0) return requested;
        const unsigned hw = std::thread::hardware_concurrency();
        return hw > 2 ? static_cast<std::size_t>(hw - 2) : 1;
    }

    // resolveSectionThreadCount — per-section default for the WriterMT.md
    // Phase 0 migration.  Each of [probe], [record], [pythia] gets one
    // third of the (hw - 2) available cores.  Floored at 1.
    inline std::size_t resolveSectionThreadCount(std::size_t requested) {
        if (requested > 0) return requested;
        const unsigned hw = std::thread::hardware_concurrency();
        if (hw <= 2) return 1;
        return std::max<std::size_t>(1, static_cast<std::size_t>((hw - 2) / 3));
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
            reg.writer_threads = resolveSectionThreadCount(
                static_cast<std::size_t>(config["record"]["writer_threads"].value_or(0)));
            reg.writer_queue_capacity = static_cast<std::size_t>(
                config["record"]["writer_queue_capacity"].value_or(0));
        } else {
            reg.writer_threads = resolveSectionThreadCount(0);
        }
    }

    inline void validateMonitorSection(const toml::table& config) {
        const auto* monitor = config["monitor"].as_table();
        if (!monitor) return;

        const auto rejectMovedKey = [monitor](const char* key, const char* replacement) {
            if (!monitor->contains(key)) return;
            throw std::runtime_error(
                std::string("[Config] '[monitor].") + key +
                "' was removed; use '" + replacement + "'");
        };

        rejectMovedKey("print_interval", "[monitor.intervals].print_interval");
        rejectMovedKey("check_interval", "[monitor.intervals].check_interval");
        rejectMovedKey("heartbeat_interval", "[monitor.intervals].heartbeat_interval");
        rejectMovedKey("terminal_refresh_interval", "[monitor.intervals].terminal_refresh_interval");
        rejectMovedKey("program_stall_threshold", "[monitor.intervals].program_stall_threshold");
        rejectMovedKey("checkpoint_interval", "[monitor.intervals].checkpoint_interval");

        rejectMovedKey("save_heartbeat", "[monitor.logs].save_heartbeat");
        rejectMovedKey("save_checkpoints", "[monitor.logs].save_checkpoints");
        rejectMovedKey("save_log_threads", "[monitor.logs].save_log_threads");
        rejectMovedKey("save_final_log", "[monitor.logs].save_final_log");

        rejectMovedKey("bin_count", "[record].bin_count");
        rejectMovedKey("hist_scaling", "[record].hist_scaling");
    }

    inline void readPathsAndFile(const toml::table& config,
                                 const std::string& project,
                                 Watch& watch, Register& reg) {
        if (config.contains("paths")) {
            throw std::runtime_error(
                "[Config] top-level '[paths]' was removed; use '[record.paths]'");
        }
        if (config.contains("file")) {
            throw std::runtime_error(
                "[Config] top-level '[file]' was removed; use '[record.file]'");
        }

        const auto* pathsTbl = config["record"]["paths"].as_table();
        const auto* fileTbl  = config["record"]["file"].as_table();

        const auto pathStr = [pathsTbl](const char* key, std::string fallback) {
            if (!pathsTbl) return fallback;
            return (*pathsTbl)[key].value_or(fallback);
        };
        const auto pathBool = [pathsTbl](const char* key, bool fallback) {
            if (!pathsTbl) return fallback;
            return (*pathsTbl)[key].value_or(fallback);
        };
        const auto fileStr = [fileTbl](const char* key, std::string fallback) {
            if (!fileTbl) return fallback;
            return (*fileTbl)[key].value_or(fallback);
        };
        const auto fileBool = [fileTbl](const char* key, bool fallback) {
            if (!fileTbl) return fallback;
            return (*fileTbl)[key].value_or(fallback);
        };

        const bool logSubDir    = pathBool("logInSubDir", true);
        const bool checkSubDir  = pathBool("checkpointsInSubDir", true);
        const bool serialSubDir = pathBool("serialDirectory", true);
        const std::string baseRootDir   = pathStr("directory", "output/" + project + "/");
        const std::string logBasePath   = pathStr("output_log_directory", "params/");
        const std::string checkBasePath = pathStr("checkpoint_directory", "checkpoints/");

        const std::size_t sr_padding = static_cast<std::size_t>(
            config["record"]["sr_padding"].value_or(2));

        const std::string serialStr = Form(
            ("_%0" + std::to_string((int)sr_padding) + "d").c_str(), (int)reg.serial);
        const std::string rootDir = serialSubDir ? (baseRootDir + serialStr + "/") : baseRootDir;

        reg.rootDirectory       = rootDir;
        reg.logDirectory        = logSubDir   ? rootDir + logBasePath   : logBasePath;
        reg.checkpointDirectory = checkSubDir ? rootDir + checkBasePath : checkBasePath;

        const std::string filePrefix = fileStr("prefix", "Unspecified");
        reg.filePrefix = filePrefix;   // stored for shard-dir derivation in Configure.hh
        const bool fileSerial = fileBool("serial", true);
        const bool fileEnergy = fileBool("energy", true);
        const bool fileEvents = fileBool("events", true);

        std::string fileTitle = filePrefix;
        if (fileSerial) fileTitle += serialStr;
        if (fileEnergy) fileTitle += "_" + std::string(reg.beamEnergy.Data()) + "GeV";
        if (fileEvents) fileTitle += "_" + Utility::numberString(watch.nEvents);

        std::string threadDir = std::string("threads_") +
            (fileEnergy ? ("_" + std::string(reg.beamEnergy.Data()) + "GeV") : "") +
            (fileEvents ? ("_" + Utility::numberString(watch.nEvents)) : "");

        reg.fileTitle = fileTitle;

        reg.outName            = Form("%s%s.root",            reg.rootDirectory.Data(), fileTitle.c_str());
        reg.logName            = Form("%s%s.log",             reg.logDirectory.Data(),  fileTitle.c_str());
        reg.runStatName        = Form("%s%s_runstat.log",     reg.logDirectory.Data(),  fileTitle.c_str());
        reg.threadStatDirectory= Form("%s%s/",                reg.logDirectory.Data(),  threadDir.c_str());
        reg.checkpointOutName  = Form("%s%s_checkpoint.root", reg.checkpointDirectory.Data(), fileTitle.c_str());
        reg.checkpointLogName  = Form("%s%s_checkpoint.log",  reg.checkpointDirectory.Data(), fileTitle.c_str());

        auto makeDir = [](const TString& file) {
            fs::create_directories(fs::path(file.Data()).parent_path());
        };
        for (const TString* path : {&reg.outName, &reg.logName, &reg.runStatName,
                                     &reg.checkpointOutName, &reg.checkpointLogName})
            makeDir(*path);
        fs::create_directories(reg.threadStatDirectory.Data());
    }

    inline void readPythiaSection(const toml::table& config, PythiaConfig& py) {
        if (!config.contains("pythia")) {
            py.pythia_threads = resolveSectionThreadCount(0);
            return;
        }
        py.beamEnergy = config["pythia"]["beam_energy"].value_or(py.beamEnergy);
        py.cmndFile   = config["pythia"]["cmnd_file"].value_or(py.cmndFile);
        py.seed       = config["pythia"]["seed"].value_or(py.seed);
        if (config["pythia"]["thread_count"]) {
            throw std::runtime_error(
                "[Config] '[pythia].thread_count' was renamed; use '[pythia].pythia_threads'");
        }
        py.pythia_threads = resolveSectionThreadCount(
            static_cast<std::size_t>(config["pythia"]["pythia_threads"].value_or(0)));
    }

    inline void readProbeSection(const toml::table& config, ProbeConfig& probe) {
        if (!config.contains("probe")) {
            probe.probe_threads    = resolveSectionThreadCount(0);
            probe.analysis_threads = resolveSectionThreadCount(0);
            return;
        }
        probe.inputFile   = config["probe"]["input_file"].value_or(probe.inputFile);
        probe.collections = Probe::parseCollectionsFromToml(config);
        if (config["probe"]["thread_count"]) {
            throw std::runtime_error(
                "[Config] '[probe].thread_count' was renamed; use '[probe].probe_threads'");
        }
        probe.probe_threads = resolveSectionThreadCount(
            static_cast<std::size_t>(config["probe"]["probe_threads"].value_or(0)));
        probe.analysis_threads = resolveSectionThreadCount(
            static_cast<std::size_t>(config["probe"]["analysis_threads"].value_or(0)));

        const std::string cbMode =
            config["probe"]["callback_mode"].value_or(std::string("CollectorThread"));
        probe.callback_mode = (cbMode == "WorkerThread")
            ? Probe::CallbackMode::WorkerThread
            : Probe::CallbackMode::CollectorThread;

        probe.queue_capacity = static_cast<std::size_t>(
            config["probe"]["queue_capacity"].value_or(0));
    }
}
