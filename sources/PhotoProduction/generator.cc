// GenerateHepMC.cc
//
// Generate Pythia8 events from a .cmnd file and write them to a single
// merged HepMC3 ASCII file for Rivet analysis. Event generation runs in
// parallel across threads via Pythia8::PythiaParallel; only the
// HepMC3 conversion+write is serialized (cheap relative to generation),
// so the result is one .hepmc file rather than one-per-thread.
//
// (Note: Pythia's own HepMC3Hooks plugin also integrates with
// PythiaParallel, but per the manual it cannot merge threads into a
// single file -- it writes out_0.hepmc, out_1.hepmc, etc. This program
// avoids that by doing the write step itself under a mutex.)
//
// Build (assumes pythia8-config / HepMC3-config are on PATH, e.g. via
// setup.sh):
//
//   g++ -O2 -std=c++17 GenerateHepMC.cc -o generate_hepmc \
//       $(pythia8-config --cxxflags --libs) \
//       $(HepMC3-config --cflags --libs) \
//       -lpthread
//
// Usage:
//   ./generate_hepmc <run.cmnd> <output.hepmc> [nEvents] [nThreads] [seed] [pdf:pSet]
//
//   run.cmnd    : standard Pythia8 command file (beams, CR/Ropewalk,
//                 Woods-Saxon, etc. -- all collision setup lives here,
//                 untouched by this program)
//   output.hepmc: destination HepMC3 ASCII file
//   nEvents     : optional; overrides Main:numberOfEvents from the cmnd
//                 file if > 0 (default: use whatever the cmnd file says)
//   nThreads    : optional; degree of parallelism (default: hardware
//                 concurrency, decided here in code rather than in the
//                 cmnd file)
//
// Then analyze with Rivet, e.g.:
//   rivet --analysis=<ANALYSIS> -o out.yoda output.hepmc

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"
#include "Pythia8Plugins/HepMC3.h"

#include <cstdlib>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

using namespace Pythia8;

int main(int argc, char* argv[]) {

  if (argc < 3) {
    std::cerr << "Usage: " << argv[0] << " <cmnd file> <output.hepmc> [nEvents] [nThreads] [seed] [pdf:pSet]\n";
    return 1;
  }

  const std::string cmndFile =  string(argv[1]);
  const std::string outFile  =  string(argv[2]);
  const long nEventsArg  = (argc > 3) ? std::atol(argv[3]) : 10000;
  const long nThreadsArg = (argc > 4) ? std::atol(argv[4]) : 20;
  const long seedArg = (argc > 5) ? std::atol(argv[5]) : -1;
  const std::string pdfSetArg = (argc > 6) ? string(argv[6]) : "";

  PythiaParallel pythia;
  if (!pythia.readFile(cmndFile)) {
    std::cerr << "ERROR: could not read cmnd file '" << cmndFile << "'\n";
    return 1;
  }

  const unsigned int nThreads = (nThreadsArg > 0) ? static_cast<unsigned int>(nThreadsArg) : std::thread::hardware_concurrency();
  pythia.readString("Parallelism:numThreads = " + std::to_string(nThreads));
  pythia.readString("Print:quiet = on");
  if (seedArg > 0) pythia.readString("Random:seed = " + std::to_string(seedArg));
  if (!pdfSetArg.empty()) pythia.readString("PDF:pSet = " + pdfSetArg);

  if (!pythia.init()) {
    std::cerr << "ERROR: Pythia initialization failed.\n";
    return 1;
  }

  Pythia8ToHepMC toHepMC(outFile);
  std::mutex writeMutex;
  long nWritten = 0;

  auto onEvent = [&](Pythia* pythiaPtr) {
    std::lock_guard<std::mutex> lock(writeMutex);
    if (toHepMC.writeNextEvent(*pythiaPtr)) ++nWritten;
    else std::cerr << "WARNING: HepMC3 conversion/write failed for an event.\n";
  };

  std::vector<long> perThreadCounts = (nEventsArg > 0) ? pythia.run(nEventsArg, onEvent) : pythia.run(onEvent);

  pythia.stat();

  long nGenerated = 0;
  for (long c : perThreadCounts) nGenerated += c;

  std::cout << "Generated " << nGenerated << " events across " << nThreads << " threads; wrote " << nWritten << " to " << outFile << "\n";

  return 0;
}
