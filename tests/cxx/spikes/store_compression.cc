// Spike: gz against zstd for the event store (P5-S01, decision D-STORE-COMP).
//
// The question is not "which compresses better" in the abstract — it is which one to make the
// default for files that are written once by a long run and read back by replays. So this measures
// what actually matters: the size of the store, how much of the generator's time writing costs, and
// how fast a replay can read it back.
//
//   store_compression [events] [directory] [card]
//
// It generates real Pythia events with the project's own photoproduction card, converts them to
// HepMC3, and writes the *same* events through each codec in turn — the comparison is of codecs, not
// of two samples. Each event is **copied** out of the converter, which reuses one `GenEvent`: holding
// its pointer 10 000 times would have measured one event written 10 000 times.

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

#include "HepMC3/CompressedIO.h"
#include "HepMC3/GenEvent.h"
#include "HepMC3/ReaderAscii.h"
#include "HepMC3/ReaderGZ.h"
#include "HepMC3/WriterAscii.h"
#include "HepMC3/WriterGZ.h"
#include "Pythia8/Pythia.h"
#include "Pythia8Plugins/HepMC3.h"

namespace {

double seconds(std::chrono::steady_clock::time_point from) {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - from).count();
}

struct Measurement {
    std::string name;
    double write_seconds = 0.0;
    double read_seconds = 0.0;
    std::uintmax_t bytes = 0;
    int read_back = 0;
};

// One codec, the same events, written and read back.
template <typename Writer, typename Reader>
Measurement measure(const std::string& name, const std::string& path,
                    const std::vector<std::shared_ptr<HepMC3::GenEvent>>& events) {
    Measurement found;
    found.name = name;
    {
        const auto started = std::chrono::steady_clock::now();
        Writer writer(path);
        for (const auto& event : events) writer.write_event(*event);
        writer.close();
        found.write_seconds = seconds(started);
    }
    found.bytes = std::filesystem::file_size(path);
    {
        const auto started = std::chrono::steady_clock::now();
        Reader reader(path);
        HepMC3::GenEvent event;
        while (!reader.failed()) {
            reader.read_event(event);
            if (reader.failed()) break;
            found.read_back += 1;
        }
        reader.close();
        found.read_seconds = seconds(started);
    }
    return found;
}

}  // namespace

int main(int argc, char* argv[]) {
    const int wanted = argc > 1 ? std::atoi(argv[1]) : 10000;
    const std::string directory = argc > 2 ? argv[2] : "output/scratch/spike-store";
    std::filesystem::create_directories(directory);

    const std::string card = argc > 3 ? argv[3]
                                      : "tests/golden/inputs/PhotoProduction/photo_ep.cmnd";
    Pythia8::Pythia pythia;
    pythia.readString("Print:quiet = on");
    if (!pythia.readFile(card)) {
        std::cerr << "spike: Pythia rejected the card: " << card << "\n";
        return 1;
    }
    pythia.readString("Beams:frameType = 2");
    pythia.readString("Beams:idB = -11");
    pythia.readString("Beams:eA = 920");
    pythia.readString("Beams:eB = 27.5");
    pythia.readString("Random:setSeed = on");
    pythia.readString("Random:seed = 4242");
    if (!pythia.init()) {
        std::cerr << "spike: Pythia failed to initialise\n";
        return 3;
    }

    // Generate once, then write the same events with each codec: the comparison is of the codecs,
    // not of two samples.
    std::vector<std::shared_ptr<HepMC3::GenEvent>> events;
    events.reserve(wanted);
    Pythia8::Pythia8ToHepMC bridge;
    const auto generation_started = std::chrono::steady_clock::now();
    while (static_cast<int>(events.size()) < wanted) {
        if (!pythia.next()) continue;
        if (!bridge.fillNextEvent(pythia)) continue;
        // A copy: the converter reuses one GenEvent, so keeping its pointer would store the same
        // event every time and make every codec look magnificent.
        events.push_back(std::make_shared<HepMC3::GenEvent>(*bridge.getEventPtr()));
    }
    const double generation = seconds(generation_started);

    std::vector<Measurement> results;
    results.push_back(measure<HepMC3::WriterAscii, HepMC3::ReaderAscii>(
        "none", directory + "/events.hepmc", events));
    results.push_back(measure<HepMC3::WriterGZ<HepMC3::WriterAscii, HepMC3::Compression::z>,
                              HepMC3::ReaderGZ<HepMC3::ReaderAscii>>(
        "gz", directory + "/events.hepmc.gz", events));
    results.push_back(measure<HepMC3::WriterGZ<HepMC3::WriterAscii, HepMC3::Compression::zstd>,
                              HepMC3::ReaderGZ<HepMC3::ReaderAscii>>(
        "zst", directory + "/events.hepmc.zst", events));

    const double plain = static_cast<double>(results.front().bytes);
    std::cout << "events " << events.size() << "  generation " << std::fixed << std::setprecision(2)
              << generation << " s (" << events.size() / generation << " ev/s)\n\n";
    std::cout << std::left << std::setw(6) << "codec" << std::right
              << std::setw(14) << "bytes" << std::setw(9) << "per ev"
              << std::setw(9) << "ratio" << std::setw(10) << "write s" << std::setw(11) << "write ev/s"
              << std::setw(9) << "read s" << std::setw(11) << "read ev/s"
              << std::setw(9) << "% of gen" << "\n";
    for (const Measurement& row : results) {
        std::cout << std::left << std::setw(6) << row.name << std::right
                  << std::setw(14) << row.bytes
                  << std::setw(9) << row.bytes / events.size()
                  << std::setw(9) << std::setprecision(2) << plain / static_cast<double>(row.bytes)
                  << std::setw(10) << std::setprecision(2) << row.write_seconds
                  << std::setw(11) << std::setprecision(0) << events.size() / row.write_seconds
                  << std::setw(9) << std::setprecision(2) << row.read_seconds
                  << std::setw(11) << std::setprecision(0) << events.size() / row.read_seconds
                  << std::setw(8) << std::setprecision(1) << 100.0 * row.write_seconds / generation
                  << "%";
        if (row.read_back != static_cast<int>(events.size()))
            std::cout << "   READ BACK " << row.read_back << " OF " << events.size();
        std::cout << "\n";
    }
    return 0;
}
