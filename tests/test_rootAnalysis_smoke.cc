// Integration smoke test: Lambda::rootAnalysis via Probe::runParallel
//
// Opens tests/fixtures/lambda_fixture.root (50 events, 4 protons + 5 pions
// per event), runs Lambda::rootAnalysis on 4 threads, and asserts:
//
//  S1  All 50 events were dispatched (iEvent == 50).
//  S2  All 50 events were counted as real (nRealEvents == 50).
//  S3  Unvalidated histogram has non-zero entries (proton+pion pairs filled).
//  S4  Validated histogram has non-zero entries (some signal pairs survived).
//  S5  Unvalidated entries exceed Validated entries (mass cut rejected noise).
//
// Build prerequisites:
//   make tests/fixtures/make_lambda_fixture.exe
//   tests/fixtures/make_lambda_fixture.exe        # writes lambda_fixture.root
//   make tests/test_rootAnalysis_smoke.exe
//
// The fixture must be present before running; the Makefile `test` target
// ensures the generator is built, but the generator must be run manually once:
//   tests/fixtures/make_lambda_fixture.exe

#include <chrono>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <string>

#include "test_assert.hh"

#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"
#include "Probe.hh"
#include "Record.hh"

namespace {
    constexpr int    kNEvents   = 50;
    constexpr int    kNThreads  = 4;
    const std::string kFixtureToml = "tests/fixtures/lambda_fixture.toml";
    const std::string kFixtureRoot = "tests/fixtures/lambda_fixture.root";
}

int main() {
    std::cout << "── test_rootAnalysis_smoke ─────────────────────────────────\n";

    // ── Guard: fixture ROOT file must exist ───────────────────────────────────
    {
        std::unique_ptr<TFile> probe(TFile::Open(kFixtureRoot.c_str(), "READ"));
        if (!probe || probe->IsZombie()) {
            std::cerr << "Fixture not found: " << kFixtureRoot << '\n'
                      << "Run: tests/fixtures/make_lambda_fixture.exe\n";
            return 77;  // conventional "skip" exit code
        }
    }

    // ── Configure ─────────────────────────────────────────────────────────────
    Config::Root rootParams;
    Config::Log  logParams;
    Config::extractConfiguration(kFixtureToml, "fixture_smoke", logParams, rootParams);
    rootParams.beamEnergy = "0";

    Config::openOutputFile(rootParams);

    Lambda::Parameters physParams;
    Lambda::extractPhysics(kFixtureToml, physParams, rootParams);

    Lambda::RootArray histogramSets;
    Lambda::declareObjects(histogramSets, physParams, rootParams);

    Monitor::AsyncLogger asyncLogger;
    Record::FinalizerController finalizer(
        histogramSets, rootParams, logParams, asyncLogger,
        [&physParams]() { return Lambda::logString(physParams); }
    );

    logParams.start = std::chrono::system_clock::now();
    asyncLogger.start(rootParams, logParams);

    // ── Run parallel reconstruction ───────────────────────────────────────────
    Lambda::AnalysisContext ctx{histogramSets, physParams, logParams, asyncLogger};
    std::mutex histMutex;
    Probe::runParallel(
        kFixtureRoot,
        Lambda::inputSchema(physParams),
        [&](const Probe::Event& ev, int threadId) {
            Lambda::rootAnalysis(ev, threadId, histMutex, ctx);
        },
        kNThreads,
        static_cast<std::size_t>(kNEvents)
    );

    // ── S1/S2: counters checked before ROOT file close ───────────────────────
    // normalShutdown() calls outFile->Close() which invalidates all histogram
    // pointers. Read everything we need BEFORE the shutdown.
    TEST_EQ(logParams.iEvent.load(), std::size_t(kNEvents));
    TEST_PASS("S1  iEvent == 50 (all events dispatched)");

    TEST_EQ(logParams.nRealEvents, std::size_t(kNEvents));
    TEST_PASS("S2  nRealEvents == 50");

    // ── S3/S4/S5: histogram sanity ────────────────────────────────────────────
    // findObjects uses the enum index → RootArray ordering established by
    // declareObjects; same ordering as kHistogramSetMap.
    const Lambda::RootObjects* unval =
        Lambda::findObjects(histogramSets, Lambda::HistogramSet::Unvalidated);
    const Lambda::RootObjects* val =
        Lambda::findObjects(histogramSets, Lambda::HistogramSet::Validated);

    TEST_TRUE(unval != nullptr);
    TEST_TRUE(val   != nullptr);
    TEST_TRUE(!unval->hists1D.empty());
    TEST_TRUE(!val->hists1D.empty());

    // Snapshot entry counts before normalShutdown() closes the file.
    const double unvalEntries = unval->hists1D[0].hist->GetEntries();
    const double valEntries   = val  ->hists1D[0].hist->GetEntries();

    // S3: unvalidated got filled (50 events × 4p × 5pi = 1000 combinations)
    TEST_LT(0.0, unvalEntries);
    TEST_PASS("S3  Unvalidated mass histogram has entries");

    // S4: validated got filled (50 events × 1 signal pair = 50 entries)
    TEST_LT(0.0, valEntries);
    TEST_PASS("S4  Validated mass histogram has entries");

    // S5: unvalidated > validated (mass cut rejects background)
    TEST_LT(valEntries, unvalEntries);
    TEST_PASS("S5  Unvalidated entries > Validated entries (cuts working)");

    std::cout << "  (unvalidated=" << unvalEntries
              << ", validated=" << valEntries << ")\n";

    finalizer.normalShutdown();

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
