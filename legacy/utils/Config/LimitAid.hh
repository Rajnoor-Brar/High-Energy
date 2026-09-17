#pragma once

#include <iostream>
#include <string>
#include <stdexcept>

#include "Utility/Paths.hh"

namespace Config{
    inline std::string resolveLimitsPath(const std::string& limitsName) {
        if (limitsName.empty()) {
            throw std::runtime_error("Histogram limits file name must not be empty");
        }

        std::string resolved;
        if (limitsName.find('/') != std::string::npos)
            resolved = limitsName;
        else if (limitsName.size() >= 5 && limitsName.substr(limitsName.size() - 5) == ".toml")
            resolved = "configs/" + limitsName;
        else
            resolved = "configs/" + limitsName + ".toml";

        // Anchor to the project root so binaries launched outside the repo
        // root still find the limits file.
        resolved = Utility::Paths::resolveProjectPath(resolved);

        std::clog << "[Config] histogram limits file: " << resolved << '\n';
        return resolved;
    }
}