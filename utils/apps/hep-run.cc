// hep-run — one resolved spec in, events through sinks, status out (02 §2, 06 §3).
//
// Everything that needs judgement happened in `hep` (Python): studies, sweeps, defaults, seeds, paths.
// This reads a resolved spec, checks its structure, runs the loop and reports. It knows nothing about
// configuration files, and that is the point of the split (00 F2).
//
//   hep-run SPEC.toml              run it
//   hep-run SPEC.toml --check      configure and initialise, generate nothing (exit 0 / 1 / 3)
//   hep-run SPEC.toml --list N     print the first N events as status messages
//   hep-run SPEC.toml --plain      force plain progress on stderr, even with fd 3 open
//   hep-run --capabilities         what this build can do, as JSON (read by hep doctor and hep plan)
//
// Exit codes are the contract of 06 §3.3: 0 ok, 1 spec/card, 2 usage, 3 init, 4 source, 5 sink,
// 6 stopped by a signal (with partial outputs), 7 stalled (the supervisor's), 70 internal.

#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

#include "Core.hh"
#include "Run.hh"
#include "Sink.hh"
#include "Status.hh"

namespace {

std::vector<std::string> components() {
    std::vector<std::string> found;
#if HEKIT_COMPONENT_RIVET
    found.push_back("rivet");
#endif
#if HEKIT_COMPONENT_HEPMC
    found.push_back("hepmc");
#endif
#if HEKIT_COMPONENT_ONNX
    found.push_back("onnx");
#endif
#if HEKIT_COMPONENT_DELPHES
    found.push_back("delphes");
#endif
    return found;
}

void printCapabilities() {
    const std::vector<std::string> found = components();
    std::cout << "{\n  \"version\": \"" << HEKIT_VERSION << "\",\n"
              << "  \"spec_schema\": " << Core::kSpecSchema << ",\n"
              << "  \"build\": \"" << HEKIT_BUILD_TYPE << "\",\n"
              << "  \"built\": \"" << __DATE__ << "\",\n"
              << "  \"compression\": \"" << HEKIT_COMPRESSION << "\",\n"
              << "  \"components\": [";
    for (std::size_t index = 0; index < found.size(); ++index)
        std::cout << (index ? ", " : "") << '"' << found[index] << '"';
    std::cout << "]\n}\n";
}

void printUsage(std::ostream& out) {
    out << "Usage: hep-run SPEC.toml [--check] [--plain] [--list N]\n"
        << "       hep-run --capabilities | --version | --help\n\n"
        << "SPEC.toml is a resolved spec written by `hep plan` (schema " << Core::kSpecSchema << ").\n";
}

struct Options {
    std::string spec;
    bool check = false;
    bool plain = false;
    long long list = 0;
};

// Parsing is strict: an unknown option is a usage error, because a silently ignored flag in a batch
// job is worse than a failure.
Options parseOptions(const std::vector<std::string>& arguments) {
    Options options;
    for (std::size_t index = 0; index < arguments.size(); ++index) {
        const std::string& argument = arguments[index];
        if (argument == "--check") {
            options.check = true;
        } else if (argument == "--plain") {
            options.plain = true;
        } else if (argument == "--list") {
            if (index + 1 >= arguments.size())
                throw Core::Error{Core::Exit::Usage, "--list needs a number of events"};
            options.list = std::atoll(arguments[++index].c_str());
        } else if (argument.rfind("--", 0) == 0) {
            throw Core::Error{Core::Exit::Usage, "unknown option '" + argument + "'"};
        } else if (options.spec.empty()) {
            options.spec = argument;
        } else {
            throw Core::Error{Core::Exit::Usage, "more than one spec given"};
        }
    }
    if (options.spec.empty()) throw Core::Error{Core::Exit::Usage, "no spec given"};
    return options;
}

std::string summaryFields(const Core::Spec& spec, const Run::Result& result) {
    std::string outputs;
    for (const Sink::Output& output : result.outputs)
        outputs += (outputs.empty() ? "" : ",") + std::string("\"") + Status::escape(output.kind) +
                   "\":\"" + Status::escape(output.path) + "\"";
    std::string fields =
        "\"events\":" + std::to_string(result.counts.accepted) +
        ",\"attempted\":" + std::to_string(result.counts.attempted) +
        ",\"stopped\":" + (result.stopped ? "true" : "false") +
        ",\"threads\":" + std::to_string(result.threads) +
        ",\"chunk\":" + std::to_string(result.chunk) +
        ",\"wall_s\":" + Status::number(result.wall_seconds) +
        ",\"seeds\":" + Status::jsonList(result.seeds) +
        ",\"outputs\":{" + outputs + "}";
    if (result.xsec_known)
        fields += ",\"xsec_pb\":" + Status::number(result.xsec_pb) +
                  ",\"err_pb\":" + Status::number(result.xsec_error_pb);
    (void)spec;
    return fields;
}

// `--list N`: one status message per event, with what an eye can use (06 §5). The full tree and the
// hard process come with `hep events` in P5-S03.
void listEvent(Status::Writer& status, Events::View& view, long long limit) {
    if (view.index() >= limit) return;
    Pythia8::Pythia* pythia = view.pythia();
    const int particles = pythia != nullptr ? pythia->event.size() : 0;
    const int code = pythia != nullptr ? pythia->info.code() : 0;
    status.emit(Status::Kind::Event,
                "\"index\":" + std::to_string(view.index()) + ",\"particles\":" +
                    std::to_string(particles) + ",\"process\":" + std::to_string(code) +
                    ",\"weight\":" + Status::number(view.weights().nominal()),
                "event " + std::to_string(view.index()) + ": " + std::to_string(particles) +
                    " particles, process " + std::to_string(code));
}

}  // namespace

