// Focused tests for Probe::ProbeParallel execution modes.

#include <algorithm>
#include <atomic>
#include <exception>
#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include <toml++/toml.hpp>

#include "test_assert.hh"

#include "Probe.hh"
#include "TFile.h"

namespace {
    constexpr int kNEvents = 50;
    const std::string kFixtureToml = "tests/fixtures/lambda_fixture.toml";
    const std::string kFixtureRoot = "tests/fixtures/lambda_fixture.root";

    std::vector<Probe::CollectionSpec> fixtureSpecs() {
        const toml::table config = toml::parse_file(kFixtureToml);
        return Probe::parseCollectionsFromToml(config);
    }

    bool fixtureAvailable() {
        std::unique_ptr<TFile> file(TFile::Open(kFixtureRoot.c_str(), "READ"));
        return file && !file->IsZombie();
    }
}

int main() {
    std::cout << "── test_probe_parallel ──────────────────────────────────────\n";

    if (!fixtureAvailable()) {
        std::cerr << "Fixture not found: " << kFixtureRoot << '\n'
                  << "Run: tests/fixtures/make_lambda_fixture.exe\n";
        return 77;
    }

    const auto specs = fixtureSpecs();

    {
        Probe::ProbeParallel probe;
        probe.setQueueCapacity(2);
        probe.configureProbe(kFixtureRoot, specs, 4, kNEvents, true);

        TEST_EQ(probe.eventCount(), static_cast<std::size_t>(kNEvents));
        TEST_EQ(probe.threadCount(), std::size_t(4));
        TEST_TRUE(probe.streamType() == Probe::StreamType::Events);

        std::vector<Long64_t> seen;
        probe.run([&](const Probe::Event& ev, int workerIndex) {
            TEST_TRUE(workerIndex >= 0);
            TEST_EQ(ev.n("protons"), std::size_t(4));
            TEST_EQ(ev.n("pions"),   std::size_t(5));
            seen.push_back(ev.index);
        });

        TEST_EQ(seen.size(), static_cast<std::size_t>(kNEvents));
        std::set<Long64_t> unique(seen.begin(), seen.end());
        TEST_EQ(unique.size(), static_cast<std::size_t>(kNEvents));
        TEST_EQ(*unique.begin(), Long64_t(1));
        TEST_EQ(*unique.rbegin(), Long64_t(kNEvents));
        TEST_TRUE(probe.stats().find("produced=50") != std::string::npos);
        TEST_TRUE(probe.stats().find("consumed=50") != std::string::npos);
        TEST_PASS("CollectorThread dispatches exactly one callback per event");
    }

    {
        Probe::ProbeParallel probe;
        probe.setCallbackMode(Probe::CallbackMode::WorkerThread);
        probe.configureProbe(kFixtureRoot, specs, 4, kNEvents, true);

        std::atomic<std::size_t> callbacks{0};
        probe.run([&](const Probe::Event& ev, int workerIndex) {
            TEST_TRUE(workerIndex >= 0);
            TEST_TRUE(ev.index >= 1 && ev.index <= kNEvents);
            callbacks.fetch_add(1, std::memory_order_relaxed);
        });
        TEST_EQ(callbacks.load(std::memory_order_relaxed), static_cast<std::size_t>(kNEvents));
        TEST_PASS("WorkerThread mode preserves direct worker callbacks");
    }

    {
        Probe::ProbeParallel probe;
        probe.configureProbe(kFixtureRoot, specs, 4, kNEvents, true);

        bool caught = false;
        try {
            probe.run([](const Probe::Event&, int) {
                throw std::runtime_error("collector callback failure");
            });
        } catch (const std::runtime_error&) {
            caught = true;
        }
        TEST_TRUE(caught);
        TEST_PASS("CollectorThread callback exceptions propagate");
    }

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
