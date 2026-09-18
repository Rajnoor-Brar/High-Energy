#pragma once

// ── Source/Types.hh ──────────────────────────────────────────────────────────
// What a source reports, and the two pieces of arithmetic P2-S02 settled by measurement.
//
// They live here, apart from `Source/Pythia.hh`, because they are decisions rather than plumbing and a
// test should be able to check them without linking a generator:
//
//   * `chunkFor` — D-Q2. A chunk is rounded **up** to a whole number of workers, so every worker gets
//     the same number of `next()` calls per chunk and a chunked run draws the same event set as an
//     unchunked one. Rounding down would leave a worker idle in the last chunk and change the sequence.
//   * `Combine` — D-Q1. `PythiaParallel` reports σ but no error, so the instances are combined by
//     weight: σ = Σwᵢσᵢ / Σwᵢ, and the errors add in quadrature, err = √(Σ(wᵢerrᵢ)²) / Σwᵢ. Pythia
//     works in mb; everything above this line is in pb.

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace Source {

    inline constexpr double kMillibarnToPicobarn = 1.0e9;

    // A cross section with an error, in the units the rest of the toolkit uses (pb).
    struct Xsec {
        double value_pb = 0.0;
        double error_pb = 0.0;
        double weight_sum = 0.0;
        bool known = false;
    };

    // D-Q2: the chunk that keeps a chunked run's event set identical to an unchunked one.
    inline std::int64_t chunkFor(std::int64_t wanted, int threads) {
        const std::int64_t workers = std::max<std::int64_t>(1, threads);
        if (wanted <= 0) return workers;
        const std::int64_t rounded = ((wanted + workers - 1) / workers) * workers;
        return std::max(rounded, workers);
    }

    // D-Q1: weighted mean of the instances, errors in quadrature. `add` takes one instance's
    // (weight sum, σ, σ error) in mb, as `Pythia8::Info` reports them.
    class Combine {
      public:
        void add(double weight_sum, double sigma_mb, double error_mb) {
            if (weight_sum <= 0.0) return;          // an instance that generated nothing says nothing
            weight_ += weight_sum;
            value_ += weight_sum * sigma_mb;
            const double term = weight_sum * error_mb;
            variance_ += term * term;
        }

        Xsec result() const {
            Xsec found;
            found.weight_sum = weight_;
            if (weight_ <= 0.0) return found;
            found.value_pb = value_ / weight_ * kMillibarnToPicobarn;
            found.error_pb = std::sqrt(variance_) / weight_ * kMillibarnToPicobarn;
            found.known = true;
            return found;
        }

      private:
        double weight_ = 0.0;
        double value_ = 0.0;
        double variance_ = 0.0;
    };

}  // namespace Source
