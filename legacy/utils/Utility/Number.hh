#pragma once

#include <array>
#include <cstddef>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

namespace Utility {

    inline std::string numberFormat(std::size_t number, std::size_t padding) {
        std::ostringstream stream;
        std::vector<std::size_t> groups;

        if (number == 0) {
            stream << '0';
            const std::string result = stream.str();
            return result.size() < padding ? std::string(padding - result.size(), ' ') + result : result;
        }

        while (number > 0) {
            groups.push_back(number % 1000);
            number /= 1000;
        }

        for (std::size_t i = groups.size(); i > 0; --i) {
            if (i == groups.size()) stream << groups[i - 1];
            else stream << ',' << std::setw(3) << std::setfill('0') << groups[i - 1];
        }

        const std::string result = stream.str();
        return result.size() < padding ? std::string(padding - result.size(), ' ') + result : result;
    }

    inline std::string numberString(std::size_t value) {
        static constexpr std::array<const char*, 7> suffix = {"", "k", "M", "B", "T", "P", "E"};
        if (value == 0) return "0";
        std::stringstream ss;
        std::string result;
        std::size_t group = 0;
        while (value > 0) {
            std::size_t chunk = value % 1000;
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
}
