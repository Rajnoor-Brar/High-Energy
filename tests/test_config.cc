// Round-trip tests for the Config parsing layer.
//
// Verifies that TOML keys → Config struct fields work correctly for the
// Probe, Record, and Monitor sections, and that the Phase 8 fix (no
// directory creation in configureProbe) holds.

#include <iostream>
#include <filesystem>
#include <fstream>
#include <string>
#include <thread>

#include "test_assert.hh"

#include "Config.hh"
#include "Monitor/Configure.hh"
#include "Probe.hh"

namespace {
    const std::string kFixtureToml = "tests/fixtures/lambda_fixture.toml";
    const std::string kProject     = "test_config";

    std::string writeTempConfig(const std::string& name, const std::string& body) {
        const std::filesystem::path dir = "output/test_config";
        std::filesystem::create_directories(dir);
        const std::filesystem::path path = dir / name;
        std::ofstream out(path);
        out << body;
        return path.string();
    }
}

int main() {
    std::cout << "── test_config ──────────────────────────────────────────────\n";

    // ── readConfigValues: event_count, record threads ────────────────────────
    {
        Config::Events   events;
        Config::Watch    watch;
        Config::Register reg;
        Config::readConfigValues(kFixtureToml, kProject, events, watch, reg);

        TEST_EQ(events.eventCount, std::size_t(50));
        TEST_TRUE(events.userEvents);
        TEST_EQ(watch.nEvents, std::size_t(50));

        // writer_threads = 2 in fixture (resolveSectionThreadCount keeps it as-is
        // since it is > 0)
        TEST_EQ(reg.writer_threads, std::size_t(2));

        // serial = 0 in fixture
        TEST_EQ(reg.serial, 0);
        TEST_EQ(reg.binCount, 100);
        TEST_NEAR(reg.histScale, 1.0, 1e-12);

        TEST_PASS("readConfigValues populates Events/Watch/Register correctly");
    }

    // ── record-owned histogram settings ─────────────────────────────────────
    {
        const std::string cfg = writeTempConfig("record_hist.toml", R"toml(
[events]
event_count = 10

[record]
writer_threads = 1
bin_count = 321
hist_scaling = 2.5

[lambda]
hist_limits = "tests/fixtures/lambda_fixture_limits.toml"
)toml");

        Config::Events   events;
        Config::Watch    watch;
        Config::Register reg;
        Config::readConfigValues(cfg, kProject, events, watch, reg);

        TEST_EQ(reg.binCount, 321);
        TEST_NEAR(reg.histScale, 2.5, 1e-12);
        TEST_PASS("[record] owns histogram bin count and scaling");
    }

    // ── canonical all.toml stays parseable by Config:: ──────────────────────
    {
        Config::Events   events;
        Config::Watch    watch;
        Config::Register reg;
        Config::readConfigValues("configs/all.toml", kProject, events, watch, reg);

        TEST_EQ(events.eventCount, std::size_t(10000));
        TEST_EQ(reg.binCount, 500);
        TEST_NEAR(reg.histScale, 1.0, 1e-12);
        TEST_TRUE(!reg.particleLimits.empty());
        TEST_TRUE(!reg.eventLimits.empty());
        TEST_PASS("configs/all.toml parses through Config::readConfigValues");
    }

    // ── stale monitor histogram keys rejected ───────────────────────────────
    {
        const std::string cfg = writeTempConfig("bad_monitor_hist.toml", R"toml(
[monitor]
bin_count = 999
)toml");

        bool rejected = false;
        try {
            Monitor::AsyncLogger logger(false);
            Monitor::configureMonitor(logger, cfg, kProject);
        } catch (const std::runtime_error&) {
            rejected = true;
        }
        TEST_TRUE(rejected);
        TEST_PASS("[monitor].bin_count is rejected");
    }

    // ── monitor subtables ───────────────────────────────────────────────────
    {
        const std::string cfg = writeTempConfig("monitor_subtables.toml", R"toml(
[monitor]
true_time_at_config = true

[monitor.intervals]
print_interval = 7
heartbeat_interval = 13
terminal_refresh_interval = 0.5
program_stall_threshold = 1.5
checkpoint_interval = 17

[monitor.logs]
save_heartbeat = true
save_checkpoints = true
save_log_threads = true
save_final_log = false
)toml");

        Monitor::AsyncLogger logger(false);
        logger.watch().nEvents = 100;
        Monitor::configureMonitor(logger, cfg, kProject);

        const Monitor::PacingInfo& pacing = logger.pacingInfo();
        TEST_EQ(pacing.printInterval, std::size_t(7));
        TEST_EQ(pacing.heartbeatMs.count(), Config::uSeconds(13000).count());
        TEST_EQ(pacing.terminalRefresh.count(), Config::Seconds(30).count());
        TEST_EQ(pacing.stallThreshold.count(), Config::Seconds(90).count());
        TEST_TRUE(logger.saveHeartbeat());
        TEST_TRUE(logger.saveCheckpoints());
        TEST_TRUE(logger.saveLogThreads());
        TEST_FALSE(logger.saveFinalLog());
        TEST_PASS("Monitor::configureMonitor reads [monitor.intervals] and [monitor.logs]");
    }

    // ── stale flat monitor pacing keys rejected ─────────────────────────────
    {
        const std::string cfg = writeTempConfig("bad_monitor_flat.toml", R"toml(
[monitor]
print_interval = 7
)toml");

        bool rejected = false;
        try {
            Monitor::AsyncLogger logger(false);
            Monitor::configureMonitor(logger, cfg, kProject);
        } catch (const std::runtime_error&) {
            rejected = true;
        }
        TEST_TRUE(rejected);
        TEST_PASS("[monitor].print_interval is rejected");
    }

    // ── configureProbe: probe threads, analysis threads, collections ─────────
    {
        Config::Watch       watch;
        Config::Register    reg;
        Config::ProbeConfig probe;
        Config::configureProbe(kFixtureToml, kProject, watch, reg, probe);

        TEST_EQ(probe.eventConfig.eventCount, std::size_t(50));

        // probe_threads = 4, analysis_threads = 2 in fixture
        TEST_EQ(probe.probe_threads,    std::size_t(4));
        TEST_EQ(probe.analysis_threads, std::size_t(2));

        // Two event-particle specs: pions and protons (alphabetical toml++ order).
        // Phase 11: usesNewToml removed; parseProbeConfig is now always used.
        TEST_EQ(probe.probeSpec.eventParticles.size(), std::size_t(2));
        const auto& ep = probe.probeSpec.eventParticles;
        // toml++ iterates sub-table keys alphabetically: pions before protons.
        TEST_TRUE(ep[0].label == "pions" || ep[1].label == "pions");
        TEST_TRUE(ep[0].label == "protons" || ep[1].label == "protons");
        // Both specs carry default index flags (true/true/true).
        TEST_TRUE(ep[0].indexSorted && ep[0].indexAscending && ep[0].indexMonotonic);

        TEST_PASS("configureProbe reads probe/probeSpec without creating directories (Phase 10)");
    }

    // (Phase 11: [probe.index] / parseCollectionsFromToml removed;
    //  per-spec index flags are tested in test_probe_parallel.cc.)

    // ── thread count resolution ──────────────────────────────────────────────
    {
        // 0 threads → auto-resolved to (hw-2)/3, clamped ≥ 1.
        const std::size_t hw = std::thread::hardware_concurrency();
        const std::size_t expected = (hw > 2) ? std::max<std::size_t>(1, (hw - 2) / 3) : 1;
        TEST_EQ(Config::resolveSectionThreadCount(0), expected);
        // Non-zero → returned as-is.
        TEST_EQ(Config::resolveSectionThreadCount(7), std::size_t(7));
        TEST_PASS("resolveSectionThreadCount: zero→auto, non-zero→passthrough");
    }

    // ── stale alias rejection ────────────────────────────────────────────────
    {
        const std::string bad = R"toml(
[run]
event_count = 10
)toml";
        bool rejected = false;
        try {
            const toml::table tbl = toml::parse(bad);
            Config::rejectSectionAliases(tbl);
        } catch (const std::runtime_error&) {
            rejected = true;
        }
        TEST_TRUE(rejected);
        TEST_PASS("rejectSectionAliases throws for removed '[run]' key");
    }

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
