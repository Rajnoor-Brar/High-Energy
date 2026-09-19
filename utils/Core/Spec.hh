#pragma once

// ── Core/Spec.hh ─────────────────────────────────────────────────────────────
// The resolved spec, as `hep-run` sees it (03 §7, contract in `hekit/plan/spec_v2.json`).
//
// `hep` has already validated everything that needs judgement — studies, sweeps, `use` indices,
// defaults, capabilities — so this reader only checks **structure**: the tables that must exist, the
// types of their keys, and the invariants `hep-run` itself depends on. That is the whole point of the
// split (00 F2): configuration logic lives in one place, and it is not here.
//
// Two invariants are checked here rather than trusted:
//   * `run.seeds.instances` has exactly `run.threads` entries — Pythia indexes that list without
//     bounds checking, so a short list is undefined behaviour rather than an error (P2-S02, D-SEEDS);
//   * every instance seed is inside Pythia's accepted range 1 … 900000000.

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iterator>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "Core/Errors.hh"

#if defined(HEKIT_HAVE_TOMLPP)
#include <toml++/toml.hpp>
#endif

namespace Core {

    inline constexpr int kSpecSchema = 2;
    inline constexpr std::int64_t kMinSeed = 1;
    inline constexpr std::int64_t kMaxSeed = 900000000;

    /// What `hep` read out of a store's `events.index.json` (11 §2, §4).
    ///
    /// The index is the source of truth for a replay, and `hep` is the side that reads JSON — so it
    /// puts the index's facts into the spec and `hep-run` needs no JSON parser. A hand-written spec
    /// may instead name `[source].inputs` (a stream), where there is no index at all.
    struct StoreSpec {
        std::string directory;
        std::string compression = "zst";
        std::vector<std::string> shards;          // file names, in the index's order
        std::vector<int> workers;                 // the worker each shard came from
        std::int64_t events = 0;                  // what the index promised
        double xsec_pb = 0.0;
        double xsec_err_pb = 0.0;
        std::vector<int> beam_ids;
        std::vector<double> beam_energies;
        std::vector<std::string> weights;
        std::int64_t queue = 0;                   // events in flight; 0 = the source's default
        bool stopped = false;                     // the store is partial, so this replay is too
    };

    struct SinkSpec {
        std::string kind;                       // rivet | module | store | delphes
        std::vector<std::string> analyses;      // rivet
        std::vector<std::string> paths;         // rivet: plugin search path
        std::string xsec = "generator";         // rivet: "generator" or a number as text
        std::string weights = "nominal";
        std::int64_t dump_every = 0;
        bool check_beams = true;
        std::string name;                       // module
        std::string library;                    // module
        std::string dir;                        // store
        std::string compression;                // store
        std::string card;                       // delphes
    };

    struct Spec {
        // [meta]
        std::string point;
        std::string hash;
        std::string origin;
        std::vector<std::string> aliases;
        // [run]
        std::int64_t events = 0;
        std::int64_t seed = 0;
        int threads = 0;
        std::vector<std::int64_t> instance_seeds;
        // [source]
        std::string source_kind;
        std::vector<std::string> cards;
        std::string input;                      // store
        std::vector<std::string> inputs;        // stream
        StoreSpec store;
        // [output]
        std::string output_dir;
        std::string yoda_name = "analysis.yoda";
        std::string summary_name = "run.summary.json";
        // [[sink]]
        std::vector<SinkSpec> sinks;
        // [status]
        int status_fd = 3;
        std::int64_t heartbeat_ms = 500;

        bool wants(const std::string& kind) const {
            return std::any_of(sinks.begin(), sinks.end(),
                               [&](const SinkSpec& sink) { return sink.kind == kind; });
        }
    };

