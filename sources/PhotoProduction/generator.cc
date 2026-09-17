// generator.cc
//
// Generate Pythia8 events and write them to a single HepMC3 ASCII stream
// (a file or the FIFO rivpyth sets up) for Rivet. Generation runs in
// parallel via Pythia8::PythiaParallel; callbacks are processed serially
// (Parallelism:processAsync = off), so one HepMC3 writer is enough.
//
// Everything is configured through cmnd files, read in the order given so
// that later settings override earlier ones. rivpyth passes two:
//   1. the base cmnd  — shared physics (configs/<project>/photo_ep.cmnd)
//   2. a point cmnd   — run control and sweep overrides
//                       (Main:numberOfEvents, Parallelism:numThreads,
//                        Random:seed, Beams:*, PDF:pSet, ...)
// Main:numberOfEvents sets the event count; Parallelism:numThreads = 0
// (Pythia's default) uses all hardware threads.
//
// Build:  make PhotoProduction/generator.exe   (after load_hep)
//
// Usage:
//   generator.exe <output.hepmc> <base.cmnd> [more.cmnd ...]
//
// Exit codes: 0 success, 1 cmnd/initialisation failure, 2 bad arguments.
// Output is opened only after a successful init(), so rivpyth must watch
// this process as well as Rivet (Rivet blocks until the stream opens).
//
// Then analyse with Rivet, e.g.:
//   rivet --analysis=<ANALYSIS> -o out.yoda output.hepmc

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"
#include "Pythia8Plugins/HepMC3.h"

#include <iostream>
#include <string>
#include <vector>

using namespace Pythia8;

int main(int argc, char* argv[]) {

  if (argc < 3) {
    std::cerr << "Usage: " << argv[0] << " <output.hepmc> <base.cmnd> [more.cmnd ...]\n";
    return 2;
  }

  const std::string outFile = argv[1];
  const std::vector<std::string> cmndFiles(argv + 2, argv + argc);

  PythiaParallel pythia;
  pythia.readString("Print:quiet = on");
  // readFile returns false for a missing file and for any line Pythia rejects
  // (unknown key or meaningless value), so bad sweep overrides stop here.
  for (const std::string& cmndFile : cmndFiles) {
    if (!pythia.readFile(cmndFile)) {
      std::cerr << "ERROR: could not read cmnd file '" << cmndFile << "' (missing file or rejected setting)\n";
      return 1;
    }
  }
  // The single HepMC3 writer below is unlocked; keep callbacks serial.
  pythia.readString("Parallelism:processAsync = off");

  if (!pythia.init()) {
    std::cerr << "ERROR: Pythia initialization failed.\n";
    return 1;
  }

  Pythia8ToHepMC toHepMC(outFile);
  long nWritten = 0;

  // Serial callback (processAsync = off): no locking needed around the writer.
  auto onEvent = [&](Pythia* pythiaPtr) {
    if (toHepMC.writeNextEvent(*pythiaPtr)) ++nWritten;
    else std::cerr << "WARNING: HepMC3 conversion/write failed for an event.\n";
  };

  // run(callback) generates Main:numberOfEvents events.
  const std::vector<long> perThreadCounts = pythia.run(onEvent);

  pythia.stat();

  long nGenerated = 0;
  for (long count : perThreadCounts) nGenerated += count;

  std::cout << "Generated " << nGenerated << " events across " << perThreadCounts.size()
            << " threads; wrote " << nWritten << " to " << outFile << "\n";

  return 0;
}
