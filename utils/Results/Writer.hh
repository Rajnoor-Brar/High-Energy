#pragma once

// ── Results/Writer.hh ────────────────────────────────────────────────────────
// Every file a run produces is written once, completely, under a temporary name, and then renamed into
// place (07 §1, D22; the pattern is adapted from `legacy/utils/Record/Recording.hh:204-231`).
//
// The defect this exists to prevent is 00/B3: the old pipeline opened the final path and wrote into it
// as the run went, so a killed run left a file that *looked* like a finished result — same name, same
// place, silently short. Here a reader only ever sees a complete file, and a stopped run is a
// **different name** (`analysis.partial.yoda`), so no plot can quietly use one for the other.
//
// Two details that are easy to get wrong and are handled here:
//
//   * **the temporary name keeps the extension.** `analysis.yoda.tmp` cannot be written at all — YODA
//     picks its format from the suffix and reports "format cannot be identified" (the same trap that
//     bit the legacy partial file in P0-S03). The temporary is `analysis.tmp.yoda`.
//   * **a run never leaves both names behind.** Writing the partial removes a stale complete file from
//     an earlier attempt in the same directory, and vice versa. Otherwise a rerun that stops early
//     would leave last week's `analysis.yoda` next to today's partial.

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "YODA/AnalysisObject.h"
#include "YODA/IO.h"

#include "Core/Errors.hh"

namespace Results {

    // `analysis.yoda` → `analysis.partial.yoda`: the marker goes *before* the suffix, so the file is
    // still a readable YODA (P0-S03).
    inline std::string marked(const std::string& name, const std::string& marker) {
        const std::size_t dot = name.rfind('.');
        if (dot == std::string::npos) return name + "." + marker;
        return name.substr(0, dot) + "." + marker + name.substr(dot);
    }

    class Writer {
      public:
        explicit Writer(std::string directory) : directory_(std::move(directory)) {
            std::error_code code;
            std::filesystem::create_directories(directory_, code);
            if (code)
                throw Core::Error{Core::Exit::Analyzer,
                                  "cannot create the output directory: " + directory_,
                                  code.message()};
        }

        const std::string& directory() const { return directory_; }

        std::string path(const std::string& name) const {
            return (std::filesystem::path(directory_) / name).string();
        }

        // The name a run's analysis file gets: a stopped run is never called `analysis.yoda` (07 §1).
        std::string resultName(const std::string& name, bool stopped) const {
            return stopped ? marked(name, "partial") : name;
        }

        // Write YODA objects and return the path they landed at.
        template <typename Objects>
        std::string writeYoda(const std::string& name, const Objects& objects, bool stopped) {
            const std::string chosen = resultName(name, stopped);
            const std::string temporary = path(marked(chosen, "tmp"));
            try {
                YODA::write(temporary, objects);
            } catch (const std::exception& error) {
                remove(temporary);
                throw Core::Error{Core::Exit::Analyzer,
                                  "cannot write " + chosen + ": " + error.what()};
            }
            return commit(temporary, chosen, other(name, stopped));
        }

        std::string writeText(const std::string& name, const std::string& text) {
            const std::string temporary = path(marked(name, "tmp"));
            {
                std::ofstream out(temporary, std::ios::binary | std::ios::trunc);
                if (!out)
                    throw Core::Error{Core::Exit::Analyzer, "cannot write " + temporary};
                out << text;
                if (!out)
                    throw Core::Error{Core::Exit::Analyzer, "cannot write " + temporary};
            }
            return commit(temporary, name, {});
        }

        static void remove(const std::string& target) {
            std::error_code code;
            std::filesystem::remove(target, code);        // best effort: a missing file is fine
        }

      private:
        // The name this write makes wrong, so it cannot be left lying around.
        std::string other(const std::string& name, bool stopped) const {
            return stopped ? name : marked(name, "partial");
        }

        std::string commit(const std::string& temporary, const std::string& name,
                           const std::string& stale) {
            const std::string target = path(name);
            std::error_code code;
            std::filesystem::rename(temporary, target, code);
            if (code) {
                remove(temporary);
                throw Core::Error{Core::Exit::Analyzer,
                                  "cannot move " + name + " into place", code.message()};
            }
            if (!stale.empty()) remove(path(stale));
            return target;
        }

        std::string directory_;
    };

}  // namespace Results
