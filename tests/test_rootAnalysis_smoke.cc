// Integration smoke test: Lambda::rootAnalysis via Probe::runParallel
//
// Opens tests/fixtures/lambda_fixture.root (50 events, 4 protons + 5 pions
// per event), runs Lambda::rootAnalysis on 4 threads, and asserts:
//
//  S1  All 50 events were dispatched (iEvent == 50).
//  S2  All 50 events were counted as real (n_real_events == 50).
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
#include <string>

#include "test_assert.hh"

#include "Config.hh"
#include "Record.hh"
#include "Lambda.hh"
#include "Monitor.hh"
#include "Probe.hh"
#include "Config/Configure.hh"

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
    Probe::ProbeParallel probe;
    Record::Writer       writer;
    Monitor::AsyncLogger asyncLogger;

    Config::configure(kFixtureToml, "fixture_smoke", probe, writer, asyncLogger);
    TEST_EQ(probe.threadCount(), static_cast<std::size_t>(kNThreads));

    Lambda::Parameters physParams;
    Lambda::RootArray  histogramSets;
    Lambda::configure(physParams, histogramSets, writer, kFixtureToml);

    writer.bind(asyncLogger, asyncLogger.watch(),
                [&physParams]() { return Lambda::logString(physParams); });

    asyncLogger.initialise(writer);

    // ── Run parallel reconstruction ───────────────────────────────────────────
    Lambda::AnalysisContext ctx{histogramSets, physParams, asyncLogger.watch(), asyncLogger, writer};

    probe.run([&](const Probe::Event& ev, int threadId) {
        Lambda::rootAnalysis(ev, threadId, ctx);
    });

    // ── S1/S2: counters checked before ROOT file close ───────────────────────
    // shutdown() calls outFile->Close() which invalidates histogram pointers.
    // Read everything we need BEFORE the shutdown.
    TEST_EQ(asyncLogger.watch().iEvent.load(), std::size_t(kNEvents));
    TEST_PASS("S1  iEvent == 50 (all events dispatched)");

    TEST_EQ(asyncLogger.watch().n_real_events.load(), std::size_t(kNEvents));
    TEST_PASS("S2  n_real_events == 50");

    // ── S3/S4/S5: histogram sanity ────────────────────────────────────────────
    const Lambda::RootObjects* unval =
        Lambda::findObjects(histogramSets, Lambda::HistogramSet::Unvalidated);
    const Lambda::RootObjects* val =
        Lambda::findObjects(histogramSets, Lambda::HistogramSet::Validated);

    TEST_TRUE(unval != nullptr);
    TEST_TRUE(val   != nullptr);
    TEST_TRUE(!unval->hists1D.empty());
    TEST_TRUE(!val->hists1D.empty());

    const double unvalEntries = unval->hists1D[0].hist->GetEntries();
    const double valEntries   = val  ->hists1D[0].hist->GetEntries();

    TEST_LT(0.0, unvalEntries);
    TEST_PASS("S3  Unvalidated mass histogram has entries");

    TEST_LT(0.0, valEntries);
    TEST_PASS("S4  Validated mass histogram has entries");

    TEST_LT(valEntries, unvalEntries);
    TEST_PASS("S5  Unvalidated entries > Validated entries (cuts working)");

    std::cout << "  (unvalidated=" << unvalEntries
              << ", validated=" << valEntries << ")\n";

    writer.shutdown(histogramSets);

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
