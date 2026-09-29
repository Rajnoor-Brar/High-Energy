#pragma once
// modules/PhotoProduction/Inproc/Analysis.hh — Rivet on threads of its own, fed by the Pythia threads.
//
// `threads` Rivets (config `rivet_threads`, V34), each a Rivet::AnalysisHandler with its own
// analyses and projections, take events from one Feed: whichever is free takes the next. At the end
// they are merged into the first (AnalysisHandler::merge adds the raw fills and the event counters),
// which is given the σ the chain's Rivet would read (L28) as a user σ, finalised once and written.
// So the result is one Rivet's over all the events, summed in another order. The merge happens
// before any finalize(), so the analyses need not even be re-entrant.
//
// More than one Rivet needs SISCone's process-wide state per thread (L29): stock FastJet keeps one
// random generator and one eta range for the process, and threads clustering at once then get
// different jets (L16) or a FastJet internal error. The patch is utils/Env/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch; without it,
// `rivet_threads` above 1 is refused. Before the threads start, one SISCone clustering on the
// constructing thread prints FastJet's and SISCone's banners and sets their first-use flags.

#include "Module.hh"
#include "Inproc/Feed.hh"

#include "HepMC3/GenEvent.h"
#include "Rivet/AnalysisHandler.hh"
#include "Rivet/Tools/RivetPaths.hh"
#include "fastjet/ClusterSequence.hh"
#include "fastjet/SISConePlugin.hh"
#include "siscone/geom_2d.h"
#include "siscone/ranlux.h"

#include <algorithm>
#include <atomic>
#include <exception>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace Inproc {

    // Whether SISCone's process-wide state is per thread (the patch, L29): its random generator (a new
    // thread then draws the first number of the sequence, where a shared one hands it the next) and
    // the eta range each clustering sets (a new thread then does not see this thread's value).
    inline bool sisconePerThread() {
        siscone::ranlux_init();
        const unsigned long first = siscone::ranlux_get();
        const double range = siscone::Ceta_phi_range::eta_min;
        siscone::Ceta_phi_range::eta_min = range - 1.0;
        unsigned long other = 0;
        double seen = 0;
        std::thread([&] {
            other = siscone::ranlux_get();
            seen = siscone::Ceta_phi_range::eta_min;
        }).join();
        siscone::Ceta_phi_range::eta_min = range;
        return other == first && seen != range - 1.0;
    }

    class Analysis {
      public:
        // `table` is [standard.rivet_analyses]: the analyses, options included, and the plugin path.
        Analysis(Module::Job& job, const Module::Values& table, int threads, size_t depth = 128)
            : job_(job), feed_(depth * static_cast<size_t>(std::max(threads, 1))) {
            if (threads < 1) job.fail(Module::Config, "rivet_threads must be at least 1");
            if (threads > 1) {
                if (!sisconePerThread())
                    job.fail(Module::Config, "rivet_threads = " + std::to_string(threads) +
                                                 " needs SISCone's random generator per thread (L29): apply "
                                                 "utils/Env/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch "
                                                 "and rebuild FastJet, or set rivet_threads = 1");
                warmUp();
            }
            Rivet::addAnalysisLibPath(table.get("plugin_path", ""));
            for (int i = 0; i < threads; ++i) {
                handlers_.push_back(std::make_unique<Rivet::AnalysisHandler>());
                handlers_.back()->addAnalyses(table.list("analyses"));
            }
        }
        ~Analysis() { halt(); }
        Analysis(const Analysis&) = delete;
        Analysis& operator=(const Analysis&) = delete;

        int threads() const { return static_cast<int>(handlers_.size()); }

        // Once the generator is initialised: nothing may exit the program while these threads run.
        void start() {
            for (auto& handler : handlers_) workers_.emplace_back([this, h = handler.get()] { loop(*h); });
        }

        // From any Pythia thread. The first event initialises every handler, on this thread and
        // before any worker can see an event. False when Rivet has stopped taking events.
        bool push(std::shared_ptr<HepMC3::GenEvent> event) {
            std::call_once(initialised_, [&] {
                for (auto& handler : handlers_) handler->init(*event);
                started_ = true;
            });
            return feed_.push(std::move(event));
        }

        bool failed() const { return failed_; }
        long analysed() const { return analysed_; }

        // No more events: the Rivets analyse what is queued, and their threads end.
        void halt() {
            feed_.close();
            for (auto& worker : workers_)
                if (worker.joinable()) worker.join();
        }

        // After the generator is done: halt, merge, then σ, finalise and write. An error message, or "".
        std::string finish(const std::vector<std::pair<double, double>>& sigma, const std::string& output) {
            halt();
            if (failed_) return error_;
            try {
                Rivet::AnalysisHandler& rivet = *handlers_.front();
                if (started_)
                    for (size_t i = 1; i < handlers_.size(); ++i) rivet.merge(*handlers_[i]);
                if (!sigma.empty()) rivet.setCrossSection(sigma, true);    // L28
                rivet.finalize();
                rivet.writeData(output);
            } catch (const std::exception& error) {
                return std::string("Rivet: ") + error.what();
            }
            return "";
        }

      private:
        void loop(Rivet::AnalysisHandler& rivet) {
            try {
                while (std::shared_ptr<HepMC3::GenEvent> event = feed_.pop()) {
                    rivet.analyze(*event);
                    {
                        std::lock_guard<std::mutex> guard(countLock_);
                        job_.countEvent(event->weights().empty() ? 1.0 : event->weights().front());
                    }
                    ++analysed_;
                }
            } catch (const std::exception& error) {
                fail(std::string("Rivet: ") + error.what());
            } catch (...) {
                fail("Rivet: unknown exception");
            }
        }

        void fail(const std::string& message) {
            {
                std::lock_guard<std::mutex> guard(countLock_);
                if (error_.empty()) error_ = message;
            }
            failed_ = true;
            feed_.close();                                              // the producers stop waiting
        }

        // FastJet and SISCone print a banner and set a flag on their first clustering: do it here, once.
        static void warmUp() {
            fastjet::SISConePlugin plugin(0.7, 0.75);
            const fastjet::JetDefinition definition(&plugin);
            const std::vector<fastjet::PseudoJet> one{fastjet::PseudoJet(1.0, 0.0, 1.0, 2.0)};
            fastjet::ClusterSequence(one, definition).inclusive_jets();
        }

        Module::Job& job_;
        std::vector<std::unique_ptr<Rivet::AnalysisHandler>> handlers_;
        Feed feed_;
        std::vector<std::thread> workers_;
        std::once_flag initialised_;
        std::atomic<bool> started_{false}, failed_{false};
        std::atomic<long> analysed_{0};
        std::mutex countLock_;                                          // job_.countEvent and error_
        std::string error_;
    };

}  // namespace Inproc
