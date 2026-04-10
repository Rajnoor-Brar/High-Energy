#pragma once

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <unistd.h>

#include "TFile.h"
#include "TString.h"

#include <sys/ioctl.h>
#include <toml++/toml.hpp>

namespace Config {
    using TimePoint = std::chrono::system_clock::time_point;
    using uSeconds  = std::chrono::microseconds;
    using Seconds   = std::chrono::seconds;

    struct Log {
        std::atomic<std::size_t> iEvent{0};
        Int_t                    serial = 0;
        std::size_t              srPadding = 2;
        std::size_t              nEvents = 100;
        std::size_t              nRealEvents = 0;
        std::size_t              nDigits = 0;
        std::size_t              printInterval = 10;
        uSeconds                 heartbeat_interval = uSeconds(1000);
        Seconds                  terminal_refresh_interval = Seconds(300);
        Seconds                  program_stall_threshold = Seconds(300);
        std::size_t              barInterval = 50;
        std::size_t              checkInterval = 10000;

        TimePoint          start = TimePoint{};
        uSeconds           elapsed = uSeconds(0);

        Log() = default;
        Log(const Log& other)
            : iEvent(other.iEvent.load()),
              serial(other.serial),
              srPadding(other.srPadding),
              nEvents(other.nEvents),
              nRealEvents(other.nRealEvents),
              nDigits(other.nDigits),
              printInterval(other.printInterval),
              heartbeat_interval(other.heartbeat_interval),
              terminal_refresh_interval(other.terminal_refresh_interval),
              program_stall_threshold(other.program_stall_threshold),
              barInterval(other.barInterval),
              checkInterval(other.checkInterval),
              start(other.start),
              elapsed(other.elapsed) {}

        Log& operator=(const Log& other) {
            if (this == &other) {
                return *this;
            }

            iEvent.store(other.iEvent.load());
            serial                    = other.serial;
            srPadding                 = other.srPadding;
            nEvents                   = other.nEvents;
            nRealEvents               = other.nRealEvents;
            nDigits                   = other.nDigits;
            printInterval             = other.printInterval;
            heartbeat_interval        = other.heartbeat_interval;
            terminal_refresh_interval = other.terminal_refresh_interval;
            program_stall_threshold   = other.program_stall_threshold;
            barInterval               = other.barInterval;
            checkInterval             = other.checkInterval;
            start                     = other.start;
            elapsed                   = other.elapsed;
            return *this;
        }
    };

    struct Root {
        TFile*  outFile       = nullptr;
        TString rootDirectory = "output/Lambda_Reconstruction/";
        TString logDirectory  = "output/Lambda_Reconstruction/params/";
        TString checkpointDirectory = "output/Lambda_Reconstruction/checkpoints/";
        TString beamEnergy    = "";
        TString outName       = "";
        TString logName       = "";
        TString runStatName   = "";
        TString threadStatDirectory = "";
        TString checkpointOutName = "";
        TString checkpointLogName = "";
        TString fileTitle     = "";
        Int_t   binCount      = 100;
        Double_t histScale    = 100;
    };

    #include <string>
#include <sstream>
#include <array>

inline std::string numberString(size_t value) {
    static constexpr std::array<const char*, 7> suffix = {
        "", "k", "M", "B", "T", "P", "E"
    };

    if (value == 0) return "0";

    std::stringstream ss;
    std::string result;

    size_t group = 0;

    while (value > 0) {
        size_t chunk = value % 1000;

        if (chunk != 0) {
            ss.str("");          
            ss.clear();
            ss << chunk << suffix[group];

            if (!result.empty())
                result = ss.str() + result;
            else
                result = ss.str();
        }

        value /= 1000;
        ++group;
    }

    return result;
}

    inline void applyEnvironmentOverrides(Log& logging) {
        if (const char* rawValue = std::getenv("LAMBDA_FORCE_HEARTBEAT_US")) {
            logging.heartbeat_interval = uSeconds(std::stoll(rawValue));
        }

        if (const char* rawValue = std::getenv("LAMBDA_FORCE_TERMINAL_REFRESH_SECONDS")) {
            logging.terminal_refresh_interval = Seconds(std::stoll(rawValue));
        }

        if (const char* rawValue = std::getenv("LAMBDA_FORCE_STALL_THRESHOLD_SECONDS")) {
            logging.program_stall_threshold = Seconds(std::stoll(rawValue));
        }
    }

    inline void sanitiseLoggingConfig(Log& logging) {
        static int wsCol = [] {
            struct winsize windowSize{};
            ioctl(STDOUT_FILENO, TIOCGWINSZ, &windowSize);
            return static_cast<int>(windowSize.ws_col);
        }();

        const std::size_t progressDivisor = static_cast<std::size_t>(std::max(1, wsCol - 6));
        std::size_t interval = logging.nEvents / progressDivisor;
        interval > 1 ? logging.barInterval = interval : logging.barInterval = 1;
        logging.printInterval = std::max<std::size_t>(1, logging.printInterval);
    }

