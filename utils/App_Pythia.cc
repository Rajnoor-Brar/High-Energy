// utils/App_Pythia.cc — the standard Pythia tool (docs/05_Tools_Reference.md §15).
// requires: pythia8 hepmc3 zstd zlib
//
//     App_Pythia.exe [--threads N] [--events N] [--seeds S1,S2,…] [--sidecar FILE]
//                    OUTPUT[,OUTPUT…] CARD [CARD…]
//
// Reads the cards in order (the runner's point card last, so its settings win) and writes HepMC3
// to every OUTPUT: a file, a FIFO, or a .gz/.zst file. Every comma-separated OUTPUT gets every
// event (fan-out, V16). An OUTPUT written `A+B+C` is a **deal group**: each event goes to one of its
// members, the first that is free, so K consumers each analyse a share of the events (a sharded
// Rivet, V31). It then writes a sidecar, <first output>.json by default, holding what a consumer
// needs to check it got everything: requested, attempted, accepted and written counts, the count
// per output, and the combined cross-section.
//
// What it must get right, each learned by v1 (ledger, docs/07_Record.md §3):
//   L1  PythiaParallel exposes σ per instance and no error for the run. The combination is the
//       ΣW-weighted mean, with errors in quadrature.
//   L2  A CLI Rivet normalises to the σ in the LAST event it reads, and the converter stamps each
//       event with its own instance's running σ. So once more than one instance has contributed,
//       every event is re-stamped with the combination; the last one then carries the final σ.
//       With one instance the converter's own numbers are left untouched: bit for bit the legacy
//       pipeline's. With callbacks in parallel and several outputs, "the last event" is per output:
//       each output writes its events one late, and at the end its held event takes the σ of the
//       last event stamped. So every shard of a dealt group ends on the same σ, the one a single
//       Rivet would have read, and rivet-merge -e keeps it (a shard ending on an older running σ
//       was 2e-4 off at 4,000 events, L28).
//   L3  The callback runs on worker threads, so nothing may escape it. An exception is caught
//       there and re-raised on the main thread.
//   L4  Parallelism:seeds must have one seed per thread, each in 1…9e8. Pythia does not check.
//   L5  Main:numberOfEvents counts attempts, and failed events never reach the callback, so
//       "written" can be less than "requested". The sidecar says which.
//   L6  run() is called in chunks that are a multiple of the thread count, so SIGINT takes effect
//       within a chunk.
//   L25 zstd for kept event files.
// The output is opened only after init() succeeds, so a card that fails leaves no half-open FIFO.
// Callbacks run concurrently (processAsync = on): each instance converts with its own converter,
// σ is combined under one small lock, and each output has its own writer and lock, so formatting
// the HepMC text (28 kB an event) is shared among the outputs rather than done by one thread. One
// writer holding one lock capped this app at ~2,200 events/s whatever its thread count (measured
// 2026-09-29: 4 threads 17.7 s, 20 threads 20.5 s for 40k events).
// Exit codes (02 §11): 0 ok, 1 card/config, 2 usage, 3 init, 5 output, 6 stopped, 70 internal.

#define HEPMC3_USE_COMPRESSION 1
#define HEPMC3_Z_SUPPORT 1
#define HEPMC3_ZSTD_SUPPORT 1

#include "Status.hh"

