#pragma once

// ── Core/Paths.hh ────────────────────────────────────────────────────────────
// Finding the repository from inside a process (idea from `legacy/utils/Utility/Paths.hh:25-54`).
//
// `hep-run` is handed absolute paths in its spec, so it rarely needs this; the tests and provenance do.
// Order: `HEKIT_ROOT` when it looks right, else walk up from the executable, else from the current
// directory. The same rule as `hekit.env.paths`, so both halves agree (00/B18).

#include <array>
#include <filesystem>
#include <string>

namespace Core::Paths {

    inline constexpr std::array<const char*, 3> markers{"docs/rework", "configs", "sources"};

    inline bool looksLikeRoot(const std::filesystem::path& path) {
        std::error_code error;
        for (const char* marker : markers)
            if (!std::filesystem::is_directory(path / marker, error)) return false;
        return true;
    }

    inline std::filesystem::path walkUp(std::filesystem::path start) {
        std::error_code error;
        start = std::filesystem::weakly_canonical(start, error);
        for (std::filesystem::path path = start; !path.empty(); path = path.parent_path()) {
            if (looksLikeRoot(path)) return path;
            if (!path.has_relative_path()) break;
        }
        return {};
    }

    // The repository root, or an empty path when it cannot be found (never an exception: provenance
    // must degrade, not fail).
    inline std::filesystem::path repoRoot(const std::string& executable = {}) {
        if (const char* declared = std::getenv("HEKIT_ROOT")) {
            const std::filesystem::path path{declared};
            if (looksLikeRoot(path)) return path;
        }
        if (!executable.empty()) {
            const std::filesystem::path found = walkUp(std::filesystem::path{executable}.parent_path());
            if (!found.empty()) return found;
        }
        std::error_code error;
        return walkUp(std::filesystem::current_path(error));
    }

}  // namespace Core::Paths
