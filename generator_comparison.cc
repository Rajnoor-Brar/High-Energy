/*
 * generator_comparison.cpp
 *
 * Compare Pythia 8, Herwig 7 and Sherpa using the same simple
 * particle-level analysis:
 *
 *   - particle pT
 *   - particle E
 *   - particle eta
 *   - charged-particle multiplicity
 *
 * 50,000 events are processed for each generator.
 *
 * IMPORTANT:
 * Pythia 8 has a stable, simple in-process C++ API.
 * Herwig 7 and Sherpa expose substantially more framework-specific
 * APIs. Rather than inventing non-existent APIs, this file uses the
 * standard event-file interface for Herwig/Sherpa:
 *
 *     generator -> HepMC3 -> this program -> ROOT
 *
 * The Pythia sample is generated in-process.
 *
 * Herwig/Sherpa commands are supplied through environment variables:
 *
 *   HERWIG_CMD
 *   SHERPA_CMD
 *
 * Each command must generate a HepMC3 file named:
 *
 *   herwig.hepmc
 *   sherpa.hepmc
 *
 * containing at least 50,000 events.
 *
 * Example:
 *
 *   export HERWIG_CMD='Herwig read ... && Herwig run ...'
 *   export SHERPA_CMD='Sherpa -f sherpa_run.yaml'
 *
 * Then:
 *
 *   ./generator_comparison
 *
 * Output:
 *
 *   generator_comparison.root
 *
 * Compile:
 *
 *   g++ -std=c++17 generator_comparison.cpp \
 *       $(pythia8-config --cxxflags --libs) \
 *       $(root-config --cflags --libs) \
 *       $(pkg-config --cflags --libs HepMC3) \
 *       -o generator_comparison
 *
 * The Pythia process below is deliberately simple:
 *
 *     pp -> QCD hard scattering
 *
 * For Herwig/Sherpa, configure the corresponding generator to produce
 * the same physical process and collision energy if you want a genuine
 * apples-to-apples comparison.
 */

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include <Pythia8/Pythia.h>

#include <HepMC3/GenEvent.h>
#include <HepMC3/GenParticle.h>
#include <HepMC3/ReaderAscii.h>

#include <TFile.h>
#include <TH1D.h>
#include <TDirectory.h>
namespace fs = std::filesystem;

static constexpr int N_EVENTS = 50000;

// -----------------------------------------------------------------------------
// Common analysis
// -----------------------------------------------------------------------------

struct Histograms {
    TH1D* pt = nullptr;
    TH1D* energy = nullptr;
    TH1D* eta = nullptr;
    TH1D* charged_mult = nullptr;

    Histograms(TFile& file, const std::string& prefix)
    {
        file.cd();

        pt = new TH1D(
            (prefix + "_pt").c_str(),
            (prefix + ": stable-particle p_{T};p_{T} [GeV];particles").c_str(),
            100, 0.0, 200.0
        );

        energy = new TH1D(
            (prefix + "_energy").c_str(),
            (prefix + ": stable-particle energy;E [GeV];particles").c_str(),
            100, 0.0, 500.0
        );

        eta = new TH1D(
            (prefix + "_eta").c_str(),
            (prefix + ": stable-particle #eta;#eta;particles").c_str(),
            100, -10.0, 10.0
        );

        charged_mult = new TH1D(
            (prefix + "_charged_mult").c_str(),
            (prefix + ": charged-particle multiplicity;N_{ch};events").c_str(),
            100, 0.0, 100.0
        );
    }

    void write()
    {
        pt->Write();
        energy->Write();
        eta->Write();
        charged_mult->Write();
    }
};

// -----------------------------------------------------------------------------
// Pythia analysis
// -----------------------------------------------------------------------------

void analyze_pythia_event(
    const Pythia8::Event& event,
    Histograms& h
)
{
    int ncharged = 0;

    for (int i = 0; i < event.size(); ++i) {

        const auto& p = event[i];

        // Stable final-state particles only.
        if (!p.isFinal())
            continue;

        const double pt = p.pT();
        const double E = p.e();
        const double eta = p.eta();

        h.pt->Fill(pt);
        h.energy->Fill(E);
        h.eta->Fill(eta);

        if (p.isCharged())
            ++ncharged;
    }

    h.charged_mult->Fill(ncharged);
}

// -----------------------------------------------------------------------------
// HepMC3 analysis
// -----------------------------------------------------------------------------

void analyze_hepmc_event(
    const HepMC3::GenEvent& event,
    Histograms& h
)
{
    int ncharged = 0;

    for (const auto& p : event.particles()) {

        // HepMC3 status 1 convention for final-state particles.
        if (p->status() != 1)
            continue;

        const auto& mom = p->momentum();

        const double px = mom.px();
        const double py = mom.py();
        const double pz = mom.pz();
        const double E  = mom.e();

        const double pt = std::hypot(px, py);
        const double pabs = std::sqrt(
            px * px + py * py + pz * pz
        );

        double eta = 0.0;

        if (pabs > std::abs(pz)) {
            eta = 0.5 * std::log(
                (pabs + pz) / (pabs - pz)
            );
        } else {
            eta = (pz >= 0.0) ? 1e10 : -1e10;
        }

        h.pt->Fill(pt);
        h.energy->Fill(E);
        h.eta->Fill(eta);

        // PDG charge lookup is intentionally conservative here.
        // The common charged stable-particle set covers the particles
        // normally relevant to this basic comparison.
        const int id = std::abs(p->pid());

        const bool charged =
            id == 11   || // e
            id == 13   || // mu
            id == 15   || // tau
            id == 211  || // pi
            id == 321  || // K
            id == 2212 || // proton
            id == 3222 || // Sigma+
            id == 3112 || // Sigma-
            id == 3312 || // Xi-
            id == 3334;   // Omega-

        if (charged)
            ++ncharged;
    }

    h.charged_mult->Fill(ncharged);
}

