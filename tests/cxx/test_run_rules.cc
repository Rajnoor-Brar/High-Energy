// The decisions inside the run loop, checked without a generator: the chunk rule (D-Q2), the σ
// combination (D-Q1) and the smallest analyzer.
//
// Why these and not the loop itself: everything else in `Run::Loop` is order — configure, init, start,
// chunk, finish — and ordering is checked end to end by `tests/python/run/test_hep_run.py`, which runs
// the real binary. What cannot be checked that way is arithmetic at sizes no test run reaches (a
// 10⁶-event chunk, an instance that generated nothing), so it is checked here.

#include <cmath>
#include <cstdint>

#include "Analyzer.hh"
#include "Source/Types.hh"
#include "check.hh"

namespace {

// D-Q2: round **up** to a whole number of workers. Rounding down would leave a worker without a
// `next()` call in the last chunk and change the event set, which is the whole point of the rule.
void chunkRule() {
    CHECK_EQ(Source::chunkFor(20, 2), std::int64_t{20});      // already a multiple
    CHECK_EQ(Source::chunkFor(21, 2), std::int64_t{22});      // rounded up
    CHECK_EQ(Source::chunkFor(1, 8), std::int64_t{8});        // never smaller than the thread count
    CHECK_EQ(Source::chunkFor(7, 3), std::int64_t{9});
    CHECK_EQ(Source::chunkFor(100000, 20), std::int64_t{100000});
    CHECK_EQ(Source::chunkFor(100001, 20), std::int64_t{100020});

    // Degenerate inputs still give a usable chunk, because a zero would be an infinite loop.
    CHECK_EQ(Source::chunkFor(0, 4), std::int64_t{4});
    CHECK_EQ(Source::chunkFor(-5, 4), std::int64_t{4});
    CHECK_EQ(Source::chunkFor(10, 0), std::int64_t{10});
    CHECK_EQ(Source::chunkFor(10, -1), std::int64_t{10});

    // The property the decision rests on: a chunk is always a whole number of workers, so every
    // worker is asked the same number of times.
    for (int threads = 1; threads <= 16; ++threads)
        for (std::int64_t wanted = 1; wanted <= 200; ++wanted) {
            const std::int64_t chunk = Source::chunkFor(wanted, threads);
            CHECK(chunk % threads == 0);
            CHECK(chunk >= wanted);
            CHECK(chunk < wanted + threads);      // rounded up, not padded
        }
}

// D-Q1: σ is the weighted mean of the instances and its error adds in quadrature, because
// PythiaParallel reports σ but no error of its own.
void xsecCombination() {
    {   // one instance: the weighting cannot change anything, only the units (mb → pb)
        Source::Combine combine;
        combine.add(1000.0, 7.0e-5, 2.0e-6);
        const Source::Xsec found = combine.result();
        CHECK(found.known);
        CHECK(std::abs(found.value_pb - 7.0e4) < 1e-6);
        CHECK(std::abs(found.error_pb - 2.0e3) < 1e-6);
    }
    {   // two equally weighted instances: the mean of σ, and the error falls by √2
        Source::Combine combine;
        combine.add(500.0, 6.0e-5, 2.0e-6);
        combine.add(500.0, 8.0e-5, 2.0e-6);
        const Source::Xsec found = combine.result();
        CHECK(std::abs(found.value_pb - 7.0e4) < 1e-6);
        CHECK(std::abs(found.error_pb - 2.0e3 / std::sqrt(2.0)) < 1e-6);
        CHECK_EQ(found.weight_sum, 1000.0);
    }
    {   // unequal weights: the heavier instance pulls σ towards itself
        Source::Combine combine;
        combine.add(900.0, 1.0e-5, 0.0);
        combine.add(100.0, 2.0e-5, 0.0);
        CHECK(std::abs(combine.result().value_pb - 1.1e4) < 1e-6);
    }
    {   // an instance that generated nothing contributes nothing and does not divide by zero
        Source::Combine combine;
        combine.add(0.0, 1.0e-5, 1.0e-6);
        CHECK(!combine.result().known);
        CHECK_EQ(combine.result().value_pb, 0.0);
        combine.add(10.0, 1.0e-5, 1.0e-6);
        CHECK(combine.result().known);
        CHECK(std::abs(combine.result().value_pb - 1.0e4) < 1e-6);
    }
    {   // nothing at all: "unknown", not "zero". A summary must be able to say it has no σ.
        CHECK(!Source::Combine().result().known);
    }
}

// The smallest analyzer, which is also the interface's documentation: it must count what the loop feeds it
// and carry the event weight through.
void countingAnalyzer() {
    Analyzer::Count analyzer;
    CHECK_EQ(analyzer.name(), std::string{"count"});
    CHECK(!analyzer.needs().hepmc);          // a counting run must not pay for a GenEvent
    CHECK(!analyzer.needs().pythia);
    CHECK(analyzer.concurrency() == Analyzer::Concurrency::Serial);
    CHECK_EQ(analyzer.events(), std::int64_t{0});
    CHECK(analyzer.outputs().empty());

    for (std::int64_t index = 0; index < 5; ++index) {
        Events::View view(nullptr, index, static_cast<int>(index % 2));
        view.weights().values.assign(1, 2.0);
        analyzer.event(view);
    }
    CHECK_EQ(analyzer.events(), std::int64_t{5});
    CHECK_EQ(analyzer.weight(), 10.0);

    // The optional parts of the interface must be safe to call on an analyzer that implements none of them.
    analyzer.start(Core::Beams{}, 5);
    analyzer.checkpoint(5);
    analyzer.finish(Core::RunRecord{});
    CHECK_EQ(analyzer.events(), std::int64_t{5});
}

// A view with no Pythia behind it is legal (a store replay has none) and must not pretend otherwise.
void emptyView() {
    Events::View view;
    CHECK(!view.hasPythia());
    CHECK(view.pythia() == nullptr);
    CHECK_EQ(view.index(), std::int64_t{0});
    CHECK_EQ(view.weights().nominal(), 1.0);      // an unweighted event weighs one, not zero

    Events::View borrowed(nullptr, 7, 3);
    CHECK_EQ(borrowed.index(), std::int64_t{7});
    CHECK_EQ(borrowed.worker(), 3);
    borrowed.weights().values.clear();
    CHECK_EQ(borrowed.weights().nominal(), 1.0);  // and an empty weight list still weighs one
}

// Worker and slot are two different numbers, and confusing them is how a sharded run corrupts either
// a store's layout or an analysis handler (05 §3). A generator's are the same; a replay's are not.
void workerAndSlot() {
    {   // a generator: one instance per thread, so the event's origin is also who carries it
        Events::View generated(nullptr, 0, 2);
        CHECK_EQ(generated.worker(), 2);
        CHECK_EQ(generated.slot(), 2);
    }
    {   // a replay: shard 5 popped by consumer 1
        Events::View replayed(nullptr, 0, 5, 1);
        CHECK_EQ(replayed.worker(), 5);           // the store keeps its layout
        CHECK_EQ(replayed.slot(), 1);             // the analysis handler is the consumer's
    }
    {   // a default-constructed view is slot 0, not a negative index into somebody's vector
        Events::View empty;
        CHECK_EQ(empty.worker(), 0);
        CHECK_EQ(empty.slot(), 0);
    }
    {   // a source that does not track workers passes -1; a slot must still be a valid index
        Events::View unknown(nullptr, 0, -1);
        CHECK_EQ(unknown.worker(), -1);
        CHECK_EQ(unknown.slot(), 0);
    }
    {   // and it can be set after the fact, which is what a consumer thread does
        Events::View moved(nullptr, 0, 4);
        moved.slot(1);
        CHECK_EQ(moved.worker(), 4);
        CHECK_EQ(moved.slot(), 1);
    }
}

}  // namespace

int main() {
    chunkRule();
    xsecCombination();
    countingAnalyzer();
    emptyView();
    workerAndSlot();
    return check::finish("run_rules");
}
