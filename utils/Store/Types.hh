#pragma once

// ── Store/Types.hh ───────────────────────────────────────────────────────────
// What an event store is made of (11 §1–2, decision D13).
//
// A store is a directory of HepMC3 shards plus one index:
//
//   events/
//     events.index.json      written last, atomically
//     events.0.hepmc.gz      one shard per generator worker (Parallelism:index)
//     events.1.hepmc.gz
//
// One shard per worker, because HepMC3 ASCII has no random access: a single file can only be read
// serially, whereas shards are written without a lock and replayed in parallel, one reader each. Each
// shard is also a valid sample on its own, which is what makes a partial store useful.
//
// The index is the **source of truth** for a replay: σ, beams, weight names and counts come from it,
// not from the per-event records (11 §4). That is why it is written last, after every shard is closed
// and hashed — a directory without an index is an incomplete store, and says so.

#include <cstdint>
#include <string>
#include <vector>

#include "Core/Types.hh"

namespace Store {

    inline constexpr int kIndexVersion = 1;
    inline constexpr const char* kIndexName = "events.index.json";
    inline constexpr const char* kFormat = "hepmc3-ascii";

    struct Shard {
        std::string file;                    // relative to the store directory
        std::int64_t events = 0;
        std::uintmax_t bytes = 0;
        std::string sha256;
        int worker = 0;
    };

    struct Index {
        int version = kIndexVersion;
        std::string format = kFormat;
        std::string compression = "gz";
        std::string point;
        std::string hash;                    // the generation's identity (03 §5)
        std::string provenance = "../provenance.json";
        std::string tool = "pythia";
        std::string tool_version;
        Core::Beams beams;
        int threads = 0;
        std::vector<std::int64_t> seeds;
        std::vector<std::string> weights{"Weight"};
        double xsec_pb = 0.0;
        double xsec_err_pb = 0.0;
        std::int64_t events = 0;             // must equal the sum over shards
        bool stopped = false;                // a partial store; replay is allowed and marked partial
        std::vector<Shard> shards;

        std::int64_t shardEvents() const {
            std::int64_t total = 0;
            for (const Shard& shard : shards) total += shard.events;
            return total;
        }

        bool consistent() const { return shardEvents() == events; }
    };

}  // namespace Store