    // What `hep-run` insists on itself, whatever produced the file.
    inline void checkSpec(const Spec& spec) {
        if (spec.point.empty())
            throw Error{Exit::Config, "[meta] point is empty"};
        if (spec.hash.rfind("sha256:", 0) != 0)
            throw Error{Exit::Config, "[meta] hash must be 'sha256:<64 hex>'", "written by `hep plan`"};
        if (spec.source_kind.empty())
            throw Error{Exit::Config, "[source] kind is empty"};
        if (spec.source_kind == "store" && spec.store.shards.empty() && spec.inputs.empty())
            throw Error{Exit::Config, "[source] is a store but names no shards",
                        "`hep run` fills [source.store] from the store's index"};
        if (spec.output_dir.empty())
            throw Error{Exit::Config, "[output] dir is empty"};
        if (spec.threads < 0)
            throw Error{Exit::Config, "[run] threads is negative"};
        if (spec.events < 0)
            throw Error{Exit::Config, "[run] events is negative"};

        // D-SEEDS: Pythia reads seeds[i] for i < numThreads with no bounds check, so a list that is too
        // short is undefined behaviour. Refuse it here, where it is still a message.
        const std::size_t wanted = static_cast<std::size_t>(spec.threads > 0 ? spec.threads : 0);
        if (wanted > 0 && spec.instance_seeds.size() != wanted)
            throw Error{Exit::Config,
                        "[run.seeds] instances has " + std::to_string(spec.instance_seeds.size()) +
                            " entries for " + std::to_string(spec.threads) + " threads",
                        "Pythia indexes this list without checking its length, so it must match exactly"};
        for (std::int64_t seed : spec.instance_seeds)
            if (seed < kMinSeed || seed > kMaxSeed)
                throw Error{Exit::Config,
                            "[run.seeds] instance seed " + std::to_string(seed) + " is outside 1..900000000"};
        if (!spec.instance_seeds.empty() && spec.seed != spec.instance_seeds.front())
            throw Error{Exit::Config, "[run] seed does not match the first instance seed",
                        "the point seed is the base of its block (03 §5)"};

        for (const SinkSpec& sink : spec.sinks) {
            if (sink.kind == "rivet" && sink.analyses.empty())
                throw Error{Exit::Config, "a rivet sink has no analyses"};
            if (sink.kind == "module" && sink.name.empty())
                throw Error{Exit::Config, "a module sink has no name"};
            if (sink.kind == "store" && sink.dir.empty())
                throw Error{Exit::Config, "a store sink has no directory"};
        }
    }

#if defined(HEKIT_HAVE_TOMLPP)

    namespace detail {

        inline const toml::table& requireTable(const toml::table& parent, std::string_view key) {
            const toml::node* node = parent.get(key);
            if (node == nullptr || !node->is_table())
                throw Error{Exit::Config, "the spec has no [" + std::string(key) + "] table",
                            "`hep plan` writes it; see hekit/plan/spec_v2.json"};
            return *node->as_table();
        }

        template <typename T>
        T value(const toml::table& table, std::string_view key, T fallback) {
            const toml::node* node = table.get(key);
            if (node == nullptr) return fallback;
            const std::optional<T> found = node->value<T>();
            if (!found)
                throw Error{Exit::Config, "the spec's '" + std::string(key) + "' has the wrong type"};
            return *found;
        }

        inline std::vector<std::string> strings(const toml::table& table, std::string_view key) {
            std::vector<std::string> found;
            const toml::node* node = table.get(key);
            if (node == nullptr) return found;
            const toml::array* array = node->as_array();
            if (array == nullptr)
                throw Error{Exit::Config, "the spec's '" + std::string(key) + "' must be a list"};
            for (const toml::node& entry : *array) {
                const std::optional<std::string> text = entry.value<std::string>();
                if (!text)
                    throw Error{Exit::Config, "the spec's '" + std::string(key) + "' must hold strings"};
                found.push_back(*text);
            }
            return found;
        }

        inline std::vector<std::int64_t> integers(const toml::table& table, std::string_view key) {
            std::vector<std::int64_t> found;
            const toml::node* node = table.get(key);
            if (node == nullptr) return found;
            const toml::array* array = node->as_array();
            if (array == nullptr)
                throw Error{Exit::Config, "the spec's '" + std::string(key) + "' must be a list"};
            for (const toml::node& entry : *array) {
                const std::optional<std::int64_t> number = entry.value<std::int64_t>();
                if (!number)
                    throw Error{Exit::Config, "the spec's '" + std::string(key) + "' must hold integers"};
                found.push_back(*number);
            }
            return found;
        }

        inline std::string numberOrText(const toml::table& table, std::string_view key,
                                        const std::string& fallback) {
            const toml::node* node = table.get(key);
            if (node == nullptr) return fallback;
            if (const std::optional<std::string> text = node->value<std::string>()) return *text;
            if (const std::optional<double> number = node->value<double>())
                return std::to_string(*number);
            throw Error{Exit::Config, "the spec's '" + std::string(key) + "' must be a string or a number"};
        }

    }  // namespace detail

