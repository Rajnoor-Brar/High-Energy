#include <chrono>
#include <cstdint>
#include <mutex>
#include <string>

#include <toml++/toml.hpp>

#include "Explore.hh"
#include "Record.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"

#include "TFile.h"
#include "TDirectory.h"
#include "TParameter.h"

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

    // Part 6a: resolve event count from metadata before falling back to a scan.
    // Three tiers: [events].event_count in the reconstruction TOML → legacy
    // [run].event_count → About/events/n_events_total in the input ROOT file →
    // full scan (existing behavior, preserved bit-for-bit).
    const std::size_t nEventsHint = [&]() -> std::size_t {
        try {
            const auto cfg = toml::parse_file(configPath);
            if (auto v = cfg["events"]["event_count"].value<int64_t>(); v && *v > 0)
                return static_cast<std::size_t>(*v);
            if (auto v = cfg["run"]["event_count"].value<int64_t>();    v && *v > 0)
                return static_cast<std::size_t>(*v);
        } catch (...) { /* fall through to ROOT metadata */ }

        std::unique_ptr<TFile> f(TFile::Open(inputPath.c_str(), "READ"));
        if (!f || f->IsZombie()) return 0;
        if (auto* dir = f->GetDirectory("About/events")) {
            if (auto* par = dynamic_cast<TParameter<Long64_t>*>(dir->Get("n_events_total")))
                if (par->GetVal() > 0) return static_cast<std::size_t>(par->GetVal());
        }
        return 0;
    }();

    if (nEventsHint > 0) {
        logParams.nEvents = nEventsHint;
    } else {
        // Scan fallback — also exercises the (now index-only) keyRange path.
        logParams.nEvents = Explore::EventStream(inputPath, Lambda::inputSchema(physParams)).nEvents();
    }

    logParams.start = std::chrono::system_clock::now();
    asyncLogger.start(rootParams, logParams);

    std::mutex histMutex;
    Explore::runParallel(inputPath,
        Lambda::inputSchema(physParams),
        [&](const Explore::Event& ev, int threadId) {
            Lambda::analyzeEvent(ev, threadId, histogramSets, physParams,
                                 logParams, asyncLogger, histMutex);
        },
        Config::resolveThreadCount(logParams.nThreads),
        nEventsHint);

    finalizer.normalShutdown();

    return 0;
}
