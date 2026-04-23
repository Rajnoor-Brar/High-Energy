#include <chrono>
#include <mutex>
#include <string>

#include <toml++/toml.hpp>

#include "Explore.hh"
#include "Record.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"

namespace {
    // Minimal stand-in so FinalizerController (which templates on PythiaT)
    // can call stat() / settings.listChanged() without a real Pythia instance.
    struct NoPythia {
        void stat() const {}
        struct { void listChanged() const {} } settings;
    };
}

int main(int argc, char* argv[]) {
    Monitor::disable_input_echo();
    std::atexit(Monitor::restore_terminal);

    const std::string project    = "Lambda_Reconstruction";
    const std::string configPath = argc > 1 ? argv[1] : "configs/" + project + ".toml";

    Config::Root rootParams;
    Config::Log  logParams;
    Config::extractConfiguration(configPath, project, logParams, rootParams);

    const std::string inputPath = [&]{
        const auto cfg = toml::parse_file(configPath);
        return cfg["input"]["root_file"].value_or(std::string{});
    }();
    if (inputPath.empty())
        throw std::runtime_error("Lambda_Reconstruction: [input].root_file not set in " + configPath);

    Config::openOutputFile(rootParams);

    Lambda::Parameters physParams;
    Lambda::extractPhysics(configPath, physParams, rootParams);

    Lambda::RootArray histogramSets;
    Lambda::declareObjects(histogramSets, physParams, rootParams);

    Monitor::AsyncLogger asyncLogger;

    NoPythia dummy;
    Record::FinalizerController finalizer(
        dummy,
        histogramSets,
        rootParams,
        logParams,
        asyncLogger,
        [&physParams]() { return Lambda::logString(physParams); }
    );
    finalizer.installFatalStallHandler();

    // Scan the input file to know total event count before streaming starts.
    logParams.nEvents = Explore::EventStream(inputPath, Lambda::inputSchema(physParams)).nEvents();

    logParams.start = std::chrono::system_clock::now();
    asyncLogger.start(rootParams, logParams);

    std::mutex histMutex;
    Explore::runParallel(inputPath,
        Lambda::inputSchema(physParams),
        [&](const Explore::Event& ev, int threadId) {
            Lambda::analyzeEvent(ev, threadId, histogramSets, physParams,
                                 logParams, asyncLogger, histMutex);
        },
        Config::resolveThreadCount(logParams.nThreads));

    finalizer.normalShutdown();

    return 0;
}
