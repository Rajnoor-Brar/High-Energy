#pragma once

// ── Utility/Paths.hh ──────────────────────────────────────────────────────────
// Project-root anchored path resolution.
//
// Several defaults ("configs/defaults/Limits.toml", "configs/defaults/Paint.toml")
// were previously resolved relative to the current working directory, silently
// skipping the file when a binary ran from anywhere but the repo root (batch
// systems, Python wrappers, IDE debuggers). resolveProjectPath anchors them:
//
//   1. $HIGH_ENERGY_ROOT, when set, is the project root.
//   2. Otherwise walk up from the CWD looking for a "configs" directory.
//   3. Otherwise fall back to the path unchanged (CWD-relative, old behavior).
// ─────────────────────────────────────────────────────────────────────────────

#include <cstdlib>
#include <filesystem>
#include <string>

namespace Utility::Paths {

    namespace fs = std::filesystem;

    // projectRoot — resolved once per process, empty when undetermined.
    inline const fs::path& projectRoot() {
        static const fs::path root = []() -> fs::path {
            if (const char* env = std::getenv("HIGH_ENERGY_ROOT")) {
                const fs::path p(env);
                if (fs::is_directory(p)) return p;
            }
            std::error_code ec;
            fs::path dir = fs::current_path(ec);
            for (int depth = 0; !ec && !dir.empty() && depth < 12; ++depth) {
                if (fs::is_directory(dir / "configs")) return dir;
                const fs::path parent = dir.parent_path();
                if (parent == dir) break;
                dir = parent;
            }
            return {};
        }();
        return root;
    }

    // resolveProjectPath — anchor a repo-relative path ("configs/...") to the
    // project root. Absolute paths and paths that already exist relative to
    // the CWD are returned unchanged.
    inline std::string resolveProjectPath(const std::string& path) {
        const fs::path p(path);
        if (p.is_absolute() || fs::exists(p)) return path;
        const fs::path& root = projectRoot();
        if (root.empty()) return path;
        const fs::path anchored = root / p;
        return fs::exists(anchored) ? anchored.string() : path;
    }

} // namespace Utility::Paths
