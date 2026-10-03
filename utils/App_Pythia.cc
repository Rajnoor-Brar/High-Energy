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
// The σ combination (L1), the stamping (L2, L28), the seed check (L4) and the chunking (L6) are
// utils/PythiaRun.hh's, shared with the integrated programs (V63).
// The output is opened only after init() succeeds, so a card that fails leaves no half-open FIFO.
// Callbacks run concurrently (processAsync = on): each instance converts with its own converter,
// σ is combined under one small lock, and each output has its own writer and lock, so formatting
// the HepMC text (28 kB an event) is shared among the outputs rather than done by one thread. One
// writer holding one lock capped this app at ~2,200 events/s whatever its thread count (measured
// 2026-09-29: 4 threads 17.7 s, 20 threads 20.5 s for 40k events).
// Exit codes: utils/Kit.hh's one table (V73): 0 ok, 1 its card, 2 usage, 3 init, 5 output, 6 stopped,
// 70 internal.

#define HEPMC3_USE_COMPRESSION 1
#define HEPMC3_Z_SUPPORT 1
#define HEPMC3_ZSTD_SUPPORT 1

#include "Kit.hh"
#include "PythiaRun.hh"
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

    using Kit::Ok, Kit::Config, Kit::Usage, Kit::Init, Kit::Output, Kit::Stopped, Kit::Internal;   // V73: Config is its card

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
        const Kit::Args given(argc, argv, {"threads", "events", "seeds", "sidecar"});
        if (!given.ok()) throw std::invalid_argument(given.error());
        if (given.has("threads")) args.threads = std::stoi(given.get("threads"));
        if (given.has("events")) args.events = std::stol(given.get("events"));
        for (const auto& s : split(given.get("seeds"), ',')) args.seeds.push_back(std::stol(s));
        args.sidecar = given.get("sidecar");
        const std::vector<std::string>& positional = given.positional();
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

    // One output: its writer, the lock that serialises it, and how many events it took.
    struct Sink {
        std::string path;
        std::unique_ptr<HepMC3::Writer> writer;
        std::mutex lock;
        std::atomic<long> written{0};
        std::shared_ptr<HepMC3::GenEvent> held;   // under lock: written when the next one comes (L2)
    };
    // What one event goes to: every group, and one member of each (a copy output is a group of one).
    struct Group {
        std::vector<Sink*> members;
        std::atomic<unsigned long> next{0};
    };

    // {"<path>": <events>, …}: what the count check of each consumer compares with (a shard takes a share)
    Kit::Json::Object perOutput(const std::vector<std::unique_ptr<Sink>>& sinks) {
        Kit::Json::Object out;
        for (const auto& sink : sinks) out.add(sink->path, sink->written.load());
        return out;
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
            return Config;
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

    const int threads = PythiaRun::threads(pythia.settings);
    const std::vector<int> seeds = pythia.settings.mvec("Parallelism:seeds");
    if (const std::string wrong = PythiaRun::checkSeeds(pythia.settings, threads); !wrong.empty()) {   // L4
        status.log("error", wrong);
        return Config;
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
    PythiaRun::Stamper stamper;                                 // numbering, run info, σ (L1, L2, L28)
    std::mutex failLock;
    std::exception_ptr failure;                                 // under failLock
    std::atomic<bool> failed{false};
    std::atomic<long> written{0}, writeFailures{0};

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
            stamper.stamp(*instance, *event);
            for (auto& group : groups) deliver(*group, event);
            ++written;
        } catch (...) {
            std::lock_guard<std::mutex> guard(failLock);
            if (!failure) failure = std::current_exception();
            failed = true;
        }
    };

    status.phase("generating", std::to_string(requested) + " events");
    const long chunk = PythiaRun::chunk(threads);  // L6
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
        const PythiaRun::Xsec running = stamper.running();
        status.xsec(running.pb, running.errPb, false);
    }
    // Every output's held event: stamped with the latest σ (unless it is that event), then written (L2).
    const PythiaRun::Stamp last = stamper.last();
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
    std::vector<Pythia8::Pythia*> instances;
    long accepted = 0;
    double sumW = 0;
    pythia.foreach([&](Pythia8::Pythia* instance) {
        instances.push_back(instance);
        accepted += instance->info.nAccepted();
        sumW += instance->info.weightSum();
    });
    const PythiaRun::Xsec xs = PythiaRun::final(instances);
    pythia.stat();

    const bool stopped = stopRequested.load();
    Kit::Json::Object()
        .add("tool", "App_Pythia")
        .raw("pythia_version", Kit::Json::number(PYTHIA_VERSION, 12))
        .add("requested", requested).add("attempted", attempted).add("accepted", accepted)
        .add("written", written.load()).add("write_failures", writeFailures.load())
        .add("sigma_pb", xs.pb).add("sigma_err_pb", xs.errPb).add("sum_w", sumW)
        .add("threads", threads).numbers("seeds", seeds).add("random_seed", pythia.settings.mode("Random:seed"))
        .add("outputs", args.outputs).add("written_per_output", perOutput(sinks)).add("cards", args.cards)
        .add("stopped", stopped)
        .write(args.sidecar);

    status.xsec(xs.pb, xs.errPb, true);
    status.progress(written, requested, rate(), true);
    status.summary(Kit::Json::Object().add("written", written.load()).add("attempted", attempted).add("accepted", accepted)
                       .add("sidecar", args.sidecar).add("outputs", args.outputs).fields());

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
