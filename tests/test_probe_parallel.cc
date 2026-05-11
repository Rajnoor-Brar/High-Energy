// Focused tests for Probe::ProbeParallel execution modes.

#include <algorithm>
#include <atomic>
#include <exception>
#include <filesystem>
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

    // ── Split-cache test ──────────────────────────────────────────────────────
    // Verifies that:
    //   1. configureProbe creates N shard files in the temp directory.
    //   2. A second configureProbe (same input, same N) reuses cached shards.
    //   3. All events are delivered correctly when reading from shards.
    //   4. Shard directory is removed when keep_shards = false (destructor).
    {
        const std::string tempBase = "temp/test_split_cache/";

        // ── first run: create shards, keep them so we can inspect ────────────
        std::string capturedShardDir;
        {
            Probe::ProbeParallel probe;
            probe.configureProbe(kFixtureRoot, specs, 2, kNEvents, true,
                                 /*splitInput=*/true,
                                 tempBase, /*keepShards=*/true, "fixture");

            // Two shards should have been created.
            TEST_EQ(probe.inputShards().size(), std::size_t(2));
            capturedShardDir = probe.shardTempDir();
            TEST_TRUE(!capturedShardDir.empty());

            // Both shard files must exist on disk.
            for (std::size_t s = 0; s < 2; ++s) {
                std::error_code ec;
                TEST_TRUE(fs::exists(Probe::Splitter::shardPath(capturedShardDir, s), ec));
            }

            // Manifest must be present.
            const auto manifest = Probe::Splitter::readManifest(capturedShardDir);
            TEST_TRUE(manifest.has_value());
            TEST_EQ(manifest->shardCount, std::size_t(2));
            TEST_EQ(manifest->shardEntryCounts.size(), std::size_t(2));

            // All events must still be delivered.
            std::vector<Long64_t> seen;
            probe.run([&](const Probe::Event& ev, int /*t*/) {
                seen.push_back(ev.index);
            });
            TEST_EQ(seen.size(), static_cast<std::size_t>(kNEvents));
            std::set<Long64_t> unique(seen.begin(), seen.end());
            TEST_EQ(unique.size(), static_cast<std::size_t>(kNEvents));
            TEST_PASS("Phase 1 shard split creates correct shard files and delivers all events");
        }
        // Destructor ran with keepShards=true → directory must still exist.
        {
            std::error_code ec;
            TEST_TRUE(fs::exists(capturedShardDir, ec));
        }

        // ── second run: cache reuse ───────────────────────────────────────────
        {
            Probe::ProbeParallel probe;
            probe.configureProbe(kFixtureRoot, specs, 2, kNEvents, true,
                                 /*splitInput=*/true,
                                 tempBase, /*keepShards=*/true, "fixture");

            // Same shard directory should be reused (paths match).
            TEST_EQ(probe.shardTempDir(), capturedShardDir);
            TEST_PASS("Phase 1 shard cache reuse: same dir on second configureProbe");
        }

        // ── cleanup run: keepShards = false, destructor removes dir ──────────
        {
            Probe::ProbeParallel probe;
            probe.configureProbe(kFixtureRoot, specs, 2, kNEvents, true,
                                 /*splitInput=*/true,
                                 tempBase, /*keepShards=*/false, "fixture");
            // Shards exist during the run.
            TEST_EQ(probe.inputShards().size(), std::size_t(2));
        }
        // Destructor ran with keepShards=false → directory must be gone.
        {
            std::error_code ec;
            TEST_TRUE(!fs::exists(capturedShardDir, ec));
            TEST_PASS("Phase 1 shard cleanup: directory removed after run with keep_shards=false");
        }

        // Clean up tempBase itself.
        { std::error_code ec; fs::remove_all(tempBase, ec); }
    }

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

        std::vector<Long64_t> seen;
        std::size_t totalProtons = 0;
        std::size_t totalPions   = 0;
        probe.run([&](const Probe::Event& ev, int workerIndex) {
            TEST_TRUE(workerIndex >= 0);
            TEST_EQ(ev.n("protons"), std::size_t(4));
            TEST_EQ(ev.n("pions"),   std::size_t(5));
            seen.push_back(ev.index);
            totalProtons += ev.n("protons");
            totalPions   += ev.n("pions");
        });

        TEST_EQ(seen.size(),  static_cast<std::size_t>(kNEvents));
        TEST_EQ(totalProtons, std::size_t(kNEvents * 4));
        TEST_EQ(totalPions,   std::size_t(kNEvents * 5));

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
