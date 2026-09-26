#pragma once

// ── Store/Writer.hh ──────────────────────────────────────────────────────────
// Writing a sharded, indexed event store (11 §1–3).
//
// The order matters, and it is the whole design:
//
//   1. each worker streams into `events.<k>.hepmc.<codec>.part` — one file per worker, so two
//      workers never contend for the same stream;
//   2. at the end every shard is closed, hashed, and renamed out of `.part`;
//   3. only then is `events.index.json` written, atomically.
//
// So a directory with an index is a store whose shards are all closed and hashed, and a directory
// without one is an unfinished store rather than a silently short one — the same rule as the YODA
// writer (D22, 00/B3), applied to a directory instead of a file.
//
// The index is also the source of truth for a replay (11 §4): σ, beams, weight names and counts come
// from it, which is why it carries them and why a partial store is marked `stopped` rather than
// quietly missing events.
//
// **Under `[run].mode = "sharded"` several threads write at once.** One worker is still one stream,
// but two things are shared and are guarded here rather than in every caller: the shard *map*, which
// grows when a worker first appears, and the total count. The per-shard lock is held only across the
// HepMC3 write, and is uncontended whenever a worker belongs to one thread (which it does for a
// generator); a replay can hand the same source shard to two consumers, and then it is the thing
// that keeps the file from interleaving.

#include <atomic>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "Core/Errors.hh"
#include "Core/Sha256.hh"
#include "Status/Writer.hh"
#include "Store/Compression.hh"
#include "Store/Types.hh"

#if defined(HEKIT_WITH_HEPMC)
#include "HepMC3/GenEvent.h"
#include "HepMC3/GenRunInfo.h"
#include "HepMC3/Writer.h"
#endif

namespace Store {

    inline std::string indexJson(const Index& index) {
        auto quote = [](const std::string& text) { return "\"" + Status::escape(text) + "\""; };
        std::string json = "{\n";
        json += "  \"version\": " + std::to_string(index.version) + ",\n";
        json += "  \"format\": " + quote(index.format) + ",\n";
        json += "  \"compression\": " + quote(index.compression) + ",\n";
        json += "  \"point\": " + quote(index.point) + ",\n";
        json += "  \"hash\": " + quote(index.hash) + ",\n";
        json += "  \"provenance\": " + quote(index.provenance) + ",\n";
        json += "  \"generator\": {\"tool\": " + quote(index.tool) + ", \"version\": " +
                quote(index.tool_version) + "},\n";
        json += "  \"beams\": {\"ids\": " + Status::jsonList(index.beams.ids) +
                ", \"energies\": " + Status::jsonList(index.beams.energies) + "},\n";
        json += "  \"threads\": " + std::to_string(index.threads) + ",\n";
        json += "  \"seeds\": " + Status::jsonList(index.seeds) + ",\n";
        json += "  \"weights\": " + Status::jsonList(index.weights) + ",\n";
        json += "  \"xsec_pb\": " + Status::number(index.xsec_pb) + ",\n";
        json += "  \"xsec_err_pb\": " + Status::number(index.xsec_err_pb) + ",\n";
        json += "  \"events\": " + std::to_string(index.events) + ",\n";
        json += "  \"stopped\": " + std::string(index.stopped ? "true" : "false") + ",\n";
        json += "  \"shards\": [";
        for (std::size_t position = 0; position < index.shards.size(); ++position) {
            const Shard& shard = index.shards[position];
            json += (position ? ",\n" : "\n") + std::string("    {\"file\": ") + quote(shard.file) +
                    ", \"worker\": " + std::to_string(shard.worker) +
                    ", \"events\": " + std::to_string(shard.events) +
                    ", \"bytes\": " + std::to_string(static_cast<std::uint64_t>(shard.bytes)) +
                    ", \"sha256\": " + quote(shard.sha256) + "}";
        }
        json += index.shards.empty() ? "]\n" : "\n  ]\n";
        return json + "}\n";
    }

#if defined(HEKIT_WITH_HEPMC)

    /// One store: shards keyed by worker, an index written last.
    class Writer {
      public:
        Writer(std::string directory, std::string codec)
            : directory_(std::move(directory)), codec_(std::move(codec)) {
            requireCodec(codec_);
            std::error_code code;
            std::filesystem::create_directories(directory_, code);
            if (code)
                throw Core::Error{Core::Exit::Analyzer,
                                  "cannot create the event store directory: " + directory_,
                                  code.message()};
        }

        Writer(const Writer&) = delete;
        Writer& operator=(const Writer&) = delete;
        ~Writer() { closeShards(); }

