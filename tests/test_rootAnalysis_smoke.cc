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
#include "TH1.h"

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
    Lambda::configure(physParams, writer, kFixtureToml);

    writer.bind(asyncLogger,
                [&physParams]() { return Lambda::logString(physParams); });

    asyncLogger.initialise(writer);
    writer.start();

    // ── Run parallel reconstruction ───────────────────────────────────────────
    Lambda::AnalysisContext ctx{physParams, asyncLogger.watch(), asyncLogger, writer};

    probe.run([&](const Probe::Event& ev, int threadId) {
        Lambda::rootAnalysis(ev, threadId, ctx);
    });

    // ── S1/S2: counters checked before final ROOT file inspection ────────────
    TEST_EQ(asyncLogger.watch().iEvent.load(), std::size_t(kNEvents));
    TEST_PASS("S1  iEvent == 50 (all events dispatched)");

    TEST_EQ(asyncLogger.watch().n_real_events.load(), std::size_t(kNEvents));
    TEST_PASS("S2  n_real_events == 50");

    const std::string outputPath = writer.paths().outName.Data();
    writer.finish(asyncLogger.watch().nEvents);

    std::unique_ptr<TFile> out(TFile::Open(outputPath.c_str(), "READ"));
    TEST_TRUE(out && !out->IsZombie());

    auto* unvalHist = dynamic_cast<TH1*>(out->Get("Unvalidated/Unvalidated_Mass_Invariant_Hist"));
    auto* valHist   = dynamic_cast<TH1*>(out->Get("Validated/Validated_Mass_Invariant_Hist"));
    TEST_TRUE(unvalHist != nullptr);
    TEST_TRUE(valHist   != nullptr);

    const double unvalEntries = unvalHist->GetEntries();
    const double valEntries   = valHist->GetEntries();

    TEST_LT(0.0, unvalEntries);
    TEST_PASS("S3  Unvalidated mass histogram has entries");

    TEST_LT(0.0, valEntries);
    TEST_PASS("S4  Validated mass histogram has entries");

    TEST_LT(valEntries, unvalEntries);
    TEST_PASS("S5  Unvalidated entries > Validated entries (cuts working)");

    std::cout << "  (unvalidated=" << unvalEntries
              << ", validated=" << valEntries << ")\n";

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
