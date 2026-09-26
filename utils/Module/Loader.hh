#pragma once

// ── Module/Loader.hh ─────────────────────────────────────────────────────────
// Finding and opening a user's module (05 §5).
//
// `dlopen` from the configured paths, exactly as Rivet finds its analysis plugins, so that adding a
// module never rebuilds `hep-run`. Two things it is careful about, both learned from the Rivet analyzer:
//
//   * **a module that is not there fails before the first event.** The library is opened and its
//     entry point resolved in `prepare()`, which is where `--check` stops (06 §3.3) — a typo costs a
//     second rather than a whole generation;
//   * **the handle is never closed.** The module's objects outlive the loader (its vtable lives in
//     that library), and `dlclose`ing it while anything still points into it is a crash with a
//     stack trace that names nobody. A process that is exiting anyway loses nothing by keeping it.

#include <dlfcn.h>

#include <filesystem>
#include <memory>
#include <string>
#include <vector>

#include "Core/Errors.hh"
#include "Module/Registry.hh"

namespace Module {

    /// `libhekit_<name>.so`, which is what the CMake target for a module produces.
    inline std::string libraryName(const std::string& name) {
        return "libhekit_" + name + ".so";
    }

    /// Where a module of this name could be, in the order they are tried.
    inline std::vector<std::string> candidates(const std::string& name,
                                               const std::vector<std::string>& paths) {
        std::vector<std::string> found;
        for (const std::string& directory : paths)
            found.push_back((std::filesystem::path(directory) / libraryName(name)).string());
        found.push_back(libraryName(name));          // then wherever the loader would look anyway
        return found;
    }

    /// Open `name` and build one. Throws with everywhere it looked when it cannot.
    inline std::unique_ptr<Base> load(const std::string& name,
                                      const std::vector<std::string>& paths) {
        // A module compiled into this binary wins: that is how a test registers one without
        // building a shared library at all.
        const auto built_in = registry().find(name);
        if (built_in != registry().end()) return built_in->second();

        std::string tried;
        for (const std::string& path : candidates(name, paths)) {
            void* handle = ::dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
            if (handle == nullptr) {
                tried += (tried.empty() ? "" : "\n  ") + path;
                continue;
            }
            // Deliberately never `dlclose`d: the objects this creates carry a vtable that lives in
            // this library, and unloading it underneath them is a crash that names nobody.
            using Create = Base* (*)();
            const auto create = reinterpret_cast<Create>(::dlsym(handle, HEKIT_MODULE_ENTRY));
            if (create == nullptr)
                throw Core::Error{Core::Exit::Config,
                                  path + " has no " + HEKIT_MODULE_ENTRY,
                                  "the module needs HEKIT_MODULE(\"" + name + "\", YourClass) at "
                                  "the bottom of its .cc"};
            std::unique_ptr<Base> made(create());
            if (made == nullptr)
                throw Core::Error{Core::Exit::Config, path + " built no module"};
            return made;
        }
        throw Core::Error{Core::Exit::Config, "no module called '" + name + "'",
                          "looked for " + libraryName(name) + " in:\n  " + tried +
                              "\n`hep build --modules <project>` builds them"};
    }

}  // namespace Module
