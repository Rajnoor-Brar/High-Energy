// Focused tests for Probe::ProbeParallel execution modes.

#include <algorithm>
#include <atomic>
#include <exception>
#include <filesystem>
#include <iostream>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include <toml++/toml.hpp>

#include "test_assert.hh"

#include "Probe.hh"
#include "TFile.h"

namespace fs = std::filesystem;

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

        // CollectorThread now spawns analysis_threads collectors (defaults
        // to thread_count).  User callbacks under multi-collector must be
        // thread-safe; this test protects `seen` with a mutex.
        std::vector<Long64_t> seen;
        std::mutex            seenMutex;
        probe.run([&](const Probe::Event& ev, int workerIndex) {
            TEST_TRUE(workerIndex >= 0);
            TEST_EQ(ev.n("protons"), std::size_t(4));
            TEST_EQ(ev.n("pions"),   std::size_t(5));
            std::lock_guard<std::mutex> lock(seenMutex);
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

    {
        // [probe.index] parsing — verify sorted/ascending/monotonic fields are
        // applied element-wise to CollectionSpec from a TOML table.
        const std::string src = R"toml(
[probe]
event_particles = [
    ["protons", 0, "Protons", [["pX","D"],["pY","D"],["pZ","D"],["E","D"]], [["idx","I"]]],
    ["pions",   0, "Pions",   [["pX","D"],["pY","D"],["pZ","D"],["E","D"]], [["idx","I"]]]
]
[probe.index]
sorted    = [true, false]
ascending = [true, true]
monotonic = [false, true]
)toml";
        const toml::table tbl = toml::parse(src);
        auto specs2 = Probe::parseCollectionsFromToml(tbl);
        TEST_EQ(specs2.size(), std::size_t(2));
        TEST_TRUE(specs2[0].indexSorted    == true);
        TEST_TRUE(specs2[0].indexAscending == true);
        TEST_TRUE(specs2[0].indexMonotonic == false);
        TEST_TRUE(specs2[1].indexSorted    == false);
        TEST_TRUE(specs2[1].indexAscending == true);
        TEST_TRUE(specs2[1].indexMonotonic == true);
        TEST_PASS("[probe.index] sorted/ascending/monotonic applied to CollectionSpec");
    }

    {
        // Explicit multi-collector count: analysis_threads different from
        // probe_threads.  Verify all events are still delivered exactly once.
        Probe::ProbeParallel probe;
        probe.setAnalysisThreadCount(2);  // 2 collectors, 4 reader threads
        probe.configureProbe(kFixtureRoot, specs, 4, kNEvents, true);

        std::atomic<std::size_t> count{0};
        probe.run([&](const Probe::Event& /*ev*/, int workerIndex) {
            TEST_TRUE(workerIndex >= 0 && workerIndex < 2);
            count.fetch_add(1, std::memory_order_relaxed);
        });
        TEST_EQ(count.load(std::memory_order_relaxed), static_cast<std::size_t>(kNEvents));
        TEST_PASS("CollectorThread with analysis_threads=2 delivers all events");
    }

    {
        // Error path: non-existent input file throws during configureProbe.
        Probe::ProbeParallel probe;
        bool caught = false;
        try {
            probe.configureProbe("/no/such/file.root", specs, 1, kNEvents, true);
        } catch (const std::runtime_error&) {
            caught = true;
        }
        TEST_TRUE(caught);
        TEST_PASS("configureProbe throws for non-existent input file");
    }

    // (Phase 5 cleanup: docs/WriterMT.md.  The Splitter / shard-cache tests
    //  were removed along with the Splitter feature itself.  ProbeParallel +
    //  multithreaded Writer is the production path; splitting was never the
    //  right fix for the original bottleneck.)

    // ── ProbeIMT tests (Phase 2) ──────────────────────────────────────────────
    // ProbeIMT must deliver the same set of events with the same particle
    // counts as ProbeParallel.  Drop-in substitution at the driver site;
    // identical user-callback semantics.
    {
        Probe::ProbeIMT probe;
        probe.configureProbe(kFixtureRoot, specs, 4, kNEvents, true);

        TEST_EQ(probe.eventCount(),  static_cast<std::size_t>(kNEvents));
        TEST_EQ(probe.threadCount(), std::size_t(4));
        TEST_TRUE(probe.streamType() == Probe::StreamType::Events);

        // ProbeIMT's flush is parallel; callback must be thread-safe.
        std::vector<Long64_t>    seen;
        std::mutex               seenMutex;
        std::atomic<std::size_t> totalProtons{0};
        std::atomic<std::size_t> totalPions{0};
        probe.run([&](const Probe::Event& ev, int workerIndex) {
            TEST_TRUE(workerIndex >= 0);
            TEST_EQ(ev.n("protons"), std::size_t(4));
            TEST_EQ(ev.n("pions"),   std::size_t(5));
            {
                std::lock_guard<std::mutex> lock(seenMutex);
                seen.push_back(ev.index);
            }
            totalProtons.fetch_add(ev.n("protons"), std::memory_order_relaxed);
            totalPions.fetch_add(ev.n("pions"),   std::memory_order_relaxed);
        });

        TEST_EQ(seen.size(),                std::size_t(kNEvents));
        TEST_EQ(totalProtons.load(),        std::size_t(kNEvents * 4));
        TEST_EQ(totalPions.load(),          std::size_t(kNEvents * 5));

        std::set<Long64_t> unique(seen.begin(), seen.end());
        TEST_EQ(unique.size(), static_cast<std::size_t>(kNEvents));
        TEST_EQ(*unique.begin(),  Long64_t(1));
        TEST_EQ(*unique.rbegin(), Long64_t(kNEvents));
        TEST_PASS("ProbeIMT delivers all events with correct particle counts");
    }

    {
        // Output equivalence: ProbeIMT and ProbeParallel must produce the
        // same per-event particle 4-momenta sums.  Sum components to avoid
        // depending on within-event particle order.
        auto sumOfRun = [&](auto& probe) {
            std::vector<double> sums(kNEvents * 8, 0.0);  // 8 = 4 components × 2 specs
            probe.run([&](const Probe::Event& ev, int /*t*/) {
                const std::size_t i = static_cast<std::size_t>(ev.index - 1);
                if (i >= static_cast<std::size_t>(kNEvents)) return;
                for (const auto& p : ev["protons"]) {
                    sums[i * 8 + 0] += p.Px(); sums[i * 8 + 1] += p.Py();
                    sums[i * 8 + 2] += p.Pz(); sums[i * 8 + 3] += p.E();
                }
                for (const auto& p : ev["pions"]) {
                    sums[i * 8 + 4] += p.Px(); sums[i * 8 + 5] += p.Py();
                    sums[i * 8 + 6] += p.Pz(); sums[i * 8 + 7] += p.E();
                }
            });
            return sums;
        };

        Probe::ProbeParallel manual;
        manual.configureProbe(kFixtureRoot, specs, 4, kNEvents, true);
        const auto manualSums = sumOfRun(manual);

        Probe::ProbeIMT imt;
        imt.configureProbe(kFixtureRoot, specs, 4, kNEvents, true);
        const auto imtSums = sumOfRun(imt);

        TEST_EQ(manualSums.size(), imtSums.size());
        bool allClose = true;
        for (std::size_t i = 0; i < manualSums.size(); ++i) {
            if (std::abs(manualSums[i] - imtSums[i]) > 1e-9) { allClose = false; break; }
        }
        TEST_TRUE(allClose);
        TEST_PASS("ProbeIMT output equivalence with ProbeParallel (per-event momentum sums)");
    }

    {
        // IMT mode rejects vector-stream specs (no index branches) with a
        // clear error.  Construct a malformed spec to exercise the path.
        Probe::CollectionSpec bad = specs.front();
        bad.indexBranches.clear();
        std::vector<Probe::CollectionSpec> badSpecs{bad};

        Probe::ProbeIMT probe;
        bool caught = false;
        try {
            probe.configureProbe(kFixtureRoot, badSpecs, 2, kNEvents, true);
        } catch (const std::runtime_error&) {
            caught = true;
        }
        TEST_TRUE(caught);
        TEST_PASS("ProbeIMT rejects vector-stream specs with a clear error");
    }

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
