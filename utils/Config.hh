#pragma once

#include <atomic>
#include <chrono>
#include <filesystem>
#include <sstream>
#include <stdexcept>
#include <string>
#include <optional>
#include <thread>
#include <unistd.h>
#include <map>
#include <array>

#include "TFile.h"
#include "TString.h"
#include <sys/ioctl.h>
#include <toml++/toml.hpp>

namespace Config {
    using TimePoint = std::chrono::system_clock::time_point;
    using uSeconds  = std::chrono::microseconds;
    using Seconds   = std::chrono::seconds;
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

    enum class Quantity : std::size_t {
        Mass_Invariant,
        Mass_Transverse,
        Energy_Net,
        Energy_Transverse,
        Momentum_Net,
        Momentum_Transverse,
        Momentum_X,
        Momentum_Y,
        Momentum_Z,
        Rapidity,
        Pseudorapidity,
        Azimuthal_Angle,
        Multiplicity
    };
    using LimitTable = std::map<Quantity, std::map<RangeSize, Bounds>>;

    struct Log {
        std::atomic<std::size_t> iEvent{0};
        Int_t                    serial = 0;
        std::size_t              srPadding = 2;
        std::size_t              nEvents = 100;
        std::size_t              nRealEvents = 0;
        std::size_t              nDigits = 0;
        std::size_t              nThreads = 0;
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
              nThreads(other.nThreads),
              printInterval(other.printInterval),
              heartbeat_interval(other.heartbeat_interval),
              terminal_refresh_interval(other.terminal_refresh_interval),
              program_stall_threshold(other.program_stall_threshold),
              barInterval(other.barInterval),
              checkInterval(other.checkInterval),
              start(other.start),
              elapsed(other.elapsed) {}

        Log& operator=(const Log& other) {
            if (this == &other) return *this;
            iEvent.store(other.iEvent.load());
            serial                    = other.serial;
            srPadding                 = other.srPadding;
            nEvents                   = other.nEvents;
            nRealEvents               = other.nRealEvents;
            nDigits                   = other.nDigits;
            nThreads                  = other.nThreads;
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
        TString rootDirectory = "output/";
        TString logDirectory  = "output/params/";
        TString checkpointDirectory = "output/checkpoints/";
        TString beamEnergy    = "";
        TString outName       = "";
        TString logName       = "";
        TString runStatName   = "";
        TString threadStatDirectory = "";
        TString checkpointOutName = "";
        TString checkpointLogName = "";
        TString fileTitle     = "";
        TString histLimitsFile = "";
        LimitTable limits{};
        Int_t   binCount      = 100;
        Double_t histScale    = 100;
    };

    // Resolves a requested thread count to a usable value:
    // 0 → hardware_concurrency() - 2 (clamped to >= 1); otherwise returned as-is.
    inline std::size_t resolveThreadCount(std::size_t requested) {
        if (requested > 0) return requested;
        const unsigned hw = std::thread::hardware_concurrency();
        return hw > 2 ? static_cast<std::size_t>(hw - 2) : 1;
    }

    inline std::string numberString(size_t value) {
        static constexpr std::array<const char*, 7> suffix = {"", "k", "M", "B", "T", "P", "E"};
        if (value == 0) return "0";
        std::stringstream ss;
        std::string result;
        size_t group = 0;
        while (value > 0) {
            size_t chunk = value % 1000;
            if (chunk != 0) {
                ss.str(""); ss.clear();
                ss << chunk << suffix[group];
                result = ss.str() + result;
            }
            value /= 1000;
            ++group;
        }
        return result;
    }

    inline RangeSize stringToLevel(const std::string& levelStr) {
        if (levelStr == "Minute")   return RangeSize::Minute;
        if (levelStr == "Small")    return RangeSize::Small;
        if (levelStr == "Moderate") return RangeSize::Moderate;
        if (levelStr == "Large")    return RangeSize::Large;
        if (levelStr == "Extreme")  return RangeSize::Extreme;
        throw std::runtime_error("Unknown limit level: " + levelStr);
    }

