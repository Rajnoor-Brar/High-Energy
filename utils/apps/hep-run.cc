// hep-run — the C++ half of the toolkit: one resolved spec in, events through sinks, status out.
//
// P2-S01 builds this as a stub: it reports what the build can do (`--capabilities`, which `hep doctor`
// and `hep plan` read) and refuses anything else with the step that will implement it. The source, the
// sinks and the run loop arrive in P2-S04 and P2-S05.
//
// Exit codes (06 §3.3): 0 success, 1 card or spec error, 2 usage, 3 initialisation failure,
// 6 interrupted. A stub returns 3 for "not implemented yet", because nothing was initialised.

#include <cstring>
#include <iostream>
#include <string>
#include <vector>

namespace {

// The components this binary was built with; hep doctor reports them and hep plan checks against them.
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

void print_capabilities() {
  std::cout << "{\n  \"version\": \"" << HEKIT_VERSION << "\",\n"
            << "  \"spec_schema\": 2,\n"
            << "  \"build\": \"" << HEKIT_BUILD_TYPE << "\",\n"
            << "  \"built\": \"" << __DATE__ << "\",\n"
            << "  \"compression\": \"" << HEKIT_COMPRESSION << "\",\n"
            << "  \"components\": [";
  const std::vector<std::string> found = components();
  for (std::size_t index = 0; index < found.size(); ++index)
    std::cout << (index ? ", " : "") << '"' << found[index] << '"';
  std::cout << "]\n}\n";
}

void print_usage(std::ostream& out) {
  out << "Usage: hep-run SPEC.toml [--check] [--plain] [--list N]\n"
      << "       hep-run --capabilities | --version\n\n"
      << "SPEC.toml is a resolved spec written by `hep plan` (schema 2).\n";
}

}  // namespace

int main(int argc, char* argv[]) {
  const std::vector<std::string> arguments(argv + 1, argv + argc);
  if (arguments.empty()) {
    print_usage(std::cerr);
    return 2;
  }
  if (arguments[0] == "--capabilities") {
    print_capabilities();
    return 0;
  }
  if (arguments[0] == "--version") {
    std::cout << "hep-run " << HEKIT_VERSION << " (spec schema 2)\n";
    return 0;
  }
  if (arguments[0] == "--help" || arguments[0] == "-h") {
    print_usage(std::cout);
    return 0;
  }
  if (arguments[0].rfind("--", 0) == 0) {
    std::cerr << "hep-run: unknown option '" << arguments[0] << "'\n";
    print_usage(std::cerr);
    return 2;
  }
  std::cerr << "hep-run: running a spec is not implemented yet; it arrives in step P2-S04\n"
            << "hep-run: this build reports its components with --capabilities\n";
  return 3;
}
