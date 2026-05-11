#pragma once

// ── Probe/Splitter.hh ────────────────────────────────────────────────────────
// Fast-clone input-file splitter for ProbeParallel.
//
// Splits a single ROOT input file into N per-worker shard files so each
// worker reads from its own TFile, eliminating ROOT global-mutex contention
// on TBranch::GetEntry (see docs/ROOTMT.md, Phase 1).
//
// Called from ProbeParallel::configureProbe after prepareEntryBounds() has
// run.  The returned paths replace inputFile_ in each worker's EventStream
// constructor.  Workers still use the same event-key partitions; the shard
// contains exactly that key range so the worker reads from entry 0.
//
// Entry point: Splitter::ensureShards
// ─────────────────────────────────────────────────────────────────────────────

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <toml++/toml.hpp>

#include "Probe/BranchControl.hh"
#include "Probe/Types.hh"

#include "TFile.h"
#include "TROOT.h"
#include "TTree.h"

namespace fs = std::filesystem;

namespace Probe {
namespace Splitter {

    // ── Manifest ─────────────────────────────────────────────────────────────
    // Written to <shardDir>/manifest.toml after a successful split.
    // Used to validate cache reuse on subsequent runs.

    struct Manifest {
        std::string  sourcePath;
        std::string  rootVersion;
        std::int64_t sourceMtime = 0;      // fs::last_write_time ticks
        std::int64_t sourceSize  = 0;      // bytes
        std::size_t  shardCount  = 0;
        std::vector<std::int64_t> shardEntryCounts; // [shard]: entries across all trees
    };

    // ── File-stat helpers ─────────────────────────────────────────────────────

    inline std::int64_t fileMtime(const std::string& path) {
        std::error_code ec;
        const auto t = fs::last_write_time(path, ec);
        if (ec) return 0;
        return static_cast<std::int64_t>(t.time_since_epoch().count());
    }

    inline std::int64_t fileSize(const std::string& path) {
        std::error_code ec;
        const auto sz = fs::file_size(path, ec);
        return ec ? 0 : static_cast<std::int64_t>(sz);
    }

    // ── Directory naming ──────────────────────────────────────────────────────

    // 8-char lowercase hex hash of an arbitrary string via std::hash.
    inline std::string shortHash(const std::string& s) {
        const std::size_t h = std::hash<std::string>{}(s);
        std::ostringstream oss;
        oss << std::hex << (h & 0xFFFFFFFFu);
        return oss.str();
    }

    // Returns the shard sub-directory name (NOT a full path).
    // Format: <stem>_<8hex>_<N>shards
    inline std::string shardDirName(const std::string& inputFile,
                                    std::int64_t mtime,
                                    std::int64_t size,
                                    std::size_t  shardCount)
    {
        const std::string stem = fs::path(inputFile).stem().string();
        const std::string key  = inputFile
            + '|' + std::to_string(mtime)
            + '|' + std::to_string(size)
            + '|' + std::to_string(shardCount);
        return stem + "_" + shortHash(key) + "_" + std::to_string(shardCount) + "shards";
    }

    // Builds the full shard directory path: <baseDir>/<dirName>/
    inline std::string buildShardDir(const std::string& baseDir,
                                     const std::string& dirName)
    {
        std::string d = baseDir;
        if (!d.empty() && d.back() != '/') d += '/';
        d += dirName + '/';
        return d;
    }

    // ── Shard path helpers ────────────────────────────────────────────────────

    inline std::string shardPath(const std::string& dir, std::size_t s) {
        return dir + "shard_" + std::to_string(s) + ".root";
    }

    // ── Manifest I/O ─────────────────────────────────────────────────────────

    inline std::optional<Manifest> readManifest(const std::string& dir) {
        const std::string path = dir + "manifest.toml";
        std::error_code ec;
        if (!fs::exists(path, ec) || ec) return std::nullopt;
        try {
            const toml::table tbl = toml::parse_file(path);
            Manifest m;
            m.sourcePath  = tbl["source_path"].value_or(std::string{});
            m.rootVersion = tbl["root_version"].value_or(std::string{});
            m.sourceMtime = tbl["source_mtime"].value_or(std::int64_t{0});
            m.sourceSize  = tbl["source_size"].value_or(std::int64_t{0});
            m.shardCount  = static_cast<std::size_t>(
                tbl["shard_count"].value_or(std::int64_t{0}));
            if (const auto* arr = tbl["shard_entry_counts"].as_array()) {
                for (const auto& v : *arr)
                    m.shardEntryCounts.push_back(v.value_or(std::int64_t{0}));
            }
            return m;
        } catch (...) {
            return std::nullopt;
        }
    }