    inline std::optional<Quantity> tryStringToQuantity(const std::string& qStr) {
        if (qStr == "Mass_Invariant" || qStr == "Mass") return Quantity::Mass_Invariant;
        if (qStr == "Mass_Transverse")     return Quantity::Mass_Transverse;
        if (qStr == "Energy_Net" || qStr == "Energy")  return Quantity::Energy_Net;
        if (qStr == "Energy_Transverse")   return Quantity::Energy_Transverse;
        if (qStr == "Momentum_Net")        return Quantity::Momentum_Net;
        if (qStr == "Momentum_Transverse") return Quantity::Momentum_Transverse;
        if (qStr == "Momentum_X")          return Quantity::Momentum_X;
        if (qStr == "Momentum_Y")          return Quantity::Momentum_Y;
        if (qStr == "Momentum_Z")          return Quantity::Momentum_Z;
        if (qStr == "Rapidity")            return Quantity::Rapidity;
        if (qStr == "Pseudorapidity")      return Quantity::Pseudorapidity;
        if (qStr == "Azimuthal_Angle")     return Quantity::Azimuthal_Angle;
        if (qStr == "Multiplicity")        return Quantity::Multiplicity;
        return std::nullopt;
    }

    inline Quantity stringToQuantity(const std::string& qStr) {
        if (auto q = tryStringToQuantity(qStr)) return *q;
        throw std::runtime_error("Unknown quantity: " + qStr);
    }

    inline Bounds parseBoundsArray(const toml::array& boundsArray, const std::string& filePath, const std::string& quantityName, const std::string& levelName) {
        if (boundsArray.size() != 2) {
            throw std::runtime_error("Expected exactly 2 values for " + quantityName + "." + levelName + " in " + filePath);
        }

        const auto low = boundsArray[0].value<Double_t>();
        const auto high = boundsArray[1].value<Double_t>();
        if (!low || !high) {
            throw std::runtime_error("Expected numeric bounds for " + quantityName + "." + levelName + " in " + filePath);
        }

        return {*low, *high};
    }

    inline std::string resolveLimitsPath(const std::string& limitsName) {
        if (limitsName.empty()) {
            throw std::runtime_error("Histogram limits file name must not be empty");
        }

        if (limitsName.find('/') != std::string::npos) return limitsName;
        if (limitsName.size() >= 5 && limitsName.substr(limitsName.size() - 5) == ".toml") return "configs/" + limitsName;
        return "configs/" + limitsName + ".toml";
    }

