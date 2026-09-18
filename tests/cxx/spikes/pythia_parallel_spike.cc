// P2-S02 — measurements behind D-Q1, D-Q2 and D-SEEDS. A one-off spike, not a test: it is kept so the
// numbers in the step log can be reproduced.
//
//   Build: g++ -O2 -std=c++17 tests/cxx/spikes/pythia_parallel_spike.cc -o spike \
//              $(pythia8-config --cxxflags --ldflags)
//   Run:   ./spike [threads] [events] [chunks]      (defaults 4 4000 4)
//
// Questions:
//   Q2      Is the cross section consistent when run() is called k times after one init(), and are the
//           events the same as one run(k·n)?
//   Q1      PythiaParallel exposes sigmaGen() and weightSum() but no error. Can the error be combined
//           from the instances via foreach, and does it agree with a serial run's stat()?
//   D-SEEDS Does Parallelism:seeds reach the instances, and do repeated run() calls continue their
//           streams rather than restarting them?

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"

#include <cmath>
#include <cstdlib>
#include <cstdio>
#include <string>
#include <vector>

namespace {

int kThreads = 4;
long kEvents = 4000;
int kChunks = 4;
constexpr int kSeedBase = 700001;      // an identity block, as hekit would hand it over
std::vector<int> kSeeds;

void parse(int argc, char* argv[]) {
  if (argc > 1) kThreads = std::atoi(argv[1]);
  if (argc > 2) kEvents = std::atol(argv[2]);
  if (argc > 3) kChunks = std::atoi(argv[3]);
  kSeeds.clear();
  for (int index = 0; index < kThreads; ++index) kSeeds.push_back(kSeedBase + index);
}

// A cheap but non-trivial process: jets at moderate pT, no MPI and no hadronisation, so the spike runs
// in seconds while still exercising the cross-section machinery.
void configure(Pythia8::Settings& settings) {
  settings.readString("Beams:idA = 2212");
  settings.readString("Beams:idB = 2212");
  settings.readString("Beams:eCM = 200.");
  settings.readString("HardQCD:all = on");
  settings.readString("PhaseSpace:pTHatMin = 20.");
  settings.readString("PartonLevel:MPI = off");
  settings.readString("HadronLevel:all = off");
  settings.readString("Print:quiet = on");
  settings.readString("Next:numberCount = 0");
}

struct Tally {
  long events = 0;
  // An integer checksum: a floating-point sum would differ in its last bits purely because the
  // callback order across chunks differs, which says nothing about the events themselves.
  long long pthat_sum = 0;

  void add(double pthat) {
    events += 1;
    pthat_sum += std::llround(pthat * 1000.0);
  }
};

// sum w_i sigma_i / sum w_i, with the errors combined as independent (each instance has its own stream)
struct Merged {
  double sigma = 0.0;
  double error = 0.0;
  double weight_sum = 0.0;
  long accepted = 0;
};

Merged merge_instances(Pythia8::PythiaParallel& parallel) {
  Merged merged;
  double variance = 0.0;
  parallel.foreach([&](Pythia8::Pythia* instance) {
    const double weight = instance->info.weightSum();
    merged.weight_sum += weight;
    merged.sigma += weight * instance->info.sigmaGen();
    variance += (weight * instance->info.sigmaErr()) * (weight * instance->info.sigmaErr());
    merged.accepted += instance->info.nAccepted();
  });
  if (merged.weight_sum > 0.0) {
    merged.sigma /= merged.weight_sum;
    merged.error = std::sqrt(variance) / merged.weight_sum;
  }
  return merged;
}

void report_seeds(Pythia8::PythiaParallel& parallel, const char* when) {
  std::string seeds;
  parallel.foreach([&](Pythia8::Pythia* instance) {
    seeds += (seeds.empty() ? "" : ", ") + std::to_string(instance->settings.mode("Random:seed"));
  });
  std::printf("  seeds %-18s %s\n", when, seeds.c_str());
}

}  // namespace

