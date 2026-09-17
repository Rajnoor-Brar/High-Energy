// ── tests/spike_imt_read.cc ──────────────────────────────────────────────────
// Phase 2 spike binary for docs/ROOTMT.md.
//
// Question: does ROOT::EnableImplicitMT + TTreeProcessorMT break the ~150% CPU
// floor on our access pattern?  Phase 1 (per-worker shard files) confirmed the
// limiter is ROOT's global thread-safety mutex, not per-TFile basket contention.
// IMT is the only known in-ROOT way to escape that lock; this spike measures
// whether it actually does, before we commit to the full ProbeIMT refactor.
//
// Deliberately minimal: ~150 LOC, no Probe dependencies.  Reads one numeric
// branch from one tree and accumulates a sum, forcing real basket
// decompression.  Compare wall time at nThreads=1 vs nThreads=8 to compute
// speed-up.  Pair with `/usr/bin/time -v` for true CPU% measurement.
//
// Build:
//   make tests/spike_imt_read.exe
//
// Usage:
//   tests/spike_imt_read.exe <input.root> <tree> <branch> <type=D|F> [nThreads] [firstEntry] [lastEntry]
//
// When firstEntry and lastEntry are provided, TTreeProcessorMT is constructed
// with a globalRange = {firstEntry, lastEntry + 1} (ROOT's half-open
// convention).  This tests whether IMT actually subdivides work *below*
// basket-cluster boundaries — the load-bearing assumption behind the
// chunked-streaming ProbeIMT proposal.
//
// Examples:
//   # baseline (no IMT)
//   /usr/bin/time -v tests/spike_imt_read.exe input.root Protons Px D 1
//   # IMT with 8 threads
//   /usr/bin/time -v tests/spike_imt_read.exe input.root Protons Px D 8
//
// Decision matrix (per docs/ROOTMT.md):
//   nThreads=8 CPU ≈ 800% and wall ≈ 1/N×baseline   → land Phase 2 proper.
//   nThreads=8 CPU 200-400% and wall 2-3×           → judgment call.
//   nThreads=8 CPU stays ~150% and wall unchanged   → IMT doesn't help us;
//                                                     skip to Fallback A or B.
//   iostat shows disk-saturated during baseline    → Fallback B (accept floor).
//
// NOT built by `make test`; opt-in.
// ─────────────────────────────────────────────────────────────────────────────

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>

#include "TBranch.h"
#include "TChain.h"
#include "TFile.h"
#include "TROOT.h"
#include "TTreeReader.h"
#include "TTreeReaderValue.h"
#include "ROOT/TTreeProcessorMT.hxx"

namespace {

    // ── arg parsing ───────────────────────────────────────────────────────────
    struct Args {
        std::string input;
        std::string tree;
        std::string branch;
        char        typeCode = 'D';     // D=Double_t, F=Float_t
        unsigned    nThreads = 1;
        bool        hasRange = false;
        long long   firstEntry = 0;
        long long   lastEntry  = 0;     // inclusive
    };

    void usage(const char* argv0) {
        std::cerr <<
            "Usage: " << argv0 << " <input.root> <tree> <branch> <type=D|F> [nThreads=1] [firstEntry lastEntry]\n"
            "  type:     D for Double_t, F for Float_t\n"
            "  nThreads: 1 disables IMT (baseline); >1 enables it\n"
            "  firstEntry/lastEntry: inclusive range; if both omitted, processes the whole chain\n";
    }

    Args parseArgs(int argc, char** argv) {
        if (argc < 5) { usage(argv[0]); std::exit(2); }
        Args a;
        a.input    = argv[1];
        a.tree     = argv[2];
        a.branch   = argv[3];
        const std::string t = argv[4];
        if (t.size() != 1 || (t[0] != 'D' && t[0] != 'F')) {
            std::cerr << "Invalid type code: " << t << " (expected D or F)\n";
            std::exit(2);
        }
        a.typeCode = t[0];
        if (argc >= 6) a.nThreads = static_cast<unsigned>(std::atoi(argv[5]));
        if (a.nThreads == 0) a.nThreads = 1;
        if (argc >= 8) {
            a.firstEntry = std::atoll(argv[6]);
            a.lastEntry  = std::atoll(argv[7]);
            a.hasRange   = true;
        }
        return a;
    }

    // ── timed scan ────────────────────────────────────────────────────────────
    // Process all entries in `chain`, summing `branch`.  Forces basket reads.
    // Templated on the leaf type so we can bind TTreeReaderValue correctly.
    template<typename T>
    void scanOne(TTreeReader& reader,
                 const std::string& branch,
                 std::atomic<long long>& count,
                 std::atomic<double>&    sum)
    {
        TTreeReaderValue<T> v(reader, branch.c_str());
        double local = 0.0;
        long long n = 0;
        while (reader.Next()) {
            local += static_cast<double>(*v);
            ++n;
        }
        // atomic merge
        double prev = sum.load(std::memory_order_relaxed);
        while (!sum.compare_exchange_weak(prev, prev + local,
                                          std::memory_order_relaxed)) { /* retry */ }
        count.fetch_add(n, std::memory_order_relaxed);
    }