int main(int argc, char* argv[]) {
    const std::vector<std::string> arguments(argv + 1, argv + argc);
    if (arguments.empty()) {
        printUsage(std::cerr);
        return Core::code(Core::Exit::Usage);
    }
    if (arguments[0] == "--capabilities") {
        printCapabilities();
        return 0;
    }
    if (arguments[0] == "--version") {
        std::cout << "hep-run " << HEKIT_VERSION << " (spec schema " << Core::kSpecSchema << ")\n";
        return 0;
    }
    if (arguments[0] == "--help" || arguments[0] == "-h") {
        printUsage(std::cout);
        return 0;
    }

    try {
        const Options options = parseOptions(arguments);
        const Core::Spec spec = Core::parseSpecFile(options.spec);

        Status::Writer status(options.plain ? -1 : spec.status_fd,
                             static_cast<double>(spec.heartbeat_ms) / 1000.0);
        Status::Heartbeat heartbeat(status, static_cast<double>(spec.heartbeat_ms) / 1000.0);
        Core::Signals::installGracefulStop();

        Run::Loop loop(spec, status, heartbeat);
        // P2-S05 adds Sink::Rivet here, reading spec.sinks; until then a run counts its events, which
        // is what the generation-only legs of the benchmark and the equivalence gate need.
        auto counter = std::make_unique<Sink::Count>();
        Sink::Count* counted = counter.get();
        loop.add(std::move(counter));
        if (options.list > 0)
            loop.onEvent([&](Events::View& view) { listEvent(status, view, options.list); });

        if (options.check) {
            loop.prepare();
            status.phase("checked", "spec and cards are usable");
            return 0;
        }

        const Run::Result result = loop.run();
        status.summary(summaryFields(spec, result),
                       std::to_string(result.counts.accepted) + " events in " +
                           Core::durationText(result.wall_seconds) +
                           (result.xsec_known
                                ? ", sigma = " + Status::number(result.xsec_pb) + " pb"
                                : "") +
                           (result.stopped ? " (stopped)" : ""));
        (void)counted;
        return Core::code(result.exit);
    } catch (const Core::Error& error) {
        std::cerr << "hep-run: " << error.what() << "\n";
        if (error.exit() == Core::Exit::Usage) printUsage(std::cerr);
        return Core::code(error.exit());
    } catch (const std::exception& error) {
        // Anything uncaught is a bug in us, not in the user's configuration.
        std::cerr << "hep-run: internal error: " << error.what() << "\n"
                  << "hep-run: please report this with the spec that caused it\n";
        return Core::code(Core::Exit::Internal);
    }
}
