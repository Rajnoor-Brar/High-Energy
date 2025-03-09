#include <iostream>
#include "Pythia8/Pythia.h"
using namespace Pythia8;
int main() {
    int nEvent = 5;
    Pythia pythia;
    pythia.readString("Beams:eCM = 13000.");
    

    pythia.init();
    for (int iEvent = 0; iEvent < nEvent; iEvent++) {
        pythia.next();
    }
    pythia.stat();
    return 0;
}
