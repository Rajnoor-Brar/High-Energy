#pragma once

#include <algorithm>
#include <string>
#include <unordered_map>

#include "TColor.h"
#include "Paint/Types.hh"

namespace Paint {

    inline Color_t parseColor(const std::string& spec) {
        static const std::unordered_map<std::string, Color_t> kNamedColors = {
            {"kWhite",   kWhite},   {"kBlack",   kBlack},   {"kGray",    kGray},
            {"kRed",     kRed},     {"kGreen",   kGreen},   {"kBlue",    kBlue},
            {"kYellow",  kYellow},  {"kMagenta", kMagenta}, {"kCyan",    kCyan},
            {"kOrange",  kOrange},  {"kSpring",  kSpring},  {"kTeal",    kTeal},
            {"kAzure",   kAzure},   {"kViolet",  kViolet},  {"kPink",    kPink},
        };

        std::string s = spec;
        s.erase(std::remove_if(s.begin(), s.end(), ::isspace), s.end());
        if (s.empty()) return kBlack;

        if (s[0] != 'k') {
            try { return static_cast<Color_t>(std::stoi(s)); }
            catch (...) { return kBlack; }
        }

        const std::size_t opPos = s.find_first_of("+-", 1);
        const std::string base  = (opPos == std::string::npos) ? s : s.substr(0, opPos);
        const int offset        = (opPos == std::string::npos) ? 0 : std::stoi(s.substr(opPos));

        const auto it = kNamedColors.find(base);
        if (it == kNamedColors.end()) return kBlack;
        return static_cast<Color_t>(it->second + offset);
    }
}