    inline void loadLimitsFile(const std::string& filePath, LimitTable& limits) {
        if (!std::filesystem::exists(filePath)) {
            throw std::runtime_error("Limits file does not exist: " + filePath);
        }

        toml::table table = toml::parse_file(filePath);
        for (auto&& [quantityKey, quantityValue] : table) {
            if (!quantityValue.is_table()) continue;

            const std::string quantityName = std::string(quantityKey.str());
            const auto quantity = tryStringToQuantity(quantityName);
            if (!quantity) continue;
            toml::table& quantityTable = *quantityValue.as_table();

            for (auto&& [levelKey, levelValue] : quantityTable) {
                if (!levelValue.is_array()) continue;

                const std::string levelName = std::string(levelKey.str());
                const RangeSize level = stringToLevel(levelName);
                limits[*quantity][level] = parseBoundsArray(*levelValue.as_array(), filePath, quantityName, levelName);
            }
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

    inline void limitExtractor(const std::string& configPath, Root& root) {
        root.limits.clear();
        loadLimitsFile("configs/General_Limits.toml", root.limits);

        toml::table mainConfig = toml::parse_file(configPath);
        const std::string limitsFileName = mainConfig["lambda"]["hist_limits"].value_or("Lambda_Limits");
        const std::string limitsFile = resolveLimitsPath(limitsFileName);
        root.histLimitsFile = limitsFile;
        loadLimitsFile(limitsFile, root.limits);
    }

    // Reads configs/Monitor.toml (silently skips if absent) and populates
    // the Log and Root structs with default monitoring values.
    inline void loadMonitorDefaults(Log& logging, Root& root) {
        const std::string monitorPath = "configs/Monitor.toml";
        if (!std::filesystem::exists(monitorPath)) return;
        try {
            toml::table mon = toml::parse_file(monitorPath);
            logging.printInterval  = static_cast<std::size_t>(mon["monitor"]["print_interval"].value_or(100));
            logging.checkInterval  = static_cast<std::size_t>(mon["monitor"]["check_interval"].value_or(10000));
            std::size_t hb = static_cast<std::size_t>(mon["monitor"]["heartbeat_interval"].value_or(1000));
            logging.heartbeat_interval = uSeconds(hb);
            double tr = mon["monitor"]["terminal_refresh_interval"].value_or(2.0);
            logging.terminal_refresh_interval = Seconds(static_cast<int>(60 * tr));
            double ps = mon["monitor"]["program_stall_threshold"].value_or(5.0);
            logging.program_stall_threshold = Seconds(static_cast<int>(60 * ps));
            root.binCount  = mon["monitor"]["bin_count"].value_or(100);
            root.histScale = mon["monitor"]["hist_scaling"].value_or(1.0);
        } catch (...) {}
    }

   inline void extractConfiguration(const std::string& configPath,
                                 const std::string& project,
                                 Log& logging,
                                 Root& root)
    {
        // Load Monitor.toml defaults first; per-config [log] section overrides below.
        loadMonitorDefaults(logging, root);

        limitExtractor(configPath, root);
        toml::table config = toml::parse_file(configPath);

        std::size_t temp = 0;
        double tempDouble = 0.0;

        // [record] section (new); fall back to [run] for backward compat.
        const bool hasRecord = config.contains("record");
        logging.serial    = hasRecord ? config["record"]["serial"].value_or(0)
                                      : config["run"]["serial"].value_or(0);
        logging.srPadding = static_cast<std::size_t>(
            hasRecord ? config["record"]["sr_padding"].value_or(2)
                      : config["run"]["sr_Padding"].value_or(2));

        // [events] section (new); fall back to [run] for backward compat.
        const bool hasEvents = config.contains("events");
        logging.nEvents  = static_cast<std::size_t>(
            hasEvents ? config["events"]["event_count"].value_or(1000)
                      : config["run"]["event_count"].value_or(1000));
        logging.nThreads = static_cast<std::size_t>(
            hasEvents ? config["events"]["nThreads"].value_or(0)
                      : config["run"]["nThreads"].value_or(0));

        // [log] section (new); fall back to [logging] for backward compat.
        // These override whatever loadMonitorDefaults() set.
        const bool hasLog     = config.contains("log");
        const bool hasLogging = config.contains("logging");
        const std::string logKey = hasLog ? "log" : (hasLogging ? "logging" : "");

        if (!logKey.empty()) {
            logging.printInterval = static_cast<std::size_t>(
                config[logKey]["print_interval"].value_or(
                    static_cast<int64_t>(logging.printInterval)));
            logging.checkInterval = static_cast<std::size_t>(
                config[logKey]["check_interval"].value_or(
                    static_cast<int64_t>(logging.checkInterval)));

            temp = static_cast<std::size_t>(
                config[logKey]["heartbeat_interval"].value_or(
                    static_cast<int64_t>(logging.heartbeat_interval.count())));
            logging.heartbeat_interval = uSeconds(temp);

            tempDouble = config[logKey]["terminal_refresh_interval"].value_or(
                static_cast<double>(logging.terminal_refresh_interval.count()) / 60.0);
            logging.terminal_refresh_interval = Seconds(static_cast<int>(60 * tempDouble));

            tempDouble = config[logKey]["program_stall_threshold"].value_or(
                static_cast<double>(logging.program_stall_threshold.count()) / 60.0);
            logging.program_stall_threshold = Seconds(static_cast<int>(60 * tempDouble));

            root.binCount  = config[logKey]["bin_count"].value_or(root.binCount);
            root.histScale = config[logKey]["hist_scaling"].value_or(root.histScale);
        }

        logging.nDigits = std::to_string(logging.nEvents).size();

        sanitiseLoggingConfig(logging);

        const bool logSubDir    = config["paths"]["logInSubDir"].value_or(true);
        const bool checkSubDir  = config["paths"]["checkpointsInSubDir"].value_or(true);
        const bool serialSubDir = config["paths"]["serialDirectory"].value_or(true);

        std::string baseRootDir = config["paths"]["directory"]
                                    .value_or("output/" + project + "/");

        std::string logBasePath   = config["paths"]["output_log_directory"].value_or("params/");
        std::string checkBasePath = config["paths"]["checkpoint_directory"].value_or("checkpoints/");

        std::string serialStr = Form(("_%0" + std::to_string((int)logging.srPadding) + "d").c_str(),
                                    logging.serial);

        std::string rootDir = (serialSubDir)
                                ? (baseRootDir + serialStr + "/")
                                : baseRootDir;

        root.rootDirectory       = rootDir;
        root.logDirectory        = (logSubDir)   ? rootDir + logBasePath   : logBasePath;
        root.checkpointDirectory = (checkSubDir) ? rootDir + checkBasePath : checkBasePath;

        const std::string filePrefix = config["file"]["prefix"].value_or("Unspecified");
        const bool fileSerial = config["file"]["serial"].value_or(true);
        const bool fileEnergy = config["file"]["energy"].value_or(true);
        const bool fileEvents = config["file"]["events"].value_or(true);

        std::string fileTitle = filePrefix;

        if (fileSerial)
            fileTitle += serialStr;

        if (fileEnergy)
            fileTitle += "_" + std::string(root.beamEnergy.Data()) + "GeV";

        if (fileEvents)
            fileTitle += "_" + numberString(logging.nEvents);

        std::string threadDir =
            std::string("threads_") +
            (fileEnergy ? ("_" + std::string(root.beamEnergy.Data()) + "GeV") : "") +
            (fileEvents ? ("_" + numberString(logging.nEvents)) : "");

        root.fileTitle = fileTitle;

        root.outName            = Form("%s%s.root", root.rootDirectory.Data(), fileTitle.c_str());
        root.logName            = Form("%s%s.log", root.logDirectory.Data(), fileTitle.c_str());
        root.runStatName        = Form("%s%s_runstat.log", root.logDirectory.Data(), fileTitle.c_str());
        root.threadStatDirectory= Form("%s%s/", root.logDirectory.Data(), threadDir.c_str());

        root.checkpointOutName  = Form("%s%s_checkpoint.root", root.checkpointDirectory.Data(), fileTitle.c_str());
        root.checkpointLogName  = Form("%s%s_checkpoint.log", root.checkpointDirectory.Data(), fileTitle.c_str());

        auto makeDir = [](const TString& file) {
            std::filesystem::create_directories( std::filesystem::path(file.Data()).parent_path() );
        };

        for (const TString* path : {&root.outName, &root.logName, &root.runStatName,
                                     &root.checkpointOutName, &root.checkpointLogName})
            makeDir(*path);

        std::filesystem::create_directories(root.threadStatDirectory.Data());
    }

    inline void openOutputFile(Root& root) {
        if (root.outFile != nullptr) {
            root.outFile->Close();
            delete root.outFile;
            root.outFile = nullptr;
        }

        root.outFile = new TFile(root.outName, "RECREATE");
        if (root.outFile == nullptr || root.outFile->IsZombie()) {
            throw std::runtime_error("Failed to create ROOT output file: " + std::string(root.outName.Data()));
        }
    }
}