#include "HepMC3/WriterAscii.h"
#include "HepMC3/WriterGZ.h"
#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"
#include "Pythia8Plugins/HepMC3.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <exception>
#include <fstream>
#include <map>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {

    enum Exit { Ok = 0, Card = 1, Usage = 2, Init = 3, Output = 5, Stopped = 6, Internal = 70 };

    // ── signals: the first stops within a chunk, the second is the default (it kills) ──────────
    std::atomic<bool> stopRequested{false};
    extern "C" void onSignal(int signal) {
        stopRequested = true;
        struct sigaction restore {};
        restore.sa_handler = SIG_DFL;
        sigaction(signal, &restore, nullptr);
    }
    void installSignals() {
        struct sigaction action {};
        action.sa_handler = onSignal;
        sigemptyset(&action.sa_mask);
        action.sa_flags = 0;  // no SA_RESTART: a blocked FIFO open() returns EINTR and we can leave
        sigaction(SIGINT, &action, nullptr);
        sigaction(SIGTERM, &action, nullptr);
    }

    // ── arguments ──────────────────────────────────────────────────────────────────────────────
    struct Args {
        int threads = -1;
        long events = -1;
        std::vector<long> seeds;
        std::string sidecar;
        std::vector<std::vector<std::string>> groups;   // OUTPUT[,OUTPUT…]; a member list per OUTPUT
        std::vector<std::string> outputs;               // every path, in order
        std::vector<std::string> cards;
    };

    const char* usage =
        "usage: App_Pythia.exe [--threads N] [--events N] [--seeds S1,S2,…] [--sidecar FILE]\n"
        "                      OUTPUT[,OUTPUT…] CARD [CARD…]      (an OUTPUT A+B+C deals its events among A, B, C)\n";

    std::vector<std::string> split(const std::string& text, char by) {
        std::vector<std::string> parts;
        std::stringstream stream(text);
        for (std::string part; std::getline(stream, part, by);)
            if (!part.empty()) parts.push_back(part);
        return parts;
    }

    Args parse(int argc, char** argv) {
        Args args;
        std::vector<std::string> positional;
        for (int i = 1; i < argc; ++i) {
            const std::string arg = argv[i];
            auto value = [&]() -> std::string {
                if (i + 1 >= argc) throw std::invalid_argument(arg + " needs a value");
                return argv[++i];
            };
            if (arg == "--threads") args.threads = std::stoi(value());
            else if (arg == "--events") args.events = std::stol(value());
            else if (arg == "--seeds") for (const auto& s : split(value(), ',')) args.seeds.push_back(std::stol(s));
            else if (arg == "--sidecar") args.sidecar = value();
            else if (arg == "-h" || arg == "--help") throw std::invalid_argument("");
            else if (arg.rfind("--", 0) == 0) throw std::invalid_argument("unknown option " + arg);
            else positional.push_back(arg);
        }
        if (positional.size() < 2) throw std::invalid_argument("need OUTPUT and at least one CARD");
        for (const auto& item : split(positional[0], ',')) {
            args.groups.push_back(split(item, '+'));
            if (args.groups.back().empty()) throw std::invalid_argument("an empty OUTPUT in " + positional[0]);
            for (const auto& path : args.groups.back()) args.outputs.push_back(path);
        }
        if (args.outputs.empty()) throw std::invalid_argument("no OUTPUT");
        args.cards.assign(positional.begin() + 1, positional.end());
        if (args.sidecar.empty()) args.sidecar = args.outputs.front() + ".json";
        return args;
    }

    // ── σ over instances (L1) ──────────────────────────────────────────────────────────────────
    struct Instance {
        double weightSum = 0, sigmaMb = 0, errorMb = 0;
    };
    struct Xsec {
        double pb = 0, errPb = 0;
    };
    Xsec combine(const std::map<const Pythia8::Pythia*, Instance>& instances) {
        double weight = 0, value = 0, variance = 0;
        for (const auto& [_, in] : instances) {
            if (in.weightSum <= 0) continue;  // an instance that generated nothing says nothing
            weight += in.weightSum;
            value += in.weightSum * in.sigmaMb;
            variance += std::pow(in.weightSum * in.errorMb, 2);
        }
        if (weight <= 0) return {};
        return {value / weight * 1e9, std::sqrt(variance) / weight * 1e9};  // mb → pb
    }

    // ── output ─────────────────────────────────────────────────────────────────────────────────
    bool endsWith(const std::string& text, const std::string& tail) {
        return text.size() >= tail.size() && text.compare(text.size() - tail.size(), tail.size(), tail) == 0;
    }
    // As the legacy pipeline did (Pythia8ToHepMC::setNewFile): no run info at construction; the
    // writer takes it from the first event.
    std::unique_ptr<HepMC3::Writer> openWriter(const std::string& path) {
        if (endsWith(path, ".gz"))
            return std::make_unique<HepMC3::WriterGZ<HepMC3::WriterAscii, HepMC3::Compression::z>>(path);
        if (endsWith(path, ".zst"))
            return std::make_unique<HepMC3::WriterGZ<HepMC3::WriterAscii, HepMC3::Compression::zstd>>(path);
        return std::make_unique<HepMC3::WriterAscii>(path);
    }

    void writeSidecar(const std::string& path, const std::string& json) {
        const std::string partial = path + ".part";
        {
            std::ofstream out(partial);
            out << json;
        }
        std::rename(partial.c_str(), path.c_str());
    }

    // One output: its writer, the lock that serialises it, and how many events it took.
    struct Sink {
        std::string path;
        std::unique_ptr<HepMC3::Writer> writer;
        std::mutex lock;
        std::atomic<long> written{0};
        std::shared_ptr<HepMC3::GenEvent> held;   // under lock: written when the next one comes (L2)
    };
    // The σ an event was stamped with, as the converter or the re-stamp left it.
    struct Stamp {
        std::vector<double> xs, err;
        long accepted = -1, attempted = -1;
    };
    // What one event goes to: every group, and one member of each (a copy output is a group of one).
    struct Group {
        std::vector<Sink*> members;
        std::atomic<unsigned long> next{0};
    };

    std::string jsonList(const std::vector<std::string>& items) {
        std::string out = "[";
        for (size_t i = 0; i < items.size(); ++i) out += (i ? ", " : "") + Status::quote(items[i]);
        return out + "]";
    }
    // {"<path>": <events>, …}: what the count check of each consumer compares with (a shard takes a share)
    std::string perOutput(const std::vector<std::unique_ptr<Sink>>& sinks) {
        std::string out = "{";
        for (size_t i = 0; i < sinks.size(); ++i)
            out += (i ? ", " : "") + Status::quote(sinks[i]->path) + ": " + std::to_string(sinks[i]->written.load());
        return out + "}";
    }

    template <class T>
    std::string jsonNumbers(const std::vector<T>& items) {
        std::string out = "[";
        for (size_t i = 0; i < items.size(); ++i) out += (i ? ", " : "") + std::to_string(items[i]);
        return out + "]";
    }

}  // namespace