    // Dispatch on type code; runs scan either serially or through IMT.
    void runScan(const Args& a, TChain& chain,
                 std::atomic<long long>& count,
                 std::atomic<double>&    sum)
    {
        auto callback = [&](TTreeReader& r) {
            if (a.typeCode == 'D') scanOne<Double_t>(r, a.branch, count, sum);
            else                   scanOne<Float_t>(r, a.branch, count, sum);
        };

        if (a.nThreads > 1) {
            if (a.hasRange) {
                // ROOT's globalRange uses half-open [start, end) semantics.
                const std::pair<Long64_t, Long64_t> range{
                    static_cast<Long64_t>(a.firstEntry),
                    static_cast<Long64_t>(a.lastEntry + 1)
                };
                ROOT::TTreeProcessorMT processor(
                    std::string_view{a.input},
                    std::string_view{a.tree},
                    a.nThreads, range);
                processor.Process(callback);
            } else {
                ROOT::TTreeProcessorMT processor(chain);
                processor.Process(callback);
            }
        } else {
            TTreeReader r(&chain);
            if (a.hasRange) r.SetEntriesRange(a.firstEntry, a.lastEntry + 1);
            callback(r);
        }
    }

} // anonymous

int main(int argc, char** argv) {
    const Args a = parseArgs(argc, argv);

    // ── sanity: open + verify ─────────────────────────────────────────────────
    {
        std::unique_ptr<TFile> f(TFile::Open(a.input.c_str(), "READ"));
        if (!f || f->IsZombie()) {
            std::cerr << "Cannot open: " << a.input << "\n";
            return 1;
        }
        auto* t = dynamic_cast<TTree*>(f->Get(a.tree.c_str()));
        if (!t) {
            std::cerr << "Tree '" << a.tree << "' missing from " << a.input << "\n";
            return 1;
        }
        if (!t->GetBranch(a.branch.c_str())) {
            std::cerr << "Branch '" << a.branch << "' missing from tree '"
                      << a.tree << "'\n";
            return 1;
        }
    }

    // ── enable threading mode ─────────────────────────────────────────────────
    // Baseline still gets ThreadSafety so the comparison is apples-to-apples
    // with our production reads (which always have it on).
    if (a.nThreads > 1) ROOT::EnableImplicitMT(a.nThreads);
    else                ROOT::EnableThreadSafety();

    // ── build chain ───────────────────────────────────────────────────────────
    TChain chain(a.tree.c_str());
    chain.Add(a.input.c_str());
    const long long total = chain.GetEntries();

    std::cerr
        << "spike_imt_read: input=" << a.input
        << " tree="     << a.tree
        << " branch="   << a.branch
        << " type="     << a.typeCode
        << " entries="  << total
        << " nThreads=" << a.nThreads
        << " IMT="      << (a.nThreads > 1 ? "on" : "off")
        << "\n";

    // ── timed scan ────────────────────────────────────────────────────────────
    std::atomic<long long> count{0};
    std::atomic<double>    sum{0.0};

    const auto       wallStart = std::chrono::steady_clock::now();
    const std::clock_t cpuStart = std::clock();

    runScan(a, chain, count, sum);

    const auto       wallEnd = std::chrono::steady_clock::now();
    const std::clock_t cpuEnd = std::clock();

    const double wallSec = std::chrono::duration<double>(wallEnd - wallStart).count();
    const double cpuSec  = static_cast<double>(cpuEnd - cpuStart) / CLOCKS_PER_SEC;
    const double cpuPct  = wallSec > 0 ? 100.0 * cpuSec / wallSec : 0.0;
    const double thru    = wallSec > 0 ? static_cast<double>(count.load()) / wallSec : 0.0;

    // ── report ────────────────────────────────────────────────────────────────
    std::cout
        << "---- spike_imt_read result ----\n"
        << "  entries read    : " << count.load() << " / " << total << "\n"
        << "  wall time (s)   : " << wallSec << "\n"
        << "  cpu  time (s)   : " << cpuSec  << "\n"
        << "  cpu utilisation : " << cpuPct  << " %   (target: nThreads * 100% with IMT)\n"
        << "  throughput      : " << thru    << " entries/s\n"
        << "  branch sum      : " << sum.load() << "  (sanity)\n"
        << "-------------------------------\n"
        << "Compare against nThreads=1 baseline to compute speed-up.\n"
        << "For true CPU% wrap this binary in /usr/bin/time -v.\n";

    return (count.load() == total) ? 0 : 3;
}
