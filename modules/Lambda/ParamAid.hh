#pragma once

#include <algorithm>
#include "Types.hh"

namespace Lambda{
inline string defaultTreeName(string label) {
        if (!label.empty()) {
            label[0] = static_cast<char>(std::toupper( static_cast<unsigned char>(label[0])));
        }
        return label;
    }

    inline string resolveTreeName(const InputConfig& input,
                                       const CandidateConfig& candidate) {
        auto it = input.treeNames.find(candidate.label);
        if (it != input.treeNames.end()) return it->second;
        return defaultTreeName(candidate.label);
    }

    inline string labelForPidAbs(const Parameters& parameters,
                                      int pidAbs,
                                      string fallback) {
        const auto matchesPid = [pidAbs](const CandidateConfig& candidate) {
            return std::abs(candidate.pidAbs) == pidAbs;
        };

        const auto enabledIt = std::find_if(
            parameters.candidates.begin(), parameters.candidates.end(),
            [&](const CandidateConfig& candidate) {
                return candidate.enabled && matchesPid(candidate);
            });
        if (enabledIt != parameters.candidates.end()) return enabledIt->label;

        const auto anyIt = std::find_if(
            parameters.candidates.begin(),
            parameters.candidates.end(),
            matchesPid);
        return anyIt != parameters.candidates.end() ? anyIt->label : fallback;
    }

    inline std::pair<string, string> resolveCandidateLabels( const Parameters& parameters) {
        return {
            labelForPidAbs(parameters, std::abs(ProtonPid), "Protons"),
            labelForPidAbs(parameters, std::abs(PionPid), "Pions")
        };
    }
}