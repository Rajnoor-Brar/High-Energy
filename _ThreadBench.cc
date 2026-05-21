// _ThreadBench.cc
// ──────────────────────────────────────────────────────────────────────────────
// Sweeps (probe × analysis × writer) thread-count combinations for a given
// reconstruction binary + config, measures wall time, and reports the fastest
// configuration.
//
// Usage:
//   ./_ThreadBench.exe [binary] [configPath] [nEvents]
//
// Defaults:
//   binary     = ./_Lambda_Reconstruction.exe
//   configPath = configs/Lambda_Reconstruction.toml
//   nEvents    = 10000
//
// Candidates are powers of 2 from 1 up to hardware_concurrency().
// Combinations where probe+analysis+writer > 2×hw are skipped.
// Output directories are redirected to /tmp/thread_bench/ so no real output
// is written.  Temp TOML files are cleaned up after the run.
// ──────────────────────────────────────────────────────────────────────────────

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <tuple>
#include <vector>

#include <toml++/toml.hpp>

namespace fs = std::filesystem;

// ── Types ─────────────────────────────────────────────────────────────────────

struct RunResult {
    std::size_t probe, analysis, writer;
    double wallSec;
    double evPerSec;
};

// ── Helpers ───────────────────────────────────────────────────────────────────

// Powers of 2 from 1 up to hw (inclusive).
static std::vector<std::size_t> makeThreadCandidates(std::size_t hw) {
    std::vector<std::size_t> v;
    for (std::size_t n = 1; n <= hw; n *= 2)
        v.push_back(n);
    return v;
}

// Build a modified TOML string from a deep copy of the base config.
// Overrides: [events].event_count, [threads], [record.paths], [monitor.logs].
static std::string buildTempToml(const toml::table& base,
                                 const std::string& scratchDir,
                                 std::size_t        nEvents,
                                 std::size_t        probe_t,
                                 std::size_t        analysis_t,
                                 std::size_t        writer_t)
{
    toml::table cfg = base;   // deep copy (toml++ is value-semantic)

    // ── [events].event_count ─────────────────────────────────────────────────
    if (auto* ev = cfg["events"].as_table()) {
        ev->insert_or_assign("event_count", (int64_t)nEvents);
    } else {
        cfg.insert_or_assign("events",
            toml::table{{ "event_count", (int64_t)nEvents }});
    }

    // ── [threads] — wholesale replacement ───────────────────────────────────
    cfg.insert_or_assign("threads", toml::table{
        { "probe",    (int64_t)probe_t    },
        { "analysis", (int64_t)analysis_t },
        { "writer",   (int64_t)writer_t   }
    });

    // ── [record] — redirect output to scratch, disable serial subdir ─────────
    if (auto* rec = cfg["record"].as_table()) {
        const std::string outDir = scratchDir + "/output/";
        rec->insert_or_assign("serial", (int64_t)0);
        rec->insert_or_assign("paths", toml::table{
            { "directory",            outDir                       },
            { "output_log_directory", std::string("logs/")         },
            { "checkpoint_directory", std::string("checkpoints/")  },
            { "serialDirectory",      false                        },
            { "logInSubDir",          true                         },
            { "checkpointsInSubDir",  true                         }
        });
    }

    // ── [monitor.logs] — silence all file I/O ───────────────────────────────
    const toml::table silentLogs{
        { "save_final_log",   false },
        { "save_checkpoints", false },
        { "save_log_threads", false },
        { "save_heartbeat",   false }
    };
    if (auto* mon = cfg["monitor"].as_table()) {
        mon->insert_or_assign("logs", silentLogs);
    } else {
        cfg.insert_or_assign("monitor",
            toml::table{{ "logs", silentLogs }});
    }

    std::ostringstream oss;
    oss << cfg;
    return oss.str();
}