    inline void writeManifest(const std::string& dir, const Manifest& m) {
        const std::string path = dir + "manifest.toml";

        toml::array counts;
        for (const auto c : m.shardEntryCounts) counts.push_back(c);

        toml::table tbl;
        tbl.insert("source_path",        m.sourcePath);
        tbl.insert("root_version",       m.rootVersion);
        tbl.insert("source_mtime",       m.sourceMtime);
        tbl.insert("source_size",        m.sourceSize);
        tbl.insert("shard_count",        static_cast<std::int64_t>(m.shardCount));
        tbl.insert("shard_entry_counts", std::move(counts));

        std::ofstream f(path);
        if (!f)
            throw std::runtime_error("[Probe::Splitter] Cannot write manifest: " + path);
        f << tbl;
    }

    // ── Cache validation ──────────────────────────────────────────────────────

    inline bool isManifestCurrent(const Manifest& m,
                                  const std::string& inputFile,
                                  std::int64_t mtime,
                                  std::int64_t size,
                                  std::size_t  shardCount)
    {
        return m.sourcePath      == inputFile
            && m.sourceMtime     == mtime
            && m.sourceSize      == size
            && m.shardCount      == shardCount
            && m.rootVersion     == gROOT->GetVersion()
            && m.shardEntryCounts.size() == shardCount;
    }

    // Check that all expected shard files exist on disk.
    inline bool allShardsPresent(const std::string& dir, std::size_t n) {
        for (std::size_t s = 0; s < n; ++s) {
            std::error_code ec;
            if (!fs::exists(shardPath(dir, s), ec) || ec) return false;
        }
        return true;
    }

    // ── Orphan cleanup ────────────────────────────────────────────────────────
    // Scans baseDir for sub-directories whose manifest source doesn't match
    // the current inputFile (or whose manifest is missing/corrupt).
    // Removes them with one warning line each.  Never throws.

    inline void cleanupOrphans(const std::string& baseDir,
                                const std::string& inputFile)
    {
        std::error_code ec;
        if (!fs::exists(baseDir, ec) || ec) return;

        for (const auto& entry : fs::directory_iterator(baseDir, ec)) {
            if (ec) break;
            if (!entry.is_directory()) continue;
            const std::string d = entry.path().string() + "/";
            const auto opt = readManifest(d);
            bool orphan = false;
            if (!opt) {
                orphan = true;
            } else {
                // Orphan if source path differs (different input file).
                orphan = (opt->sourcePath != inputFile);
            }
            if (orphan) {
                std::cerr << "[Probe::Splitter] removing stale shard dir: " << d << '\n';
                std::error_code ec2;
                fs::remove_all(d, ec2);
            }
        }
    }

    // ── Shard removal ────────────────────────────────────────────────────────

    inline void removeShardDir(const std::string& dir) {
        std::error_code ec;
        if (!dir.empty() && fs::exists(dir, ec) && !ec)
            fs::remove_all(dir, ec);
    }

    // ── Core split ───────────────────────────────────────────────────────────
    // Opens inputFile once, fast-clones entries per shard into shardDir.
    //
    // entryBoundsByWorker: [worker][spec] → Probe::Bounds (entry-level range
    //   in the original file).  Empty when streamType is Vectors (use
    //   partitions directly as entry indices).
    //
    // Returns per-shard total entry counts (sum over all specs).

    inline std::vector<std::int64_t>
    splitFile(const std::string&                          inputFile,
              const std::vector<ParticleSpec>&             specs,
              const std::vector<BranchControl::Partition>& partitions,
              const std::vector<std::vector<Bounds>>&      entryBoundsByWorker,
              const std::string&                           shardDir)
    {
        const std::size_t N = partitions.size();
        std::vector<std::int64_t> entryCounts(N, 0);

        // ── open input once ───────────────────────────────────────────────────
        std::unique_ptr<TFile> inputF(TFile::Open(inputFile.c_str(), "READ"));
        if (!inputF || inputF->IsZombie())
            throw std::runtime_error(
                "[Probe::Splitter] Cannot open input file: " + inputFile);

        const bool useEntryBounds = !entryBoundsByWorker.empty();

        for (std::size_t s = 0; s < N; ++s) {

            const std::string outPath = shardPath(shardDir, s);
            TFile* shardF = TFile::Open(outPath.c_str(), "RECREATE");
            if (!shardF || shardF->IsZombie())
                throw std::runtime_error(
                    "[Probe::Splitter] Cannot create shard file: " + outPath);

            for (std::size_t p = 0; p < specs.size(); ++p) {
                const std::string& treeName = specs[p].tree;

                TTree* inTree = dynamic_cast<TTree*>(inputF->Get(treeName.c_str()));
                if (!inTree)
                    throw std::runtime_error(
                        "[Probe::Splitter] Missing tree '" + treeName +
                        "' in '" + inputFile + "'");

                // Ensure all branches are active for the copy.
                inTree->SetBranchStatus("*", 1);

                Long64_t firstEntry = 0;
                Long64_t nEntries   = 0;

                if (useEntryBounds) {
                    // Flat (indexed) stream: use pre-computed entry bounds.
                    const Bounds& b = entryBoundsByWorker[s][p];
                    if (b.valid()) {
                        firstEntry = b.first;
                        nEntries   = b.last - b.first + 1;
                    }
                    // else: no entries for this spec in this shard → copy 0
                } else {
                    // Vector stream: partitions are entry-level ranges.
                    const auto& part = partitions[s];
                    firstEntry = part.firstEvent;
                    nEntries   = (part.lastEvent >= part.firstEvent)
                                 ? part.lastEvent - part.firstEvent + 1
                                 : 0;
                }

                shardF->cd();

                TTree* outTree = nullptr;
                if (nEntries > 0) {
                    // Fast basket-level copy (no decompress/recompress).
                    outTree = inTree->CopyTree("", "fast", nEntries, firstEntry);
                } else {
                    // Clone schema only; no entries.
                    outTree = inTree->CloneTree(0);
                }

                if (!outTree)
                    throw std::runtime_error(
                        "[Probe::Splitter] CopyTree/CloneTree failed for tree '" +
                        treeName + "' shard " + std::to_string(s));

                entryCounts[s] += outTree->GetEntries();

                // Reset input-tree branch addresses left by CopyTree.
                inTree->ResetBranchAddresses();
            }

            shardF->Write("", TObject::kOverwrite);
            shardF->Close();
            delete shardF;
        }

        return entryCounts;
    }

