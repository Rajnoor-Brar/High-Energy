// What the results layer promises a module (P8-S01, 05 §5).
//
// Three things, and the third is the one the whole design rests on:
//
//   1. **booking validates**, at the only moment when a mistake is still cheap;
//   2. **merging adds**, so k workers' clones give what one worker would have had — which is what
//      makes a sharded run's answer equal a serial one's;
//   3. **scaling is only reachable from `Final`**, so "scaled during the run" and "scaled twice"
//      are not mistakes a module can make. That one is checked by the API's shape rather than by an
//      assertion: `Results::Worker` has no `scale`, and this file would not compile if it did.

#include <cmath>
#include <vector>

#include "Core/Errors.hh"
#include "Results/Booker.hh"
#include "Results/Merge.hh"
#include "Results/Worker.hh"
#include "check.hh"

namespace {

// Declare-time validation. Every one of these would otherwise be found after a run rather than
// before one, and two of them keep nothing at all.
void bookingRules() {
    Results::Booker booker("/toy");

    const Results::Handle histo = booker.histo1D("h", 10, 0.0, 1.0);
    const Results::Handle counter = booker.counter("c");
    CHECK_EQ(histo, Results::Handle{0});
    CHECK_EQ(counter, Results::Handle{1});
    CHECK_EQ(booker.declarations().size(), std::size_t{2});
    CHECK_EQ(booker.path(booker.declarations()[0]), std::string{"/toy/h"});

    // A name used twice would silently overwrite the first in the YODA.
    CHECK_THROWS(booker.histo1D("h", 10, 0.0, 1.0), Core::Error);
    CHECK_THROWS(booker.counter("c"), Core::Error);
    // A path is the module's to give, not the object's.
    CHECK_THROWS(booker.histo1D("a/b", 10, 0.0, 1.0), Core::Error);
    CHECK_THROWS(booker.histo1D("", 10, 0.0, 1.0), Core::Error);
    // No bins keeps nothing; reversed edges keep nothing either, and look fine until you plot them.
    CHECK_THROWS(booker.histo1D("zero", 0, 0.0, 1.0), Core::Error);
    CHECK_THROWS(booker.histo1D("backwards", 10, 1.0, 0.0), Core::Error);
    CHECK_THROWS(booker.histo2D("bad_y", 10, 0.0, 1.0, 0, 0.0, 1.0), Core::Error);
    // A counter has no axis, so neither rule applies to it.
    booker.counter("fine");
}

// The property that makes sharding sound: clones add.
void mergingAdds() {
    Results::Booker booker("/toy");
    const Results::Handle histo = booker.histo1D("h", 4, 0.0, 4.0);
    const Results::Handle profile = booker.profile1D("p", 4, 0.0, 4.0);
    const Results::Handle counter = booker.counter("c");
    const Results::Handle histo2d = booker.histo2D("h2", 2, 0.0, 2.0, 2, 0.0, 2.0);

    std::vector<Results::Slot> one = Results::clonesOf(booker);
    std::vector<Results::Slot> two = Results::clonesOf(booker);
    std::vector<Results::Slot> together = Results::clonesOf(booker);

    Results::Worker first(one, 0);
    Results::Worker second(two, 1);
    Results::Worker both(together, 0);

    // The same fills, split between two workers and then all into one.
    for (int index = 0; index < 10; ++index) {
        const double value = 0.5 + (index % 4);
        Results::Worker& worker = (index % 2 == 0) ? first : second;
        worker.fill(histo, value, 2.0);
        worker.fill(profile, value, value * 3.0, 2.0);
        worker.count(counter, 2.0);
        worker.fill(histo2d, 0.5, 1.5, 2.0);

        both.fill(histo, value, 2.0);
        both.fill(profile, value, value * 3.0, 2.0);
        both.count(counter, 2.0);
        both.fill(histo2d, 0.5, 1.5, 2.0);
    }

    Results::merge(one, two);

    CHECK(std::abs(one[histo].histo1d->sumW() - together[histo].histo1d->sumW()) < 1e-12);
    CHECK(std::abs(one[counter].counter->sumW() - together[counter].counter->sumW()) < 1e-12);
    CHECK(std::abs(one[histo2d].histo2d->sumW() - together[histo2d].histo2d->sumW()) < 1e-12);
    CHECK_EQ(one[counter].counter->sumW(), 20.0);
    // A profile is a mean, and a mean of the same entries is the same mean however they were split.
    CHECK(std::abs(one[profile].profile1d->sumW() - together[profile].profile1d->sumW()) < 1e-12);
}

// Merging two sets that did not come from the same booker is a bug, not a recoverable state.
void mergingRefusesMismatches() {
    Results::Booker one("/a");
    one.histo1D("h", 4, 0.0, 4.0);
    Results::Booker two("/b");
    two.histo1D("h", 4, 0.0, 4.0);
    two.counter("c");

    std::vector<Results::Slot> left = Results::clonesOf(one);
    std::vector<Results::Slot> right = Results::clonesOf(two);
    CHECK_THROWS(Results::merge(left, right), Core::Error);
}

// Filling an object with the wrong number of coordinates is caught, not silently ignored.
void fillingIsChecked() {
    Results::Booker booker("/toy");
    const Results::Handle histo = booker.histo1D("h", 4, 0.0, 4.0);
    const Results::Handle profile = booker.profile1D("p", 4, 0.0, 4.0);
    const Results::Handle counter = booker.counter("c");

    std::vector<Results::Slot> slots = Results::clonesOf(booker);
    Results::Worker worker(slots, 0);

    CHECK_THROWS(worker.fill(histo, 1.0, 2.0, 1.0), Core::Error);      // a 1D histogram takes one coordinate
    CHECK_THROWS(worker.fill(profile, 1.0), Core::Error);              // a profile takes two
    CHECK_THROWS(worker.count(histo), Core::Error);                    // only a counter counts
    CHECK_THROWS(worker.fill(Results::Handle{99}, 1.0), Core::Error);  // never booked
    worker.fill(counter, 3.0);                            // a counter's "x" is its weight
    CHECK_EQ(slots[counter].counter->sumW(), 3.0);
}

// The scaling contract: `Final` knows σ and ΣW, and is the only thing that can scale.
void scalingHappensOnceAtTheEnd() {
    Results::Booker booker("/toy");
    const Results::Handle histo = booker.histo1D("h", 4, 0.0, 4.0);
    std::vector<Results::Slot> slots = Results::clonesOf(booker);

    Results::Worker worker(slots, 0);
    for (int index = 0; index < 10; ++index) worker.fill(histo, 1.5, 2.0);
    CHECK_EQ(slots[histo].histo1d->sumW(), 20.0);         // raw weights, as filled

    Results::Final results(slots, /*xsec_pb=*/100.0, /*sum_of_weights=*/20.0, /*events=*/10);
    CHECK_EQ(results.crossSection(), 100.0);
    CHECK_EQ(results.sumOfWeights(), 20.0);
    CHECK_EQ(results.events(), 10LL);
    CHECK_EQ(results.perEventCrossSection(), 5.0);

    results.normalise(histo);
    // Σw × (σ / Σw) = σ: the integral of a normalised histogram *is* the cross-section.
    CHECK(std::abs(slots[histo].histo1d->sumW() - 100.0) < 1e-9);

    results.scale(histo, 0.5);
    CHECK(std::abs(slots[histo].histo1d->sumW() - 50.0) < 1e-9);
    CHECK_THROWS(results.scale(Results::Handle{99}, 2.0), Core::Error);
}

// A run with no events must not divide by zero when it normalises.
void anEmptyRunNormalisesToNothing() {
    Results::Booker booker("/toy");
    const Results::Handle histo = booker.histo1D("h", 4, 0.0, 4.0);
    std::vector<Results::Slot> slots = Results::clonesOf(booker);

    Results::Final results(slots, /*xsec_pb=*/100.0, /*sum_of_weights=*/0.0, /*events=*/0);
    CHECK_EQ(results.perEventCrossSection(), 0.0);
    results.normalise(histo);                             // must not be inf or nan
    CHECK_EQ(slots[histo].histo1d->sumW(), 0.0);
}

}  // namespace

int main() {
    bookingRules();
    mergingAdds();
    mergingRefusesMismatches();
    fillingIsChecked();
    scalingHappensOnceAtTheEnd();
    anEmptyRunNormalisesToNothing();
    return check::finish("results_objects");
}
