#pragma once

#include <algorithm>
#include <filesystem>
#include <string>
#include <thread>
#include <unistd.h>
#include <sys/ioctl.h>

#include "TString.h"
#include <toml++/toml.hpp>

#include "Types.hh"
#include "Utility.hh"
#include "Defaults.hh"

namespace fs = std::filesystem;

namespace Config {

    inline std::size_t resolveThreadCount(std::size_t requested) {
        if (requested > 0) return requested;
        const unsigned hw = std::thread::hardware_concurrency();
        return hw > 2 ? static_cast<std::size_t>(hw - 2) : 1;
    }

    inline void sanitiseLoggingConfig(Watch& watch) {
        static int wsCol = [] {
            struct winsize windowSize{};
            ioctl(STDOUT_FILENO, TIOCGWINSZ, &windowSize);
            return static_cast<int>(windowSize.ws_col);
        }();
        const std::size_t progressDivisor = static_cast<std::size_t>(std::max(1, wsCol - 6));
        std::size_t interval = watch.nEvents / progressDivisor;
        interval > 1 ? watch.bar_interval = interval : watch.bar_interval = 1;
        watch.print_interval = std::max<std::size_t>(1, watch.print_interval);
    }

    // ── Section helpers ──────────────────────────────────────────────────────

    inline void readEventsSection(const toml::table& config, Events& events, Watch& watch) {
        const bool hasEvents = config.contains("events");
        auto pythia = config["events"]["pythia"];
        auto probe   = config["events"]["probe"];
        events.isPythia = pythia ? pythia.value_or(true) : (probe ? !probe.value_or(true) : true);
        events.eventCount = static_cast<std::size_t>(
            hasEvents ? config["events"]["event_count"].value_or(1000)
                      : config["run"]["event_count"].value_or(1000));
        events.nThreads   = static_cast<std::size_t>(
            hasEvents ? config["events"]["nThreads"].value_or(0)
                      : config["run"]["nThreads"].value_or(0));

        watch.nEvents  = events.eventCount;
        watch.n_threads = events.nThreads;
    }


    inline void readRecordSection(const toml::table& config, Watch& watch, Register& reg) {
        const bool hasRecord = config.contains("record");
        watch.serial    = hasRecord ? config["record"]["serial"].value_or(0)
                                    : config["run"]["serial"].value_or(0);
        watch.sr_padding = static_cast<std::size_t>(
            hasRecord ? config["record"]["sr_padding"].value_or(2)
                      : config["run"]["sr_Padding"].value_or(2));

        if (hasRecord) {
            reg.binCount  = config["record"]["bin_count"].value_or(reg.binCount);
            reg.histScale = config["record"]["hist_scaling"].value_or(reg.histScale);
        }
    }

    inline void readLogSection(const toml::table& config, Watch& watch, Register& reg) {
        std::string logKey;
        if      (config.contains("monitor")) logKey = "monitor";
        else if (config.contains("log"))     logKey = "log";
        else if (config.contains("logging")) logKey = "logging";
        if (logKey.empty()) return;

        watch.print_interval = static_cast<std::size_t>(
            config[logKey]["print_interval"].value_or(static_cast<int64_t>(watch.print_interval)));
        watch.check_interval = static_cast<std::size_t>(
            config[logKey]["check_interval"].value_or(static_cast<int64_t>(watch.check_interval)));

        std::size_t hb = static_cast<std::size_t>(
            config[logKey]["heartbeat_interval"].value_or(static_cast<int64_t>(watch.heartbeat_interval.count())));
        watch.heartbeat_interval = uSeconds(hb);

        double tr = config[logKey]["terminal_refresh_interval"].value_or(
            static_cast<double>(watch.terminal_refresh_interval.count()) / 60.0);
        watch.terminal_refresh_interval = Seconds(static_cast<int>(60 * tr));

        double ps = config[logKey]["program_stall_threshold"].value_or(
            static_cast<double>(watch.program_stall_threshold.count()) / 60.0);
        watch.program_stall_threshold = Seconds(static_cast<int>(60 * ps));

        reg.binCount  = config[logKey]["bin_count"].value_or(reg.binCount);
        reg.histScale = config[logKey]["hist_scaling"].value_or(reg.histScale);
    }

    inline void readPathsAndFile(const toml::table& config,
                                 const std::string& project,
                                 Watch& watch, Register& reg) {
        const auto* pathsTbl = config["record"]["paths"].as_table();
        if (!pathsTbl) pathsTbl = config["paths"].as_table();
        const auto* fileTbl  = config["record"]["file"].as_table();
        if (!fileTbl)  fileTbl  = config["file"].as_table();

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

        const std::string serialStr = Form(
            ("_%0" + std::to_string((int)watch.sr_padding) + "d").c_str(), watch.serial);
        const std::string rootDir = serialSubDir ? (baseRootDir + serialStr + "/") : baseRootDir;

        reg.rootDirectory       = rootDir;
        reg.logDirectory        = logSubDir   ? rootDir + logBasePath   : logBasePath;
        reg.checkpointDirectory = checkSubDir ? rootDir + checkBasePath : checkBasePath;

        const std::string filePrefix = fileStr("prefix", "Unspecified");
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
        if (!config.contains("pythia")) return;
        py.beamEnergy = config["pythia"]["beam_energy"].value_or(py.beamEnergy);
        py.cmndFile   = config["pythia"]["cmnd_file"].value_or(py.cmndFile);
        py.seed       = config["pythia"]["seed"].value_or(py.seed);
    }

    inline void readProbeSection(const toml::table& config, ProbeConfig& probe) {
        if (!config.contains("probe")) return;
        probe.inputFile = config["probe"]["input_file"].value_or(probe.inputFile);

        const auto* arr = config["probe"]["event_particles"].as_array();
        if (!arr) return;
        probe.particles.clear();
        for (const auto& entry : *arr) {
            const auto* row = entry.as_array();
            if (!row || row->size() < 5) continue;
            ProbeParticle p;
            p.label    = (*row)[0].value_or(std::string{});
            p.spec     = (*row)[1].value_or(0);
            p.treeName = (*row)[2].value_or(std::string{});
            if (const auto* branchArr = (*row)[3].as_array()) {
                for (const auto& b : *branchArr)
                    p.branches.push_back(b.value_or(std::string{}));
            }
            probe.particles.push_back(std::move(p));
        }
    }
}
