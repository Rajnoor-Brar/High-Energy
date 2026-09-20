#pragma once

// ── Module/Registry.hh ───────────────────────────────────────────────────────
// How a module announces itself (05 §5).
//
// `HEKIT_MODULE("name", Class)` at the bottom of a module's `.cc` is all a user writes. It defines
// one `extern "C"` factory, which is the only symbol `Module/Loader.hh` looks for — and `extern "C"`
// matters: a C++ symbol's name depends on the compiler that produced it, so a mangled entry point
// would tie a module's build to `hep-run`'s. This is the same arrangement Rivet plugins use, for the
// same reason.
//
// The registry inside `hep-run` is what a *built-in* module would use; the dlopen'd ones do not need
// it, and it exists so a test can register a module without a shared library.

#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "Module/Types.hh"

namespace Module {

    using Factory = std::function<std::unique_ptr<Base>()>;

    /// Modules compiled into this binary (tests, mostly). A dlopen'd one never touches this.
    inline std::map<std::string, Factory>& registry() {
        static std::map<std::string, Factory> known;
        return known;
    }

    inline void add(const std::string& name, Factory factory) {
        registry()[name] = std::move(factory);
    }

    inline std::vector<std::string> names() {
        std::vector<std::string> found;
        for (const auto& [name, _] : registry()) found.push_back(name);
        return found;
    }

}  // namespace Module

/// The entry point a loaded module exposes, and the one `Module::Loader` asks for by name.
#define HEKIT_MODULE_ENTRY "hekit_module_create"

/// Put this at the bottom of a module's `.cc`:  `HEKIT_MODULE("mymodule", MyModule);`
#define HEKIT_MODULE(NAME, CLASS)                                                     \
    extern "C" ::Module::Base* hekit_module_create() { return new CLASS(); }           \
    extern "C" const char* hekit_module_name() { return NAME; }                        \
    namespace {                                                                        \
        struct CLASS##Registrar {                                                      \
            CLASS##Registrar() {                                                       \
                ::Module::add(NAME, [] { return std::unique_ptr<::Module::Base>(       \
                                                 new CLASS()); });                     \
            }                                                                          \
        };                                                                             \
        const CLASS##Registrar CLASS##_registrar;                                      \
    }