    // ── Main entry point ──────────────────────────────────────────────────────
    // Ensures N shard files exist in <shardDir> that correctly represent the
    // partitioned contents of inputFile.
    //
    // Returns the vector of shard file paths (one per partition).
    // shardDirOut receives the directory path actually used (for cleanup).
    //
    // Algorithm:
    //   1. Scan baseDir for orphan dirs and remove them.
    //   2. Compute the expected shardDir from the source-file identity.
    //   3. If shardDir exists with a valid manifest: cache hit, return paths.
    //   4. Otherwise: split, write manifest, return paths.

    inline std::vector<std::string>
    ensureShards(const std::string&                          inputFile,
                 const std::vector<ParticleSpec>&             specs,
                 const std::vector<BranchControl::Partition>& partitions,
                 const std::vector<std::vector<Bounds>>&      entryBoundsByWorker,
                 const std::string&                           baseDir,
                 std::string&                                 shardDirOut)
    {
        const std::size_t N     = partitions.size();
        const std::int64_t mtime = fileMtime(inputFile);
        const std::int64_t size  = fileSize(inputFile);

        // ── orphan scan ───────────────────────────────────────────────────────
        cleanupOrphans(baseDir, inputFile);

        // ── shard directory ───────────────────────────────────────────────────
        const std::string dirName = shardDirName(inputFile, mtime, size, N);
        shardDirOut = buildShardDir(baseDir, dirName);

        // ── cache check ───────────────────────────────────────────────────────
        const auto optManifest = readManifest(shardDirOut);
        if (optManifest
                && isManifestCurrent(*optManifest, inputFile, mtime, size, N)
                && allShardsPresent(shardDirOut, N))
        {
            std::cerr << "[Probe::Splitter] reusing " << N
                      << " cached shards in " << shardDirOut << '\n';
            std::vector<std::string> paths;
            paths.reserve(N);
            for (std::size_t s = 0; s < N; ++s)
                paths.push_back(shardPath(shardDirOut, s));
            return paths;
        }

        // ── create shard directory ────────────────────────────────────────────
        {
            std::error_code ec;
            fs::create_directories(shardDirOut, ec);
            if (ec)
                throw std::runtime_error(
                    "[Probe::Splitter] Cannot create shard dir: " + shardDirOut +
                    " (" + ec.message() + ")");
        }

        std::cerr << "[Probe::Splitter] splitting " << inputFile
                  << " into " << N << " shards in " << shardDirOut << " ...\n";

        // ── split ─────────────────────────────────────────────────────────────
        const std::vector<std::int64_t> counts =
            splitFile(inputFile, specs, partitions, entryBoundsByWorker, shardDirOut);

        // ── write manifest ────────────────────────────────────────────────────
        Manifest m;
        m.sourcePath       = inputFile;
        m.rootVersion      = gROOT->GetVersion();
        m.sourceMtime      = mtime;
        m.sourceSize       = size;
        m.shardCount       = N;
        m.shardEntryCounts = counts;
        writeManifest(shardDirOut, m);

        std::cerr << "[Probe::Splitter] split complete.\n";

        std::vector<std::string> paths;
        paths.reserve(N);
        for (std::size_t s = 0; s < N; ++s)
            paths.push_back(shardPath(shardDirOut, s));
        return paths;
    }

} // namespace Splitter
} // namespace Probe