// -----------------------------------------------------------------------------
// Run Pythia in-process
// -----------------------------------------------------------------------------

void run_pythia(Histograms& h)
{
    std::cout << "\n========================================\n";
    std::cout << "Pythia: generating " << N_EVENTS << " events\n";
    std::cout << "========================================\n";

    Pythia8::Pythia pythia;

    pythia.readString("Beams:idA = 2212");
    pythia.readString("Beams:idB = 2212");

    // 13 TeV pp example.
    pythia.readString("Beams:eCM = 13000.");

    // Generic QCD hard scattering.
    pythia.readString("HardQCD:all = on");

    // Reproducible run.
    pythia.readString("Random:setSeed = on");
    pythia.readString("Random:seed = 12345");

    if (!pythia.init()) {
        throw std::runtime_error(
            "Pythia initialization failed."
        );
    }

    int generated = 0;

    for (int i = 0; i < N_EVENTS; ++i) {

        if (!pythia.next())
            continue;

        ++generated;

        analyze_pythia_event(
            pythia.event,
            h
        );

        if (generated % 5000 == 0) {
            std::cout
                << "  Pythia: "
                << generated
                << " events\n";
        }
    }

    std::cout
        << "Pythia completed: "
        << generated
        << " successful events\n";
}

// -----------------------------------------------------------------------------
// Run an external generator which writes HepMC3.
//
// The external command itself is deliberately configurable because Herwig
// and Sherpa steering differs between installations and physics setups.
// -----------------------------------------------------------------------------

void run_external_hepmc_generator(
    const std::string& generator_name,
    const char* command_env,
    const fs::path& hepmc_file,
    Histograms& h
)
{
    std::cout << "\n========================================\n";
    std::cout << generator_name
              << ": generating " << N_EVENTS << " events\n";
    std::cout << "========================================\n";

    const char* command = std::getenv(command_env);

    if (!command || std::string(command).empty()) {
        std::cerr
            << generator_name
            << " skipped: environment variable "
            << command_env
            << " is not set.\n";
        return;
    }

    std::cout
        << "Running: "
        << command
        << '\n';

    const int rc = std::system(command);

    if (rc != 0) {
        throw std::runtime_error(
            generator_name +
            " command failed with exit code " +
            std::to_string(rc)
        );
    }

    if (!fs::exists(hepmc_file)) {
        throw std::runtime_error(
            generator_name +
            " did not produce expected HepMC3 file: " +
            hepmc_file.string()
        );
    }

    HepMC3::ReaderAscii reader(
        hepmc_file.string()
    );

    HepMC3::GenEvent event;

    int events = 0;

    while (events < N_EVENTS && !reader.failed()) {

        reader.read_event(event);

        if (reader.failed())
            break;

        analyze_hepmc_event(
            event,
            h
        );

        ++events;

        if (events % 5000 == 0) {
            std::cout
                << "  "
                << generator_name
                << ": "
                << events
                << " events\n";
        }

        event.clear();
    }

    reader.close();

    std::cout
        << generator_name
        << " completed: "
        << events
        << " events analyzed\n";
}

// -----------------------------------------------------------------------------
// Main
// -----------------------------------------------------------------------------

int main()
{
    try {

        TFile output(
            "generator_comparison.root",
            "RECREATE"
        );

        if (output.IsZombie()) {
            throw std::runtime_error(
                "Unable to create generator_comparison.root"
            );
        }

        // One directory per generator.
        TDirectory* pythia_dir =
            output.mkdir("Pythia");

        TDirectory* herwig_dir =
            output.mkdir("Herwig");

        TDirectory* sherpa_dir =
            output.mkdir("Sherpa");

        // ---------------------------------------------------------------------
        // Pythia
        // ---------------------------------------------------------------------

        pythia_dir->cd();

        Histograms pythia_hist(
            output,
            "Pythia"
        );

        run_pythia(
            pythia_hist
        );

        // ---------------------------------------------------------------------
        // Herwig
        // ---------------------------------------------------------------------

        herwig_dir->cd();

        Histograms herwig_hist(
            output,
            "Herwig"
        );

        run_external_hepmc_generator(
            "Herwig",
            "HERWIG_CMD",
            "herwig.hepmc",
            herwig_hist
        );

        // ---------------------------------------------------------------------
        // Sherpa
        // ---------------------------------------------------------------------

        sherpa_dir->cd();

        Histograms sherpa_hist(
            output,
            "Sherpa"
        );

        run_external_hepmc_generator(
            "Sherpa",
            "SHERPA_CMD",
            "sherpa.hepmc",
            sherpa_hist
        );

        // ---------------------------------------------------------------------
        // Write
        // ---------------------------------------------------------------------

        output.cd();

        pythia_hist.write();
        herwig_hist.write();
        sherpa_hist.write();

        output.Close();

        std::cout
            << "\n========================================\n"
            << "Done.\n"
            << "Output: generator_comparison.root\n"
            << "========================================\n";

    }
    catch (const std::exception& e) {

        std::cerr
            << "\nERROR: "
            << e.what()
            << '\n';

        return 1;
    }

    return 0;
}
