#pragma once
// modules/PhotoProduction/Inproc/Stamp.hh — what every event gets before Rivet sees it, as App_Pythia
// gives it: one numbering across the instances, one run info, the combined σ, and a record of the
// last σ stamped.
//
//   L1  PythiaParallel exposes σ per instance and no error for the run: the combination is the
//       ΣW-weighted mean, errors in quadrature.
//   L2  Once more than one instance has contributed, each event is re-stamped with the combination.
//       With one instance the converter's own numbers are left as they are.
//   L28 The σ Rivet is given at the end is the last one stamped: the one the chain's Rivet reads,
//       since App_Pythia ends every output on it.

#include "HepMC3/GenCrossSection.h"
#include "HepMC3/GenEvent.h"
#include "HepMC3/GenRunInfo.h"
#include "Pythia8/Pythia.h"

#include <atomic>
#include <cmath>
#include <map>
#include <memory>
#include <mutex>
#include <utility>
#include <vector>

namespace Inproc {

    struct Xsec {
        double pb = 0, errPb = 0;
    };

    class Stamper {
      public:
        // On the instance's own thread, right after it converted `event`.
        void stamp(Pythia8::Pythia& instance, HepMC3::GenEvent& event) {
            event.set_event_number(static_cast<int>(numbered_++));   // from 0, as App_Pythia
            std::lock_guard<std::mutex> guard(lock_);
            if (!runInfo_) runInfo_ = event.run_info();
            event.set_run_info(runInfo_);                            // one run info for Rivet
            latest_[&instance] = of(instance);
            const auto cs = event.cross_section();
            if (!cs) return;
            if (latest_.size() > 1) {                                // L2
                const Xsec xs = combine(latest_);
                cs->set_cross_section(xs.pb, xs.errPb);
            }
            last_.clear();                                           // L28
            for (size_t i = 0; i < cs->xsecs().size() && i < cs->xsec_errs().size(); ++i)
                last_.emplace_back(cs->xsecs()[i], cs->xsec_errs()[i]);
        }

        // Per weight, {σ, error} in pb, as Rivet would read them from the last event stamped.
        std::vector<std::pair<double, double>> last() const {
            std::lock_guard<std::mutex> guard(lock_);
            return last_;
        }

        // The running combination, for the status line.
        Xsec running() const {
            std::lock_guard<std::mutex> guard(lock_);
            return combine(latest_);
        }

        // From every instance's numbers after the run: the report's σ, which is App_Pythia's sidecar's.
        static Xsec final(const std::vector<Pythia8::Pythia*>& instances) {
            if (instances.size() == 1)
                return {instances.front()->info.sigmaGen() * 1e9, instances.front()->info.sigmaErr() * 1e9};
            std::map<const Pythia8::Pythia*, Instance> all;
            for (Pythia8::Pythia* instance : instances) all[instance] = of(*instance);
            return combine(all);
        }

      private:
        struct Instance {
            double weightSum = 0, sigmaMb = 0, errorMb = 0;
        };

        static Instance of(Pythia8::Pythia& instance) {
            return {instance.info.weightSum(), instance.info.sigmaGen(), instance.info.sigmaErr()};
        }

        static Xsec combine(const std::map<const Pythia8::Pythia*, Instance>& instances) {   // L1, mb → pb
            double weight = 0, value = 0, variance = 0;
            for (const auto& [_, in] : instances) {
                if (in.weightSum <= 0) continue;                     // it has said nothing yet
                weight += in.weightSum;
                value += in.weightSum * in.sigmaMb;
                variance += std::pow(in.weightSum * in.errorMb, 2);
            }
            if (weight <= 0) return {};
            return {value / weight * 1e9, std::sqrt(variance) / weight * 1e9};
        }

        mutable std::mutex lock_;
        std::atomic<long> numbered_{0};
        std::shared_ptr<HepMC3::GenRunInfo> runInfo_;               // under lock_
        std::map<const Pythia8::Pythia*, Instance> latest_;          // under lock_
        std::vector<std::pair<double, double>> last_;                // under lock_
    };

}  // namespace Inproc
