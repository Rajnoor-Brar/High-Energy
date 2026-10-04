// modules/PhotoProduction/InprocJets.cc — Pythia and Rivet in one process: an integrated run.
// requires: pythia8 rivet fastjet   (Module.hh adds hepmc3 toml; Inproc/Analysis.hh uses FastJet and SISCone)
//
//     InprocJets.exe CONFIG.toml --output=photo.yoda
//
// The chain App_Pythia → FIFO → rivet as one program, with no HepMC text between the two
// (docs/06_Internals.md §21). It asks for two standard configurations (V21, 04 §9.4), so the
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
// Config ([tools.<tag>.config]):
//   engine        = "parallel"  PythiaParallel as App_Pythia runs it: the same card, seeds and instances
//                   "serial"    one Pythia8::Pythia, seeded by the card's Random:seed
//   rivet_threads = 1           Rivets, each on its own thread, merged at the end (V34); above 1 it
//                               needs the SISCone patch (L29) and refuses to run without it
//
// Threads: the card's Parallelism:numThreads generate and convert, and rivet_threads analyse. The
// pieces are in Inproc/: Stamp.hh (numbering and σ: L1, L2, L28), Feed.hh (Pythia threads → the
// Rivets), Analysis.hh (the Rivets and their merge: L16, L29), Engines.hh (serial and parallel: L3,
// L5, L6).

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

    Inproc::Analysis rivet(job, job.standardValues("rivet_analyses"), job.config().get("rivet_threads", 1));
    Inproc::Stamper stamper;
    const Inproc::Run run = engine == "serial" ? Inproc::serial(job, card, stamper, rivet)
                                               : Inproc::parallel(job, card, stamper, rivet);
    if (!run.error.empty()) {
        rivet.halt();                                               // no thread may outlive the exit
        job.fail(Module::Internal, run.error);
    }
    if (const std::string error = rivet.finish(Inproc::lastSigma(stamper), job.output()); !error.empty())
        job.fail(Module::Output, error);                            // the YODA could not be written (06 §11)

    job.setCrossSection(run.sigma.pb, run.sigma.errPb, "generator");   // the report's σ: the run's own
    job.status().xsec(run.sigma.pb, run.sigma.errPb, true);
    return job.finish();
}
