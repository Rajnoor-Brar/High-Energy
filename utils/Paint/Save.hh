#pragma once

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <stdexcept>
#include <string>

#include "TCanvas.h"
#include "TImage.h"

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

        inline void savePng(TCanvas& canvas,
                            const RenderResult& result,
                            const std::filesystem::path& path) {
            TImage* image = TImage::Create();
            if (image == nullptr) {
                throw std::runtime_error("Paint: TImage::Create() failed for " + path.string());
            }

            const int width = std::max(1, result.style.canvas.width * result.imageScale);
            const int height = std::max(1, result.style.canvas.height * result.imageScale);
            image->FromPad(&canvas, 0, 0, width, height);
            image->WriteImage(path.string().c_str());
            delete image;
        }

    } // namespace detail

    inline void saveCanvas(TCanvas& canvas, const RenderResult& result) {
        for (const std::string& rawFormat : result.formats) {
            const std::string format = detail::lowerCopy(rawFormat);
            const std::filesystem::path path = detail::outputPathFor(result, format);
            detail::ensureWritable(path, result.overwrite);

            if (format == "png") {
                detail::savePng(canvas, result, path);
            } else if (format == "pdf" || format == "svg" || format == "root") {
                canvas.Print(path.string().c_str());
            } else {
                throw std::runtime_error("Paint result '" + result.name + "': unsupported output format '" + rawFormat + "'");
            }
        }
    }

} // namespace Paint
