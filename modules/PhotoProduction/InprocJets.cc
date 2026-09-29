// modules/PhotoProduction/InprocJets.cc — Pythia and Rivet in one process: an integrated run.
// requires: pythia8 rivet   (Module.hh adds hepmc3 toml)
//
//     InprocJets.exe CONFIG.toml --output=photo.yoda
//
// The chain App_Pythia → FIFO → rivet as one program, with no HepMC text between the two
// (docs/05_Tools_Reference.md §18). It asks for two standard configurations (V21, 04 §9.4), so the
// runner still owns the sweeps, seeds and cards, and this program only runs them:
//
//     [tools.jets]
//     tool           = "module"
//     executable     = "InprocJets.exe"
//     output_file    = "photo.yoda"
//     pythia_cmnd    = true       # [standard.pythia_cmnd].path: the card App_Pythia would get, seeds included
//     rivet_analyses = true       # [standard.rivet_analyses]: the rivet table's analyses (options included)
//                                 # and the plugin path
//
// Config ([tools.jets.config]):
//   engine = "parallel"  PythiaParallel as App_Pythia runs it: the same card, seeds and instances
//            "serial"    one Pythia8::Pythia, seeded by the card's Random:seed
//
// Threads: the card's Parallelism:numThreads generate and convert; one more runs Rivet. The pieces
// are in Inproc/: Stamp.hh (numbering and σ: L1, L2, L28), Feed.hh (Pythia threads → Rivet),
// Analysis.hh (Rivet on its own thread, L16), Engines.hh (serial and parallel: L3, L5, L6).

#include "Module.hh"
#include "Inproc/Analysis.hh"
#include "Inproc/Engines.hh"
#include "Inproc/Stamp.hh"

#include <string>

int main(int argc, char** argv) {
    Module::Job job(argc, argv);
    if (job.hasInput()) job.fail(Module::Usage, "InprocJets makes its own events; give it no input");
    const std::string card = job.standard("pythia_cmnd");
    const std::string engine = job.config().get("engine", "parallel");
    if (engine != "parallel" && engine != "serial") job.fail(Module::Config, "engine must be parallel or serial");

    Inproc::Analysis rivet(job, job.standardValues("rivet_analyses"));
    Inproc::Stamper stamper;
    const Inproc::Run run = engine == "serial" ? Inproc::serial(job, card, stamper, rivet)
                                               : Inproc::parallel(job, card, stamper, rivet);
    if (!run.error.empty()) {
        rivet.halt();                                               // no thread may outlive the exit
        job.fail(Module::Internal, run.error);
    }
    if (const std::string error = rivet.finish(stamper.last(), job.output()); !error.empty())
        job.fail(Module::Internal, error);

    job.setCrossSection(run.sigma.pb, run.sigma.errPb);             // the report's σ: the run's, as a sidecar's
    job.status().xsec(run.sigma.pb, run.sigma.errPb, true);
    return job.finish();
}
