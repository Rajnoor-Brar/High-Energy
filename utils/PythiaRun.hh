#pragma once
// utils/PythiaRun.hh — what every program that runs Pythia for the framework does the same way (V63):
// App_Pythia (the chain's generator) and the integrated programs (modules/PhotoProduction/InprocJets),
// so their events and σ are the same by construction, not by a copied file.
//
//   L1  PythiaParallel exposes σ per instance and no error for the run: the combination is the
//       ΣW-weighted mean, errors in quadrature (`combine`, `final`).
//   L2  Once more than one instance has contributed, each event is re-stamped with the combination;
//       with one instance the converter's own numbers are left as they are (`Stamper::stamp`).
//   L28 The σ a consumer reads at the end is the last one stamped (`Stamper::last`).
//   L4  Parallelism:seeds must have one seed per thread, each in 1 … 9·10⁸; Pythia checks neither
//       (`checkSeeds`). Parallelism:numThreads ≤ 0 means every core (`threads`).
//   L6  run() goes in chunks that are a multiple of the thread count (`chunk`), so a stop takes effect
//       within one and every program gives the instances the same work.
// requires: pythia8 hepmc3

#include "HepMC3/GenCrossSection.h"
#include "HepMC3/GenEvent.h"
#include "HepMC3/GenRunInfo.h"
#include "Pythia8/Pythia.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace PythiaRun {

    struct Xsec {
        double pb = 0, errPb = 0;
    };

    struct Instance {
        double weightSum = 0, sigmaMb = 0, errorMb = 0;
    };

    inline Instance of(Pythia8::Pythia& instance) {
        return {instance.info.weightSum(), instance.info.sigmaGen(), instance.info.sigmaErr()};
    }

    // L1: the ΣW-weighted mean, errors in quadrature; mb → pb.
    inline Xsec combine(const std::map<const Pythia8::Pythia*, Instance>& instances) {
        double weight = 0, value = 0, variance = 0;
        for (const auto& [_, in] : instances) {
            if (in.weightSum <= 0) continue;                         // an instance that generated nothing says nothing
            weight += in.weightSum;
            value += in.weightSum * in.sigmaMb;
            variance += std::pow(in.weightSum * in.errorMb, 2);
        }
        if (weight <= 0) return {};
        return {value / weight * 1e9, std::sqrt(variance) / weight * 1e9};
    }

    // From every instance's numbers after the run: one instance's own, else the combination.
    inline Xsec final(const std::vector<Pythia8::Pythia*>& instances) {
        if (instances.size() == 1)
            return {instances.front()->info.sigmaGen() * 1e9, instances.front()->info.sigmaErr() * 1e9};
        std::map<const Pythia8::Pythia*, Instance> all;
        for (Pythia8::Pythia* instance : instances) all[instance] = of(*instance);
        return combine(all);
    }

    // The σ an event was stamped with, as the converter or the re-stamp left it.
    struct Stamp {
        std::vector<double> xs, err;
        long accepted = -1, attempted = -1;
    };

    // What every converted event gets before anyone reads it: one numbering across the instances, one
    // run info, the combined σ (L2), and a record of the last σ stamped (L28). Thread-safe: each
    // instance's callback calls stamp() on its own thread.
    class Stamper {
      public:
        void stamp(Pythia8::Pythia& instance, HepMC3::GenEvent& event) {
            event.set_event_number(static_cast<int>(numbered_++));   // one numbering, from 0
            std::lock_guard<std::mutex> guard(lock_);
            if (!runInfo_) runInfo_ = event.run_info();
            event.set_run_info(runInfo_);                            // one run info: no per-event warning
            latest_[&instance] = of(instance);
            const auto cs = event.cross_section();
            if (!cs) return;
            if (latest_.size() > 1) {                                // L2
                const Xsec xs = combine(latest_);
                cs->set_cross_section(xs.pb, xs.errPb);
            }
            last_ = {cs->xsecs(), cs->xsec_errs(), cs->get_accepted_events(), cs->get_attempted_events()};
        }

        Stamp last() const {                                         // L28
            std::lock_guard<std::mutex> guard(lock_);
            return last_;
        }

        Xsec running() const {                                       // for the status line
            std::lock_guard<std::mutex> guard(lock_);
            return combine(latest_);
        }

      private:
        mutable std::mutex lock_;
        std::atomic<long> numbered_{0};
        std::shared_ptr<HepMC3::GenRunInfo> runInfo_;               // under lock_
        std::map<const Pythia8::Pythia*, Instance> latest_;          // under lock_
        Stamp last_;                                                 // under lock_
    };

    // Parallelism:numThreads as Pythia will use it: ≤ 0 is every core. (Settings::mode is not const.)
    inline int threads(Pythia8::Settings& settings) {
        const int set = settings.mode("Parallelism:numThreads");
        return set > 0 ? set : static_cast<int>(std::max(1u, std::thread::hardware_concurrency()));
    }

    // L4: "" when Parallelism:seeds is empty or right, else what is wrong with it.
    inline std::string checkSeeds(Pythia8::Settings& settings, int threadCount) {
        const std::vector<int> seeds = settings.mvec("Parallelism:seeds");
        if (seeds.empty()) return "";
        if (static_cast<int>(seeds.size()) != threadCount)
            return "Parallelism:seeds has " + std::to_string(seeds.size()) + " seeds for " + std::to_string(threadCount) +
                   " threads; it needs one per thread";
        for (int seed : seeds)
            if (seed < 1 || seed > 900000000)
                return "seed " + std::to_string(seed) + " is outside Pythia's range 1…900000000";
        return "";
    }

    // L6: events per call of PythiaParallel::run, a multiple of the thread count.
    inline long chunk(int threadCount) { return 100L * threadCount; }

}  // namespace PythiaRun
