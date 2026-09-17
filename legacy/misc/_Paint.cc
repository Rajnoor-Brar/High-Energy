#include <exception>
#include <iostream>
#include <string>

#include "Paint.hh"

namespace {
    void usage(const char* argv0) {
        std::cerr << "Usage: " << argv0 << " [config.toml] [--dry-run]\n";
    }
}

int main(int argc, char** argv) {
    std::string configPath = "configs/Paint.toml";
    bool dryRun = false;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--dry-run") {
            dryRun = true;
        } else if (!arg.empty() && arg[0] == '-') {
            usage(argv[0]);
            return 2;
        } else {
            configPath = arg;
        }
    }

    try {
        Paint::Illustrator illustrator(configPath);
        illustrator.load();
        illustrator.resolve();

        if (dryRun) {
            illustrator.dryRun(std::cout);
        } else {
            illustrator.render();
        }
    } catch (const std::exception& ex) {
        std::cerr << "Paint error: " << ex.what() << '\n';
        return 1;
    }

    return 0;
}
