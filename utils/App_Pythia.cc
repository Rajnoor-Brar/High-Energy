// utils/App_Pythia.cc — the standard Pythia tool (docs/05_Tools_Reference.md §15).
// requires: pythia8 hepmc3 zstd zlib
//
//     App_Pythia.exe [--threads N] [--events N] [--seeds S1,S2,…] [--sidecar FILE]
//                    OUTPUT[,OUTPUT…] CARD [CARD…]
//
// Reads the cards in order (the runner's point card last, so its settings win) and writes HepMC3
// to every OUTPUT: a file, a FIFO, or a .gz/.zst file. It then writes a sidecar,
// <first OUTPUT>.json by default, holding what a consumer needs to check it got everything:
// requested, attempted, accepted and written counts, and the combined cross-section.
//
// What it must get right, each learned by v1 (ledger, docs/07_Record.md §3):
//   L1  PythiaParallel exposes σ per instance and no error for the run. The combination is the
//       ΣW-weighted mean, with errors in quadrature.
//   L2  A CLI Rivet normalises to the σ in the LAST event it reads, and the converter stamps each
//       event with its own instance's running σ. So once more than one instance has contributed,
//       every event is re-stamped with the combination; the last one then carries the final σ.
//       With one instance the converter's own numbers are left untouched: bit for bit the legacy
//       pipeline's.
//   L3  The callback runs on worker threads even with processAsync = off, so nothing may escape
//       it. An exception is caught there and re-raised on the main thread.
//   L4  Parallelism:seeds must have one seed per thread, each in 1…9e8. Pythia does not check.
//   L5  Main:numberOfEvents counts attempts, and failed events never reach the callback, so
//       "written" can be less than "requested". The sidecar says which.
//   L6  run() is called in chunks that are a multiple of the thread count, so SIGINT takes effect
//       within a chunk.
//   L25 zstd for kept event files.
// The output is opened only after init() succeeds, so a card that fails leaves no half-open FIFO.
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
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
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
        std::vector<std::string> outputs;
        std::vector<std::string> cards;
    };

    const char* usage =
        "usage: App_Pythia.exe [--threads N] [--events N] [--seeds S1,S2,…] [--sidecar FILE]\n"
        "                      OUTPUT[,OUTPUT…] CARD [CARD…]\n";

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
        args.outputs = split(positional[0], ',');
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

    std::string jsonList(const std::vector<std::string>& items) {
        std::string out = "[";
        for (size_t i = 0; i < items.size(); ++i) out += (i ? ", " : "") + Status::quote(items[i]);
        return out + "]";
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
    pythia.readString("Parallelism:processAsync = off");

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
    std::vector<std::unique_ptr<HepMC3::Writer>> writers;
    for (const auto& output : args.outputs) {
        writers.push_back(openWriter(output));
        if (writers.back()->failed()) {
            if (stopRequested) {
                status.log("warn", "stopped while waiting to open " + output + " (a FIFO with no reader yet)");
                return Stopped;
            }
            status.log("error", "could not open output " + output);
            return Output;
        }
    }

    // ── generate ───────────────────────────────────────────────────────────────────────────────
    Pythia8::Pythia8ToHepMC converter;  // no writer of its own: one conversion, every output
    std::map<const Pythia8::Pythia*, Instance> latest;
    std::exception_ptr failure;
    std::atomic<long> written{0};
    long writeFailures = 0;

    auto onEvent = [&](Pythia8::Pythia* instance) {
        if (failure || stopRequested) return;
        try {  // L3: nothing may leave the callback
            if (!converter.fillNextEvent(*instance)) {
                ++writeFailures;
                return;
            }
            HepMC3::GenEvent& event = converter.event();
            latest[instance] = {instance->info.weightSum(), instance->info.sigmaGen(), instance->info.sigmaErr()};
            if (latest.size() > 1) {  // L2: re-stamp with the combination
                const Xsec xs = combine(latest);
                event.cross_section()->set_cross_section(xs.pb, xs.errPb);
            }
            for (auto& writer : writers) {
                writer->write_event(event);
                if (writer->failed()) ++writeFailures;
            }
            ++written;
        } catch (...) {
            failure = std::current_exception();
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
    while (attempted < requested && !stopRequested && !failure && writeFailures == 0) {
        const long n = std::min(chunk, requested - attempted);
        for (long count : pythia.run(n, onEvent)) attempted += count;
        status.progress(written, requested, rate());
        const Xsec running = combine(latest);
        status.xsec(running.pb, running.errPb, false);
    }
    for (auto& writer : writers) writer->close();

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
         << "  \"write_failures\": " << writeFailures << ",\n"
         << "  \"sigma_pb\": " << xs.pb << ",\n"
         << "  \"sigma_err_pb\": " << xs.errPb << ",\n"
         << "  \"sum_w\": " << sumW << ",\n"
         << "  \"threads\": " << threads << ",\n"
         << "  \"seeds\": " << jsonNumbers(seeds) << ",\n"
         << "  \"random_seed\": " << pythia.settings.mode("Random:seed") << ",\n"
         << "  \"outputs\": " << jsonList(args.outputs) << ",\n"
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
        status.log("error", std::to_string(writeFailures) + " event(s) could not be converted or written");
        return Output;
    }
    return stopped ? Stopped : Ok;
}