int main(int argc, char* argv[]) {
  parse(argc, argv);
  std::printf("## threads %d, events %ld, chunks %d\n", kThreads, kEvents, kChunks);
  std::printf("== A: one run(%ld) on %d threads\n", kEvents, kThreads);
  Tally single;
  Pythia8::PythiaParallel one;
  configure(one.settings);
  one.settings.mode("Parallelism:numThreads", kThreads);
  one.settings.mvec("Parallelism:seeds", kSeeds);
  if (!one.init()) return 1;
  report_seeds(one, "after init");
  const std::vector<long> attempts = one.run(kEvents, [&](Pythia8::Pythia* instance) {
    single.add(instance->info.pTHat());
  });
  long attempted = 0;
  for (long count : attempts) attempted += count;
  const Merged merged_single = merge_instances(one);
  std::printf("  attempts %ld  processed %ld  sigma %.8g mb  weightSum %.8g\n",
              attempted, single.events, one.sigmaGen(), one.weightSum());
  std::printf("  merged from instances: sigma %.8g +- %.3g mb (%.3g %%)  accepted %ld\n",
              merged_single.sigma, merged_single.error,
              100.0 * merged_single.error / merged_single.sigma, merged_single.accepted);
  std::printf("  pTHat checksum %lld\n", single.pthat_sum);

  std::printf("== B: %d x run(%ld) after one init()\n", kChunks, kEvents / kChunks);
  Tally chunked;
  Pythia8::PythiaParallel many;
  configure(many.settings);
  many.settings.mode("Parallelism:numThreads", kThreads);
  many.settings.mvec("Parallelism:seeds", kSeeds);
  if (!many.init()) return 1;
  for (int chunk = 1; chunk <= kChunks; ++chunk) {
    // the remainder goes into the last chunk, so the totals match a single run exactly
    const long size = kEvents / kChunks + (chunk == kChunks ? kEvents % kChunks : 0);
    many.run(size, [&](Pythia8::Pythia* instance) {
      chunked.add(instance->info.pTHat());
    });
    const Merged merged_chunk = merge_instances(many);
    std::printf("  chunk %d of %ld: processed %ld  sigma %.8g  weightSum %.8g  merged %.8g +- %.3g\n",
                chunk, size, chunked.events, many.sigmaGen(), many.weightSum(),
                merged_chunk.sigma, merged_chunk.error);
  }
  report_seeds(many, "after chunks");
  std::printf("  pTHat checksum %lld\n", chunked.pthat_sum);
  std::printf("  identical to A? events %s  sigma %s  checksum %s\n",
              single.events == chunked.events ? "yes" : "NO",
              one.sigmaGen() == many.sigmaGen() ? "yes" : "NO",
              single.pthat_sum == chunked.pthat_sum ? "yes" : "NO");

  std::printf("== C: serial reference, same total events, seed %d\n", kSeeds[0]);
  Pythia8::Pythia serial;
  configure(serial.settings);
  serial.settings.mode("Random:seed", kSeeds[0]);
  serial.settings.flag("Random:setSeed", true);
  if (!serial.init()) return 1;
  long serial_events = 0;
  for (long event = 0; event < kEvents; ++event)
    if (serial.next()) serial_events += 1;
  serial.stat();
  std::printf("  processed %ld  sigma %.8g +- %.3g mb (%.3g %%)\n", serial_events,
              serial.info.sigmaGen(), serial.info.sigmaErr(),
              100.0 * serial.info.sigmaErr() / serial.info.sigmaGen());
  const double difference = merged_single.sigma - serial.info.sigmaGen();
  const double combined = std::sqrt(merged_single.error * merged_single.error +
                                    serial.info.sigmaErr() * serial.info.sigmaErr());
  std::printf("  parallel - serial = %.3g mb = %.2f sigma\n", difference,
              combined > 0.0 ? difference / combined : 0.0);

  if (kThreads != 4) return 0;      // parts D and E are one-off checks, not per-configuration
  std::printf("== D: a seed list that does not match the thread count\n");
  Pythia8::PythiaParallel mismatched;
  configure(mismatched.settings);
  mismatched.settings.mode("Parallelism:numThreads", kThreads);
  mismatched.settings.mvec("Parallelism:seeds", std::vector<int>{1, 2, 3});
  const bool started = mismatched.init();
  std::printf("  init with %d seeds for %d threads: %s\n", 3, kThreads,
              started ? "SUCCEEDED (the planner cannot rely on this failing)" : "failed, as documented");

  std::printf("== E: threads = 0 (all cores), seeds left to Random:seed\n");
  Pythia8::PythiaParallel automatic;
  configure(automatic.settings);
  automatic.settings.mode("Parallelism:numThreads", 0);
  automatic.settings.flag("Random:setSeed", true);
  automatic.settings.mode("Random:seed", kSeeds[0]);
  if (automatic.init()) {
    std::printf("  resolved threads %d\n", automatic.settings.mode("Parallelism:numThreads"));
    report_seeds(automatic, "after init");
  }
  return 0;
}
