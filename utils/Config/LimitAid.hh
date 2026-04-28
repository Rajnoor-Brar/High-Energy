#pragma once

#include <string>
#include <stdexcept>

namespace Config{
    inline std::string resolveLimitsPath(const std::string& limitsName) {
        if (limitsName.empty()) {
            throw std::runtime_error("Histogram limits file name must not be empty");
        }

        if (limitsName.find('/') != std::string::npos) return limitsName;
        if (limitsName.size() >= 5 && limitsName.substr(limitsName.size() - 5) == ".toml") return "configs/" + limitsName;
        return "configs/" + limitsName + ".toml";
    }
}