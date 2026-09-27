// modules/PhotoProduction/InprocJets.cc — Pythia and Rivet in one process: an integrated run.
// requires: pythia8 rivet   (Module.hh adds hepmc3 toml)
//
//     InprocJets.exe CONFIG.toml --output=photo.yoda
//
// The chain App_Pythia → FIFO → rivet, as one program (docs/05_Tools_Reference.md §18). Its tool
// table asks for the standard configurations (V21):
//
//     [tools.jets]
//     tool           = "module"
//     executable     = "InprocJets.exe"
//     output_file    = "photo.yoda"
//     pythia_cmnd    = true       # the point card App_Pythia would get: sweeps and seeds included
//     rivet_analyses = true       # the rivet table's analyses (with options) and the plugin path
//
// So the runner still owns the sweeps, seeds and cards; this program only runs them. Config:
//   engine = "parallel"  PythiaParallel, as App_Pythia: same card, same seeds, same instances
//            "serial"    one Pythia8::Pythia, seeded by the card's Random:seed
//
// It applies what App_Pythia learned (docs/07_Record.md §3):
//   L1  σ over instances is the ΣW-weighted mean, errors in quadrature;
//   L2  once more than one instance has contributed, each event is re-stamped with the combination,
//       so the σ Rivet takes (the last event's) is the run's;
//   L3  nothing may leave the callback, which runs on worker threads;
//   L6  run() in chunks of 100 × threads, as App_Pythia, so the instances see the same work.

#include "Module.hh"

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"
#include "Pythia8Plugins/HepMC3.h"
#include "Rivet/AnalysisHandler.hh"
#include "Rivet/Tools/RivetPaths.hh"

#include <cmath>
#include <exception>
#include <map>
#include <string>

namespace {

    struct Instance {
        double weightSum = 0, sigmaMb = 0, errorMb = 0;
    };

    std::pair<double, double> combine(const std::map<const Pythia8::Pythia*, Instance>& instances) {   // L1, in pb
        double weight = 0, value = 0, variance = 0;
        for (const auto& [_, in] : instances) {
            if (in.weightSum <= 0) continue;
            weight += in.weightSum, value += in.weightSum * in.sigmaMb, variance += std::pow(in.weightSum * in.errorMb, 2);
        }
        if (weight <= 0) return {0, 0};
        return {value / weight * 1e9, std::sqrt(variance) / weight * 1e9};
    }

}  // namespace

int main(int argc, char** argv) {
    Module::Job job(argc, argv);
    if (job.hasInput()) job.fail(Module::Usage, "InprocJets makes its own events; give it no input");
    const std::string card = job.standard("pythia_cmnd");
    const Module::Values rivetTable = job.standardValues("rivet_analyses");
    const std::string engine = job.config().get("engine", "parallel");
    if (engine != "parallel" && engine != "serial") job.fail(Module::Config, "engine must be parallel or serial");

    Rivet::addAnalysisLibPath(rivetTable.get("plugin_path", ""));
    Rivet::AnalysisHandler rivet;
    rivet.addAnalyses(rivetTable.list("analyses"));

    Pythia8::Pythia8ToHepMC converter;
    long written = 0;
    std::pair<double, double> sigma{0, 0};

    if (engine == "serial") {
        Pythia8::Pythia pythia;
        pythia.readString("Print:quiet = on");
        if (!pythia.readFile(card)) job.fail(Module::Config, "could not read " + card);
        const long requested = pythia.settings.mode("Main:numberOfEvents");
        job.status().phase("init", "serial");
        if (!pythia.init()) job.fail(Module::Init, "Pythia initialisation failed");
        job.status().phase("generating", std::to_string(requested) + " events");
        for (long attempt = 0; attempt < requested && !job.stopping(); ++attempt) {
            if (!pythia.next()) continue;
            if (!converter.fillNextEvent(pythia)) continue;
            rivet.analyze(converter.event());
            job.countEvent(pythia.info.weight());
            if (++written % 100 == 0) job.progress(written, requested);
        }
        sigma = {pythia.info.sigmaGen() * 1e9, pythia.info.sigmaErr() * 1e9};
    } else {
        Pythia8::PythiaParallel pythia;
        pythia.readString("Print:quiet = on");
        if (!pythia.readFile(card)) job.fail(Module::Config, "could not read " + card);
        pythia.readString("Parallelism:processAsync = off");
        const long requested = pythia.settings.mode("Main:numberOfEvents");
        int threads = pythia.settings.mode("Parallelism:numThreads");
        if (threads <= 0) threads = 1;
        job.status().phase("init", std::to_string(threads) + " threads");
        if (!pythia.init()) job.fail(Module::Init, "Pythia initialisation failed");

        std::map<const Pythia8::Pythia*, Instance> latest;
        std::exception_ptr failure;
        auto onEvent = [&](Pythia8::Pythia* instance) {
            if (failure || job.stopping()) return;
            try {                                                  // L3
                if (!converter.fillNextEvent(*instance)) return;
                HepMC3::GenEvent& event = converter.event();
                latest[instance] = {instance->info.weightSum(), instance->info.sigmaGen(), instance->info.sigmaErr()};
                if (latest.size() > 1) {                            // L2
                    const auto xs = combine(latest);
                    event.cross_section()->set_cross_section(xs.first, xs.second);
                }
                rivet.analyze(event);
                job.countEvent(event.weights().empty() ? 1.0 : event.weights().front());
                ++written;
            } catch (...) {
                failure = std::current_exception();
            }
        };
        job.status().phase("generating", std::to_string(requested) + " events");
        const long chunk = 100L * threads;                          // L6, as App_Pythia
        long attempted = 0;
        while (attempted < requested && !job.stopping() && !failure) {
            for (long count : pythia.run(std::min(chunk, requested - attempted), onEvent)) attempted += count;
            job.progress(written, requested);
        }
        if (failure) {
            try {
                std::rethrow_exception(failure);
            } catch (const std::exception& error) {
                job.fail(Module::Internal, std::string("in the event callback: ") + error.what());
            }
        }
        std::map<const Pythia8::Pythia*, Instance> final;
        pythia.foreach([&](Pythia8::Pythia* instance) {
            final[instance] = {instance->info.weightSum(), instance->info.sigmaGen(), instance->info.sigmaErr()};
        });
        sigma = final.size() == 1 ? std::pair<double, double>{final.begin()->second.sigmaMb * 1e9, final.begin()->second.errorMb * 1e9}
                                  : combine(final);
    }

    job.setCrossSection(sigma.first, sigma.second);               // the report's σ: the run's, as a sidecar's
    rivet.finalize();
    rivet.writeData(job.output());
    return job.finish();
}
