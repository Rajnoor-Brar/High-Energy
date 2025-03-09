#include "Pythia8/Pythia.h"
using namespace Pythia8;

int main() {
    Pythia pythia;

    // Set up collision (e.g., proton-proton at 14 TeV)
    pythia.readString("Beams:idA = 2212");    // Proton
    pythia.readString("Beams:idB = 2212");    // Proton
    pythia.readString("Beams:eCM = 14000.");  // Center-of-mass energy in GeV

    // Initialize Pythia
    pythia.init();

    // Generate some events
    for (int i = 0; i < 10; ++i) {
        if (!pythia.next()) continue;  // Generate next event
        std::cout << "Event " << i + 1 << " generated." << std::endl;
    }

    return 0;
}
