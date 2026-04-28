#pragma once

#include <filesystem>
#include <stdexcept>
#include <string>

#include <toml++/toml.hpp>

#include "Types.hh"
#include "TypeAid.hh"
#include "LimitAid.hh"
#include "Physics/TypeAid.hh"

namespace Config {

    namespace fs = std::filesystem;
    using TomlTable = toml::table;
    using TomlArray = toml::array;

    inline Bounds parseBoundsArray(const TomlArray& boundsArray,
                                   const std::string& filePath,
                                   const std::string& quantityName,
                                   const std::string& levelName) {
        if (boundsArray.size() != 2) {
            throw std::runtime_error("Expected exactly 2 values for " + quantityName + "." + levelName + " in " + filePath);
        }

        const auto low  = boundsArray[0].value<Double_t>();
        const auto high = boundsArray[1].value<Double_t>();
        if (!low || !high) {
            throw std::runtime_error("Expected numeric bounds for " + quantityName + "." + levelName + " in " + filePath);
        }

        return {*low, *high};
    }

    inline void loadLimitsFile(const std::string& filePath,
                               ParticleLimits& particleLimits,
                               EventLimits&    eventLimits) {
        if (!fs::exists(filePath)) {
            throw std::runtime_error("Limits file does not exist: " + filePath);
        }

        TomlTable table = toml::parse_file(filePath);
        for (auto&& [quantityKey, quantityValue] : table) {
            if (!quantityValue.is_table()) continue;

            const std::string qname = std::string(quantityKey.str());
            TomlTable& quantityTable = *quantityValue.as_table();

            if (auto pp = Physics::tryStringToParticleProperty(qname)) {
                for (auto&& [levelKey, levelValue] : quantityTable) {
                    if (!levelValue.is_array()) continue;
                    const std::string levelName = std::string(levelKey.str());
                    particleLimits[*pp][stringToLevel(levelName)] =
                        parseBoundsArray(*levelValue.as_array(), filePath, qname, levelName);
                }
            } else if (auto ep = Physics::tryStringToEventProperty(qname)) {
                for (auto&& [levelKey, levelValue] : quantityTable) {
                    if (!levelValue.is_array()) continue;
                    const std::string levelName = std::string(levelKey.str());
                    eventLimits[*ep][stringToLevel(levelName)] =
                        parseBoundsArray(*levelValue.as_array(), filePath, qname, levelName);
                }
            }
            // else: unknown key — silently skip for forward-compatibility
        }
    }

    inline void limitExtractor(const std::string& configPath, Root& root) { // to be renamed defaultLimits()
        root.particleLimits.clear();
        root.eventLimits.clear();
        loadLimitsFile("configs/General_Limits.toml", root.particleLimits, root.eventLimits);

        TomlTable mainConfig = toml::parse_file(configPath);
        const std::string limitsFileName = mainConfig["lambda"]["hist_limits"].value_or("Lambda_Limits");
        const std::string limitsFile = resolveLimitsPath(limitsFileName);
        root.histLimitsFile = limitsFile;
        loadLimitsFile(limitsFile, root.particleLimits, root.eventLimits);
    }

    // Reads configs/Monitor.toml (silently skips if absent) and populates
    // the Log and Root structs with default monitoring values.
    inline void loadMonitorDefaults(Log& logging, Root& root) {
        const std::string monitorPath = "configs/Monitor.toml";
        if (!fs::exists(monitorPath)) return;
        try {
            TomlTable mon = toml::parse_file(monitorPath);
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
}