int main(int argc, char** argv) {
    Args args;
    try {
        args = parse(argc, argv);
    } catch (const std::exception& error) {
        if (*error.what()) std::fprintf(stderr, "App_Pythia: %s\n", error.what());
        std::fputs(usage, stderr);
        return Usage;
    }

    Status::Reporter status;
    installSignals();

    // ── configure ──────────────────────────────────────────────────────────────────────────────
    Pythia8::PythiaParallel pythia;
    pythia.readString("Print:quiet = on");
    for (const auto& card : args.cards) {
        if (!pythia.readFile(card)) {
            status.log("error", "could not read card " + card + " (missing file or rejected setting)");
            return Card;
        }
    }
    if (args.threads >= 0) pythia.readString("Parallelism:numThreads = " + std::to_string(args.threads));
    if (args.events >= 0) pythia.readString("Main:numberOfEvents = " + std::to_string(args.events));
    if (!args.seeds.empty()) {
        std::string list;
        for (long seed : args.seeds) list += (list.empty() ? "" : ",") + std::to_string(seed);
        pythia.readString("Parallelism:seeds = {" + list + "}");
    }
    pythia.readString("Parallelism:processAsync = on");     // callbacks in parallel: see the header

    int threads = pythia.settings.mode("Parallelism:numThreads");
    if (threads <= 0) threads = std::max(1u, std::thread::hardware_concurrency());
    const std::vector<int> seeds = pythia.settings.mvec("Parallelism:seeds");
    if (!seeds.empty()) {  // L4: Pythia does not check either of these
        if (static_cast<int>(seeds.size()) != threads) {
            status.log("error", "Parallelism:seeds has " + std::to_string(seeds.size()) + " seeds for " +
                                    std::to_string(threads) + " threads; it needs one per thread");
            return Card;
        }
        for (int seed : seeds)
            if (seed < 1 || seed > 900000000) {
                status.log("error", "seed " + std::to_string(seed) + " is outside Pythia's range 1…900000000");
                return Card;
            }
    }
    const long requested = pythia.settings.mode("Main:numberOfEvents");

    status.phase("init", std::to_string(threads) + " threads");
    if (!pythia.init()) {
        status.log("error", "Pythia initialisation failed (see the log)");
        return Init;
    }

    // ── outputs, opened only now (a FIFO blocks here until its reader opens it) ────────────────
    std::vector<std::unique_ptr<Sink>> sinks;
    std::vector<std::unique_ptr<Group>> groups;
    for (const auto& members : args.groups) {
        groups.push_back(std::make_unique<Group>());
        for (const auto& output : members) {
            sinks.push_back(std::make_unique<Sink>());
            sinks.back()->path = output;
            sinks.back()->writer = openWriter(output);
            if (sinks.back()->writer->failed()) {
                if (stopRequested) {
                    status.log("warn", "stopped while waiting to open " + output + " (a FIFO with no reader yet)");
                    return Stopped;
                }
                status.log("error", "could not open output " + output);
                return Output;
            }
            groups.back()->members.push_back(sinks.back().get());
        }
    }

    // ── generate ───────────────────────────────────────────────────────────────────────────────
    // A converter per instance (each callback runs on its instance's thread); read-only map from here.
    std::map<const Pythia8::Pythia*, std::unique_ptr<Pythia8::Pythia8ToHepMC>> converters;
    pythia.foreach([&](Pythia8::Pythia* instance) { converters[instance] = std::make_unique<Pythia8::Pythia8ToHepMC>(); });
    std::map<const Pythia8::Pythia*, Instance> latest;          // under xsLock
    std::shared_ptr<HepMC3::GenRunInfo> runInfo;                // under xsLock: one for every event
    Stamp last;                                                 // under xsLock: the latest event's σ
    std::mutex xsLock, failLock;
    std::exception_ptr failure;                                 // under failLock
    std::atomic<bool> failed{false};
    std::atomic<long> written{0}, writeFailures{0}, numbered{0};

    // One event to one sink of a group: a copy output's only member, or the first free member of a
    // deal group (starting from a rotating index, so an even load deals round-robin).
    auto write = [&](Sink& sink, const HepMC3::GenEvent& event) {   // under sink.lock
        sink.writer->write_event(event);
        if (sink.writer->failed()) ++writeFailures;
        else ++sink.written;
    };
    auto deliver = [&](Group& group, std::shared_ptr<HepMC3::GenEvent> event) {
        Sink* sink = nullptr;
        const size_t k = group.members.size(), start = k > 1 ? group.next++ % k : 0;
        for (size_t j = 0; j < k && !sink; ++j)
            if (group.members[(start + j) % k]->lock.try_lock()) sink = group.members[(start + j) % k];
        if (!sink) {
            sink = group.members[start];
            sink->lock.lock();
        }
        std::lock_guard<std::mutex> guard(sink->lock, std::adopt_lock);
        std::swap(sink->held, event);
        if (event) write(*sink, *event);
    };

    auto onEvent = [&](Pythia8::Pythia* instance) {
        if (failed || stopRequested) return;
        try {  // L3: nothing may leave the callback
            Pythia8::Pythia8ToHepMC& converter = *converters.at(instance);
            if (!converter.fillNextEvent(*instance)) {
                ++writeFailures;
                return;
            }
            const std::shared_ptr<HepMC3::GenEvent> event = converter.getEventPtr();   // a new one each event
            event->set_event_number(static_cast<int>(numbered++));  // one numbering across instances, from 0
            {
                std::lock_guard<std::mutex> guard(xsLock);
                if (!runInfo) runInfo = event->run_info();
                latest[instance] = {instance->info.weightSum(), instance->info.sigmaGen(), instance->info.sigmaErr()};
                const auto cs = event->cross_section();
                if (cs && latest.size() > 1) {                        // L2: re-stamp with the combination
                    const Xsec xs = combine(latest);
                    cs->set_cross_section(xs.pb, xs.errPb);
                }
                if (cs) last = {cs->xsecs(), cs->xsec_errs(), cs->get_accepted_events(), cs->get_attempted_events()};
            }
            event->set_run_info(runInfo);                              // one run info: no per-event warning
            for (auto& group : groups) deliver(*group, event);
            ++written;
        } catch (...) {
            std::lock_guard<std::mutex> guard(failLock);
            if (!failure) failure = std::current_exception();
            failed = true;
        }
    };

    status.phase("generating", std::to_string(requested) + " events");
    const long chunk = 100L * threads;  // a multiple of the thread count (L6)
    long attempted = 0;
    const auto start = std::chrono::steady_clock::now();
    auto rate = [&] {
        const double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        return s > 0 ? written / s : 0.0;
    };
    status.progress(0, requested, 0.0, true);
    while (attempted < requested && !stopRequested && !failed && writeFailures == 0) {
        const long n = std::min(chunk, requested - attempted);
        for (long count : pythia.run(n, onEvent)) attempted += count;       // every callback has returned
        status.progress(written, requested, rate());
        const Xsec running = combine(latest);
        status.xsec(running.pb, running.errPb, false);
    }
    // Every output's held event: stamped with the latest σ (unless it is that event), then written (L2).
    for (auto& sink : sinks) {
        if (!sink->held) continue;
        const auto cs = sink->held->cross_section();
        if (cs && !last.xs.empty() && (cs->xsecs() != last.xs || cs->xsec_errs() != last.err))
            cs->set_cross_section(last.xs, last.err, last.accepted, last.attempted);
        write(*sink, *sink->held);
        sink->held.reset();
    }
    for (auto& sink : sinks) sink->writer->close();

    // ── account ────────────────────────────────────────────────────────────────────────────────
    std::map<const Pythia8::Pythia*, Instance> final;
    long accepted = 0;
    pythia.foreach([&](Pythia8::Pythia* instance) {
        final[instance] = {instance->info.weightSum(), instance->info.sigmaGen(), instance->info.sigmaErr()};
        accepted += instance->info.nAccepted();
    });
    const Xsec xs = final.size() == 1 ? Xsec{final.begin()->second.sigmaMb * 1e9, final.begin()->second.errorMb * 1e9}
                                      : combine(final);
    double sumW = 0;
    for (const auto& [_, in] : final) sumW += in.weightSum;
    pythia.stat();

    const bool stopped = stopRequested.load();
    std::ostringstream json;
    json.precision(12);
    json << "{\n"
         << "  \"tool\": \"App_Pythia\",\n"
         << "  \"pythia_version\": " << PYTHIA_VERSION << ",\n"
         << "  \"requested\": " << requested << ",\n"
         << "  \"attempted\": " << attempted << ",\n"
         << "  \"accepted\": " << accepted << ",\n"
         << "  \"written\": " << written.load() << ",\n"
         << "  \"write_failures\": " << writeFailures.load() << ",\n"
         << "  \"sigma_pb\": " << xs.pb << ",\n"
         << "  \"sigma_err_pb\": " << xs.errPb << ",\n"
         << "  \"sum_w\": " << sumW << ",\n"
         << "  \"threads\": " << threads << ",\n"
         << "  \"seeds\": " << jsonNumbers(seeds) << ",\n"
         << "  \"random_seed\": " << pythia.settings.mode("Random:seed") << ",\n"
         << "  \"outputs\": " << jsonList(args.outputs) << ",\n"
         << "  \"written_per_output\": " << perOutput(sinks) << ",\n"
         << "  \"cards\": " << jsonList(args.cards) << ",\n"
         << "  \"stopped\": " << (stopped ? "true" : "false") << "\n"
         << "}\n";
    writeSidecar(args.sidecar, json.str());

    status.xsec(xs.pb, xs.errPb, true);
    status.progress(written, requested, rate(), true);
    status.summary("\"written\": " + std::to_string(written.load()) + ", \"attempted\": " + std::to_string(attempted) +
                   ", \"accepted\": " + std::to_string(accepted) + ", \"sidecar\": " + Status::quote(args.sidecar) +
                   ", \"outputs\": " + jsonList(args.outputs));

    if (failure) {
        try {
            std::rethrow_exception(failure);
        } catch (const std::exception& error) {
            status.log("error", std::string("in the event callback: ") + error.what());
        } catch (...) {
            status.log("error", "in the event callback: unknown exception");
        }
        return Internal;
    }
    if (writeFailures) {
        status.log("error", std::to_string(writeFailures.load()) + " event(s) could not be converted or written");
        return Output;
    }
    return stopped ? Stopped : Ok;
}
