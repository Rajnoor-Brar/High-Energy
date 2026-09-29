#pragma once
// modules/PhotoProduction/Inproc/Engines.hh — the two ways InprocJets makes its events.
//
//   serial    one Pythia8::Pythia, seeded by the card's Random:seed
//   parallel  PythiaParallel as App_Pythia runs it: the same card, seeds and instances; callbacks in
//             parallel (processAsync = on), each instance converting with its own converter
//
// Both stamp every converted event (Stamp.hh) and hand it to the Rivets (Analysis.hh). Nothing here
// exits the program once the Rivets' threads have started: a failure is returned in Run::error.
//   L3  Nothing may leave a callback: the first exception is kept and returned.
//   L5  Main:numberOfEvents counts attempts, and failed events never reach Rivet.
//   L6  run() goes in chunks of 100 × threads, as App_Pythia, so the instances see the same work.

#include "Module.hh"
#include "Inproc/Analysis.hh"
#include "Inproc/Stamp.hh"

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"
#include "Pythia8Plugins/HepMC3.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <exception>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace Inproc {

    struct Run {
        long requested = 0, attempted = 0;
        int threads = 1;
        Xsec sigma;               // from every instance after the run: App_Pythia's sidecar's σ
        std::string error;        // non-empty: the run failed after Rivet's thread started
    };

    namespace detail {
        template <class P>
        void configure(Module::Job& job, P& pythia, const std::string& card) {
            pythia.readString("Print:quiet = on");
            if (!pythia.readFile(card)) job.fail(Module::Config, "could not read the card " + card);
        }

        // Progress and the running σ, at most twice a second.
        class Report {
          public:
            void operator()(Module::Job& job, const Run& run, const Stamper& stamper, const Analysis& rivet,
                            bool force = false) {
                const auto now = std::chrono::steady_clock::now();
                if (!force && now - last_ < std::chrono::milliseconds(500)) return;
                last_ = now;
                job.progress(rivet.analysed(), run.requested);
                const Xsec xs = stamper.running();
                job.status().xsec(xs.pb, xs.errPb, false);
            }

          private:
            std::chrono::steady_clock::time_point last_{};
        };

        inline std::string describe(const std::exception_ptr& failure) {
            try {
                std::rethrow_exception(failure);
            } catch (const std::exception& error) {
                return std::string("in the event callback: ") + error.what();
            } catch (...) {
                return "in the event callback: unknown exception";
            }
        }
    }  // namespace detail

    inline Run serial(Module::Job& job, const std::string& card, Stamper& stamper, Analysis& rivet) {
        Pythia8::Pythia pythia;
        detail::configure(job, pythia, card);
        Run run;
        run.requested = pythia.settings.mode("Main:numberOfEvents");
        job.status().phase("init", "serial, " + std::to_string(rivet.threads()) + " Rivet");
        if (!pythia.init()) job.fail(Module::Init, "Pythia initialisation failed");

        rivet.start();
        job.status().phase("generating", std::to_string(run.requested) + " events");
        Pythia8::Pythia8ToHepMC converter;
        detail::Report report;
        try {
            for (; run.attempted < run.requested && !job.stopping(); ++run.attempted) {
                if (!pythia.next() || !converter.fillNextEvent(pythia)) continue;   // L5
                const std::shared_ptr<HepMC3::GenEvent> event = converter.getEventPtr();
                stamper.stamp(pythia, *event);
                if (!rivet.push(event)) break;                               // Rivet failed
                report(job, run, stamper, rivet);
            }
        } catch (...) {
            run.error = detail::describe(std::current_exception());
        }
        run.sigma = Stamper::final({&pythia});
        pythia.stat();
        return run;
    }

    inline Run parallel(Module::Job& job, const std::string& card, Stamper& stamper, Analysis& rivet) {
        Pythia8::PythiaParallel pythia;
        detail::configure(job, pythia, card);
        pythia.readString("Parallelism:processAsync = on");                  // as App_Pythia
        Run run;
        run.requested = pythia.settings.mode("Main:numberOfEvents");
        run.threads = std::max(1, pythia.settings.mode("Parallelism:numThreads"));
        job.status().phase("init", std::to_string(run.threads) + " threads, " + std::to_string(rivet.threads()) + " Rivet");
        if (!pythia.init()) job.fail(Module::Init, "Pythia initialisation failed");

        // A converter per instance, each used only on its instance's thread; read-only from here.
        std::map<const Pythia8::Pythia*, std::unique_ptr<Pythia8::Pythia8ToHepMC>> converters;
        pythia.foreach([&](Pythia8::Pythia* instance) { converters[instance] = std::make_unique<Pythia8::Pythia8ToHepMC>(); });
        std::mutex failLock;
        std::exception_ptr failure;                                          // under failLock
        std::atomic<bool> failed{false};
        auto onEvent = [&](Pythia8::Pythia* instance) {
            if (failed || job.stopping() || rivet.failed()) return;
            try {                                                            // L3
                Pythia8::Pythia8ToHepMC& converter = *converters.at(instance);
                if (!converter.fillNextEvent(*instance)) return;
                const std::shared_ptr<HepMC3::GenEvent> event = converter.getEventPtr();   // a new one each event
                stamper.stamp(*instance, *event);
                rivet.push(event);
            } catch (...) {
                std::lock_guard<std::mutex> guard(failLock);
                if (!failure) failure = std::current_exception();
                failed = true;
            }
        };

        rivet.start();
        job.status().phase("generating", std::to_string(run.requested) + " events");
        const long chunk = 100L * run.threads;                               // L6
        detail::Report report;
        while (run.attempted < run.requested && !job.stopping() && !failed && !rivet.failed()) {
            for (long count : pythia.run(std::min(chunk, run.requested - run.attempted), onEvent))
                run.attempted += count;                                      // every callback has returned
            report(job, run, stamper, rivet);
        }
        if (failure) run.error = detail::describe(failure);

        std::vector<Pythia8::Pythia*> instances;
        pythia.foreach([&](Pythia8::Pythia* instance) { instances.push_back(instance); });
        run.sigma = Stamper::final(instances);
        pythia.stat();
        return run;
    }

}  // namespace Inproc