    // Parse a resolved spec. Throws `Error{Exit::Config}` with the key at fault.
    inline Spec parseSpec(const std::string& text) {
        toml::table document;
        try {
            document = toml::parse(text);
        } catch (const toml::parse_error& error) {
            throw Error{Exit::Config, "the spec is not valid TOML: " + std::string{error.description()}};
        }

        Spec spec;
        const toml::table& meta = detail::requireTable(document, "meta");
        const std::int64_t schema = detail::value<std::int64_t>(meta, "schema", 0);
        if (schema != kSpecSchema)
            throw Error{Exit::Config,
                        "the spec is schema " + std::to_string(schema) + ", this hep-run reads " +
                            std::to_string(kSpecSchema),
                        "rebuild hep-run, or regenerate the spec with a matching hep"};
        spec.point = detail::value<std::string>(meta, "point", "");
        spec.hash = detail::value<std::string>(meta, "hash", "");
        spec.origin = detail::value<std::string>(meta, "origin", "");
        spec.aliases = detail::strings(meta, "aliases");

        const toml::table& run = detail::requireTable(document, "run");
        spec.events = detail::value<std::int64_t>(run, "events", 0);
        spec.seed = detail::value<std::int64_t>(run, "seed", 0);
        spec.threads = static_cast<int>(detail::value<std::int64_t>(run, "threads", 0));
        if (const toml::node* seeds = run.get("seeds")) {
            if (!seeds->is_table())
                throw Error{Exit::Config, "[run.seeds] must be a table"};
            spec.instance_seeds = detail::integers(*seeds->as_table(), "instances");
            spec.seed = detail::value<std::int64_t>(*seeds->as_table(), "point", spec.seed);
        }

        const toml::table& source = detail::requireTable(document, "source");
        spec.source_kind = detail::value<std::string>(source, "kind", "");
        spec.cards = detail::strings(source, "cards");
        spec.input = detail::value<std::string>(source, "input", "");
        spec.inputs = detail::strings(source, "inputs");
        if (const toml::node* store = source.get("store")) {
            if (!store->is_table())
                throw Error{Exit::Config, "[source.store] must be a table"};
            const toml::table& table = *store->as_table();
            spec.store.directory = detail::value<std::string>(table, "dir", spec.input);
            spec.store.compression = detail::value<std::string>(table, "compression", "zst");
            spec.store.shards = detail::strings(table, "shards");
            for (std::int64_t worker : detail::integers(table, "workers"))
                spec.store.workers.push_back(static_cast<int>(worker));
            spec.store.events = detail::value<std::int64_t>(table, "events", 0);
            spec.store.xsec_pb = detail::value<double>(table, "xsec_pb", 0.0);
            spec.store.xsec_err_pb = detail::value<double>(table, "xsec_err_pb", 0.0);
            for (std::int64_t id : detail::integers(table, "beam_ids"))
                spec.store.beam_ids.push_back(static_cast<int>(id));
            if (const toml::node* energies = table.get("beam_energies")) {
                const toml::array* array = energies->as_array();
                if (array == nullptr)
                    throw Error{Exit::Config, "[source.store].beam_energies must be a list"};
                for (const toml::node& entry : *array)
                    spec.store.beam_energies.push_back(entry.value_or(0.0));
            }
            spec.store.weights = detail::strings(table, "weights");
            spec.store.queue = detail::value<std::int64_t>(table, "queue", 0);
            spec.store.stopped = detail::value<bool>(table, "stopped", false);
        }

        const toml::table& output = detail::requireTable(document, "output");
        spec.output_dir = detail::value<std::string>(output, "dir", "");
        spec.yoda_name = detail::value<std::string>(output, "yoda", spec.yoda_name);
        spec.summary_name = detail::value<std::string>(output, "summary", spec.summary_name);

        if (const toml::node* sinks = document.get("sink")) {
            const toml::array* array = sinks->as_array();
            if (array == nullptr)
                throw Error{Exit::Config, "[[sink]] must be an array of tables"};
            for (const toml::node& entry : *array) {
                const toml::table* table = entry.as_table();
                if (table == nullptr)
                    throw Error{Exit::Config, "[[sink]] must be an array of tables"};
                SinkSpec sink;
                sink.kind = detail::value<std::string>(*table, "kind", "");
                if (sink.kind.empty()) throw Error{Exit::Config, "a sink has no kind"};
                sink.analyses = detail::strings(*table, "analyses");
                sink.paths = detail::strings(*table, "paths");
                sink.xsec = detail::numberOrText(*table, "xsec", sink.xsec);
                sink.weights = detail::value<std::string>(*table, "weights", sink.weights);
                sink.dump_every = detail::value<std::int64_t>(*table, "dump_every", 0);
                sink.check_beams = detail::value<bool>(*table, "check_beams", true);
                sink.name = detail::value<std::string>(*table, "name", "");
                sink.library = detail::value<std::string>(*table, "library", "");
                sink.dir = detail::value<std::string>(*table, "dir", "");
                sink.compression = detail::value<std::string>(*table, "compression", "");
                sink.card = detail::value<std::string>(*table, "card", "");
                spec.sinks.push_back(std::move(sink));
            }
        }

        if (const toml::node* status = document.get("status")) {
            if (!status->is_table()) throw Error{Exit::Config, "[status] must be a table"};
            spec.status_fd = static_cast<int>(detail::value<std::int64_t>(*status->as_table(), "fd", 3));
            spec.heartbeat_ms = detail::value<std::int64_t>(*status->as_table(), "heartbeat_ms", 500);
        }

        checkSpec(spec);
        return spec;
    }

    // Read a spec from disk. A missing file is a config error, not an I/O crash.
    inline Spec parseSpecFile(const std::string& path) {
        std::ifstream in(path, std::ios::binary);
        if (!in)
            throw Error{Exit::Config, "cannot read the spec: " + path,
                        "`hep run` writes it into the point directory"};
        std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        return parseSpec(text);
    }

#endif  // HEKIT_HAVE_TOMLPP

}  // namespace Core
