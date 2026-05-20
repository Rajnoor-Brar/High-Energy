#pragma once

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <set>
#include <stdexcept>
#include <string>

#include "TCanvas.h"

#include "Paint/Types.hh"

namespace Paint {

    namespace detail {

        inline std::string lowerCopy(std::string value) {
            std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
                return static_cast<char>(std::tolower(ch));
            });
            return value;
        }

        inline std::filesystem::path outputPathFor(const RenderResult& result,
                                                   const std::string& format) {
            std::filesystem::path path = std::filesystem::path(result.resultDir) / result.outputName;
            path.replace_extension("." + lowerCopy(format));
            return path;
        }

        inline void ensureWritable(const std::filesystem::path& path, bool overwrite) {
            std::filesystem::create_directories(path.parent_path());
            if (!overwrite && std::filesystem::exists(path)) {
                throw std::runtime_error("Paint output exists and overwrite=false: " + path.string());
            }
        }

        // Formats routed directly through TCanvas::Print.
        inline bool isSupportedFormat(const std::string& lower) {
            static const std::set<std::string> kSupported = {"png", "pdf", "svg", "root", "eps", "gif"};
            return kSupported.count(lower) != 0;
        }

    } // namespace detail

    inline void saveCanvas(TCanvas& canvas, const RenderResult& result) {
        for (const std::string& rawFormat : result.formats) {
            const std::string format = detail::lowerCopy(rawFormat);
            const std::filesystem::path path = detail::outputPathFor(result, format);
            detail::ensureWritable(path, result.overwrite);

            if (!detail::isSupportedFormat(format)) {
                throw std::runtime_error("Paint result '" + result.name
                    + "': unsupported output format '" + rawFormat + "'");
            }

            canvas.Print(path.string().c_str());
        }
    }

} // namespace Paint