// ── main ──────────────────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    const std::string binary  = argc > 1 ? argv[1] : "./_Lambda_Reconstruction.exe";
    const std::string baseCfg = argc > 2 ? argv[2] : "configs/Lambda_Reconstruction.toml";
    const std::size_t nEvents = argc > 3
        ? static_cast<std::size_t>(std::stoul(argv[3]))
        : 10000;

    // ── Load base config ─────────────────────────────────────────────────────
    toml::table baseConfig;
    try {
        baseConfig = toml::parse_file(baseCfg);
    } catch (const toml::parse_error& e) {
        std::cerr << "[ThreadBench] Failed to parse '" << baseCfg << "': " << e << "\n";
        return 1;
    }

    // ── Setup scratch directory ──────────────────────────────────────────────
    const std::string scratchDir = "/tmp/thread_bench";
    fs::create_directories(scratchDir + "/output");

    // ── Build permutation list ───────────────────────────────────────────────
    const std::size_t hw         = std::thread::hardware_concurrency();
    const std::size_t maxTotal   = 2 * hw;
    const auto        candidates = makeThreadCandidates(hw);

    using Triple = std::tuple<std::size_t, std::size_t, std::size_t>;
    std::vector<Triple> perms;
    for (auto p : candidates)
        for (auto a : candidates)
            for (auto w : candidates)
                if (p + a + w <= maxTotal)
                    perms.emplace_back(p, a, w);

    // ── Header ───────────────────────────────────────────────────────────────
    std::cout << "\n"
              << "[ThreadBench] Binary  : " << binary      << "\n"
              << "[ThreadBench] Config  : " << baseCfg     << "\n"
              << "[ThreadBench] Events  : " << nEvents     << "\n"
              << "[ThreadBench] HW cores: " << hw          << "\n"
              << "[ThreadBench] Runs    : " << perms.size()<< "\n\n";

    const int W_RUN = 5, W_THD = 8, W_ANA = 10, W_WRT = 8, W_SEC = 10, W_EPS = 12;

    std::cout << std::setw(W_RUN) << "Run"
              << std::setw(W_THD) << "Probe"
              << std::setw(W_ANA) << "Analysis"
              << std::setw(W_WRT) << "Writer"
              << std::setw(W_SEC) << "Wall(s)"
              << std::setw(W_EPS) << "ev/s"
              << "\n"
              << std::string(W_RUN+W_THD+W_ANA+W_WRT+W_SEC+W_EPS, '-') << "\n";

    // ── Run sweep ────────────────────────────────────────────────────────────
    std::vector<RunResult> results;
    results.reserve(perms.size());

    int runIdx = 0;
    std::vector<std::string> tempFiles;

    for (auto [p, a, w] : perms) {
        ++runIdx;
        const std::string cfgPath =
            scratchDir + "/run_" + std::to_string(runIdx) + ".toml";
        tempFiles.push_back(cfgPath);

        // Write temp TOML
        {
            std::ofstream f(cfgPath);
            if (!f) {
                std::cerr << "[ThreadBench] Cannot write '" << cfgPath << "'\n";
                continue;
            }
            f << buildTempToml(baseConfig, scratchDir, nEvents, p, a, w);
        }

        // Run binary, measure wall time
        const std::string cmd = binary + " " + cfgPath + " </dev/null >/dev/null 2>&1";
        const auto t0 = std::chrono::steady_clock::now();
        const int  rc = std::system(cmd.c_str());
        const auto t1 = std::chrono::steady_clock::now();

        const double wallSec = std::chrono::duration<double>(t1 - t0).count();
        const double evps    = (rc == 0 && wallSec > 0.0)
                                 ? (static_cast<double>(nEvents) / wallSec)
                                 : 0.0;

        std::cout << std::setw(W_RUN) << runIdx
                  << std::setw(W_THD) << p
                  << std::setw(W_ANA) << a
                  << std::setw(W_WRT) << w
                  << std::setw(W_SEC) << std::fixed << std::setprecision(2) << wallSec
                  << std::setw(W_EPS) << std::fixed << std::setprecision(0) << evps;

        if (rc != 0)
            std::cout << "  [exit=" << rc << "]";
        std::cout << "\n";
        std::cout.flush();

        if (rc == 0)
            results.push_back({ p, a, w, wallSec, evps });
    }

    // ── Cleanup temp files ───────────────────────────────────────────────────
    for (const auto& f : tempFiles)
        fs::remove(f);

    if (results.empty()) {
        std::cerr << "\n[ThreadBench] All runs failed — nothing to report.\n";
        return 1;
    }

    // ── Sort and report top-5 ────────────────────────────────────────────────
    std::sort(results.begin(), results.end(),
              [](const RunResult& x, const RunResult& y){ return x.evPerSec > y.evPerSec; });

    const std::size_t topN = std::min<std::size_t>(5, results.size());

    std::cout << "\n-- Top " << topN << " results (fastest first) "
              << std::string(28, '-') << "\n\n"
              << std::setw(W_RUN) << "Rank"
              << std::setw(W_THD) << "Probe"
              << std::setw(W_ANA) << "Analysis"
              << std::setw(W_WRT) << "Writer"
              << std::setw(W_SEC) << "Wall(s)"
              << std::setw(W_EPS) << "ev/s"
              << "\n"
              << std::string(W_RUN+W_THD+W_ANA+W_WRT+W_SEC+W_EPS, '-') << "\n";

    for (std::size_t i = 0; i < topN; ++i) {
        const auto& r = results[i];
        std::cout << std::setw(W_RUN) << (i + 1)
                  << std::setw(W_THD) << r.probe
                  << std::setw(W_ANA) << r.analysis
                  << std::setw(W_WRT) << r.writer
                  << std::setw(W_SEC) << std::fixed << std::setprecision(2) << r.wallSec
                  << std::setw(W_EPS) << std::fixed << std::setprecision(0) << r.evPerSec
                  << "\n";
    }

    // ── Recommended [threads] block ──────────────────────────────────────────
    const auto& best = results[0];
    std::cout << "\n-- Recommended [threads] block "
              << std::string(28, '-') << "\n\n"
              << "[threads]\n"
              << "probe    = " << best.probe    << "\n"
              << "analysis = " << best.analysis << "\n"
              << "writer   = " << best.writer   << "\n\n"
              << "( " << std::fixed << std::setprecision(0) << best.evPerSec
              << " ev/s  on " << hw << "-core machine with " << nEvents << " events )\n\n";

    return 0;
}