        /// Write one event into its worker's shard, opening that shard on first use.
        void write(int worker, const HepMC3::GenEvent& event) {
            Open& shard = open(worker);
            {
                const std::lock_guard<std::mutex> guard(shard.lock);
                shard.writer->write_event(const_cast<HepMC3::GenEvent&>(event));
                if (shard.writer->failed())
                    throw Core::Error{Core::Exit::Analyzer,
                                      "writing the event store failed: " + shard.partial,
                                      "a full disk is the usual cause"};
                shard.events += 1;
            }
            events_.fetch_add(1, std::memory_order_relaxed);
        }

        /// Close every shard, hash it, and rename it into place. Safe to call twice.
        std::vector<Shard> closeShards() {
            std::vector<Shard> found;
            for (auto& [worker, shard] : shards_) {
                if (shard.writer != nullptr) {
                    shard.writer->close();
                    shard.writer.reset();
                    const std::string final_path = path(shard.name);
                    std::error_code code;
                    std::filesystem::rename(shard.partial, final_path, code);
                    if (code)
                        throw Core::Error{Core::Exit::Analyzer,
                                          "cannot move the shard into place: " + shard.name,
                                          code.message()};
                    shard.closed = true;
                }
                if (!shard.closed) continue;
                Shard record;
                record.file = shard.name;
                record.worker = worker;
                record.events = shard.events;
                std::error_code code;
                record.bytes = std::filesystem::file_size(path(shard.name), code);
                record.sha256 = Core::sha256File(path(shard.name));
                found.push_back(record);
            }
            return found;
        }

        /// Close the shards and write the index. The store is complete only after this returns.
        Index finish(Index index) {
            index.compression = codec_;
            index.shards = closeShards();
            index.events = index.events ? index.events : events();
            if (!index.consistent())
                throw Core::Error{Core::Exit::Analyzer,
                                  "the event store's shard counts do not add up: " +
                                      std::to_string(index.shardEvents()) + " in shards, " +
                                      std::to_string(index.events) + " recorded",
                                  "this is a bug in the store writer, not in your configuration"};
            writeIndex(index);
            return index;
        }

        void writeIndex(const Index& index) const {
            const std::string target = path(kIndexName);
            const std::string temporary = target + ".part";
            {
                std::ofstream out(temporary, std::ios::binary | std::ios::trunc);
                if (!out)
                    throw Core::Error{Core::Exit::Analyzer, "cannot write " + temporary};
                out << indexJson(index);
                if (!out)
                    throw Core::Error{Core::Exit::Analyzer, "cannot write " + temporary};
            }
            std::error_code code;
            std::filesystem::rename(temporary, target, code);
            if (code) {
                std::filesystem::remove(temporary, code);
                throw Core::Error{Core::Exit::Analyzer, "cannot move the store index into place",
                                  code.message()};
            }
        }

        const std::string& directory() const { return directory_; }
        const std::string& codec() const { return codec_; }
        std::int64_t events() const { return events_.load(std::memory_order_relaxed); }
        std::size_t shardCount() const { return shards_.size(); }

        void setRunInfo(std::shared_ptr<HepMC3::GenRunInfo> run) { run_ = std::move(run); }

      private:
        struct Open {
            std::unique_ptr<HepMC3::Writer> writer;
            std::string name;
            std::string partial;
            std::int64_t events = 0;
            bool closed = false;
            std::mutex lock;                  // held across one write_event, never across a hash
        };

        std::string path(const std::string& name) const {
            return (std::filesystem::path(directory_) / name).string();
        }

        // `std::map` nodes never move, so a reference handed out here stays valid while the map
        // grows; the lock is only around the lookup and the insert.
        Open& open(int worker) {
            const std::lock_guard<std::mutex> guard(shards_lock_);
            auto found = shards_.find(worker);
            if (found != shards_.end()) return found->second;
            Open& shard = shards_[worker];
            shard.name = shardName(worker, codec_);
            shard.partial = path(shard.name) + ".part";
            shard.writer = makeWriter(shard.partial, codec_);
            if (shard.writer->failed())
                throw Core::Error{Core::Exit::Analyzer, "cannot open the shard " + shard.partial};
            if (run_ != nullptr) shard.writer->set_run_info(run_);
            return shard;
        }

        std::string directory_;
        std::string codec_;
        std::map<int, Open> shards_;          // ordered, so the index lists shards by worker
        std::mutex shards_lock_;              // guards the map's shape, not the streams
        std::atomic<std::int64_t> events_{0};
        std::shared_ptr<HepMC3::GenRunInfo> run_;
    };

#endif  // HEKIT_WITH_HEPMC

}  // namespace Store
