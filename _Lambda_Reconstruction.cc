#include <chrono>
#include <mutex>
#include <string>

#include <toml++/toml.hpp>

#include "Probe.hh"
#include "Record.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"

int main(int argc, char* argv[]) {
    Monitor::disable_input_echo();
    std::atexit(Monitor::restore_terminal);

    const std::string project    = "Lambda_Reconstruction";
    const std::string configPath = argc > 1 ? argv[1] : "configs/" + project + ".toml";

    Config::Root rootParams;
    Config::Log  logParams;
    Config::extractConfiguration(configPath, project, logParams, rootParams);

    // inputPath is populated by readInputSection inside extractConfiguration.
    const std::string inputPath = rootParams.inputPath;
    if (inputPath.empty())
        throw std::runtime_error("Lambda_Reconstruction: [events].input_file not set in " + configPath);

    Config::openOutputFile(rootParams);

    Lambda::Parameters physParams;
    Lambda::extractPhysics(configPath, physParams, rootParams);

    Lambda::RootArray histogramSets;
    Lambda::declareObjects(histogramSets, physParams, rootParams);

    Monitor::AsyncLogger asyncLogger;

    Record::FinalizerController finalizer(
        histogramSets,
        rootParams,
        logParams,
        asyncLogger,
        [&physParams]() { return Lambda::logString(physParams); }
    );
    finalizer.installFatalStallHandler();

    // Three-tier event-count resolution (single TOML parse after extractConfiguration):
    //  1. [events].event_count  /  legacy [run].event_count  → explicit user setting
    //  2. About/events/n_events_total in the input ROOT file → Probe::resolveEventCount
    //  3. Full index-key scan via EventStream::nEvents()      → fallback
    //
    // readEventsSection stores 1000 as a default, so we must re-check the raw TOML
    // to distinguish "not specified" from "explicitly set to 1000".
    const std::size_t nEventsHint = [&]() -> std::size_t {
        const auto cfg = toml::parse_file(configPath);
        if (auto v = cfg["events"]["event_count"].value<int64_t>(); v && *v > 0)
            return static_cast<std::size_t>(*v);
        if (auto v = cfg["run"]["event_count"].value<int64_t>();    v && *v > 0)
            return static_cast<std::size_t>(*v);
        return Probe::resolveEventCount(inputPath);  // falls back to 0 on failure
    }();

    if (nEventsHint > 0) {
        logParams.nEvents = nEventsHint;
    } else {
        // Scan fallback — also exercises the (now index-only) keyRange path.
        logParams.nEvents = Probe::EventStream(inputPath, Lambda::inputSchema(physParams)).nEvents();
    }

    logParams.start = std::chrono::system_clock::now();
    asyncLogger.start(rootParams, logParams);

    Lambda::AnalysisContext ctx{histogramSets, physParams, logParams, asyncLogger};
    std::mutex histMutex;
    Probe::runParallel(inputPath,
        Lambda::inputSchema(physParams),
        [&](const Probe::Event& ev, int threadId) {
            Lambda::rootAnalysis(ev, threadId, histMutex, ctx);
        },
        Config::resolveThreadCount(logParams.nThreads), nEventsHint);

    {
        Meta::Record metaRec = Meta::capture("Lambda_Reconstruction", configPath, logParams, rootParams);
        metaRec.dataset.parent_files = {inputPath};
        finalizer.setMeta(std::move(metaRec));
    }
    finalizer.normalShutdown();

    return 0;
}