    inline void extractConfiguration(
    const std::string& configPath,
    const std::string& project,
    Log& logging,
    Root& root
) {
    toml::table config = toml::parse_file(configPath);

    std::size_t temp = 0, nDigits = 0;
    double tempDouble = 0.0;

    // --- Logging ---
    logging.serial                    = config["run"]["serial"].value_or(0);
    logging.srPadding                 = static_cast<std::size_t>(config["run"]["sr_Padding"].value_or(2));
    logging.nEvents                   = static_cast<std::size_t>(config["run"]["event_count"].value_or(1000));
    logging.printInterval             = static_cast<std::size_t>(config["logging"]["print_interval"].value_or(100));
    logging.checkInterval             = static_cast<std::size_t>(config["logging"]["check_interval"].value_or(10000));
                temp                  = static_cast<std::size_t>(config["logging"]["heartbeat_interval"].value_or(1000));
    logging.heartbeat_interval        = uSeconds(temp);
                tempDouble            = config["logging"]["terminal_refresh_interval"].value_or(2.0);
    logging.terminal_refresh_interval = Seconds((int)(60 * tempDouble));
                tempDouble            = config["logging"]["program_stall_threshold"].value_or(5.0);
    logging.program_stall_threshold   = Seconds((int)(60 * tempDouble));
                temp = logging.nEvents;
                while (temp > 0) { ++nDigits; temp /= 10; }
    logging.nDigits                   = nDigits;
    applyEnvironmentOverrides(logging);
    sanitiseLoggingConfig(logging);

    root.binCount  = config["logging"]["bin_count"].value_or(100);
    root.histScale = config["logging"]["hist_scaling"].value_or(1.0);

    const bool logSubDir    = config["paths"]["logInSubDir"].value_or(true);
    const bool checkSubDir  = config["paths"]["checkpointInSubDir"].value_or(true);
    const bool serialSubDir = config["paths"]["serialDirectory"].value_or(true);

    std::string baseRootDir   = config["paths"]["directory"].value_or("output/" + project + "/");
    std::string logBasePath   = config["paths"]["output_log_directory"].value_or("params/");
    std::string checkBasePath = config["paths"]["checkpoint_directory"].value_or("checkpoints/");

    std::string serial = Form(("_%0" + std::to_string((int)logging.srPadding) + "d").c_str(), logging.serial);
\
    std::string rootDir = (serialSubDir) ? (baseRootDir+serial+ "/") : baseRootDir;
    root.rootDirectory = rootDir;

    root.logDirectory        = (logSubDir)   ? rootDir + logBasePath   : logBasePath;
    root.checkpointDirectory = (checkSubDir) ? rootDir + checkBasePath : checkBasePath;


    const std::string filePrefix = config["file"]["prefix"].value_or("Unspecified");
    const bool fileSerial = config["file"]["serial"].value_or(true);
    const bool fileEnergy = config["file"]["energy"].value_or(true);
    const bool fileEvents = config["file"]["events"].value_or(true);

    std::string fileTitle = filePrefix;

    if (fileSerial) fileTitle += serial;
    if (fileEnergy) fileTitle += "_" + std::string(root.beamEnergy.Data()) + "GeV";
    if (fileEvents) fileTitle += "_" + numberString(logging.nEvents);
    std::string threadDir = std::string("threads_")+(fileEnergy ? ("_" + std::string(root.beamEnergy.Data()) + "GeV") : "") + (fileEvents ? ("_" + numberString(logging.nEvents)) : "");
    root.fileTitle = fileTitle;

    root.outName             = Form("%s%s.root"           , root.rootDirectory.Data(), fileTitle.c_str());
    root.logName             = Form("%s%s.log"            , root.logDirectory.Data(), fileTitle.c_str());
    root.runStatName         = Form("%s%s_runstat.log"    , root.logDirectory.Data(), fileTitle.c_str());
    root.threadStatDirectory = Form("%s%s/"               , root.logDirectory.Data(), threadDir.c_str());
    root.checkpointOutName   = Form("%s%s_checkpoint.root", root.checkpointDirectory.Data(), fileTitle.c_str());
    root.checkpointLogName   = Form("%s%s_checkpoint.log" , root.checkpointDirectory.Data(), fileTitle.c_str());

    auto makeDirectory = [](const TString& file) {
        std::filesystem::create_directories(std::filesystem::path(file.Data()).parent_path());
    };

    makeDirectory(root.outName);
    makeDirectory(root.logName);
    makeDirectory(root.runStatName);
    makeDirectory(root.checkpointOutName);
    makeDirectory(root.checkpointLogName);
    std::filesystem::create_directories(root.threadStatDirectory.Data());

    // --- File ---
    root.outFile = new TFile(root.outName, "RECREATE");
}
}
