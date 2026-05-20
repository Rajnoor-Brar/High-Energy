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

    inline void limitExtractor(const std::string& configPath, Register& root) { // to be renamed defaultLimits()
        root.particleLimits.clear();
        root.eventLimits.clear();

        // Pass 1: global defaults file (optional — silently skipped if absent).
        // Provides fallback bounds for all properties without requiring every
        // project to ship its own defaults block.
        const std::string defaultLimitsPath = "configs/defaults/Limits.toml";
        if (fs::exists(defaultLimitsPath)) {
            loadLimitsFile(defaultLimitsPath, root.particleLimits, root.eventLimits);
        }

        // Pass 2: project-specific limits (required — throws if absent).
        // Keys present here override the defaults loaded in Pass 1.
        TomlTable mainConfig = toml::parse_file(configPath);
        const std::string limitsFileName = mainConfig["lambda"]["hist_limits"].value_or("Lambda_Limits");
        const std::string limitsFile = resolveLimitsPath(limitsFileName);
        root.histLimitsFile = limitsFile;
        loadLimitsFile(limitsFile, root.particleLimits, root.eventLimits);
    }

}
