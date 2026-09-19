// Store::Queue — the bounded queue between reader threads and the event loop (11 §4).
//
// Ported from `legacy/utils/Probe/Lifecycle.hh`, and the three properties worth testing are the ones
// that are wrong in most hand-rolled versions: a full queue blocks instead of growing, a stop wakes
// everyone at once, and "every producer finished" does not mean "stop now" — the consumer must drain
// what is left, or the tail of the last shard disappears without a word.

#include <atomic>
#include <chrono>
#include <thread>
#include <vector>

#include "Store/Queue.hh"
#include "check.hh"

namespace {

using Queue = Store::Queue<int>;

void oneProducerOneConsumer() {
    Queue queue(4, 1);
    std::vector<int> seen;
    std::thread producer([&] {
        for (int value = 0; value < 20; ++value) queue.push(value);
        queue.finish();
    });
    int value = 0;
    while (queue.pop(value)) seen.push_back(value);
    producer.join();

    CHECK_EQ(seen.size(), std::size_t{20});
    CHECK_EQ(seen.front(), 0);
    CHECK_EQ(seen.back(), 19);
    CHECK_EQ(queue.pushed(), 20LL);
    CHECK_EQ(queue.popped(), 20LL);
}

// The bound is the memory a replay is allowed to use for events in flight: a producer that runs
// ahead must block, not allocate.
void aFullQueueBlocksTheProducer() {
    Queue queue(2, 1);
    std::atomic<int> pushed{0};
    std::thread producer([&] {
        for (int value = 0; value < 5; ++value) {
            queue.push(value);
            pushed.fetch_add(1);
        }
        queue.finish();
    });

    // Give it every chance to overrun the bound.
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    CHECK(pushed.load() <= 3);                 // two in the queue, one waiting to be accepted
    CHECK(queue.size() <= 2);

    int value = 0;
    int drained = 0;
    while (queue.pop(value)) drained += 1;
    producer.join();
    CHECK_EQ(drained, 5);
}

// The tail of the last shard: a consumer must keep draining after the producers have gone.
void finishingIsNotEmptying() {
    Queue queue(8, 2);
    queue.push(1);
    queue.push(2);
    queue.finish();
    queue.finish();                            // both producers are done, two items are waiting

    int value = 0;
    CHECK(queue.pop(value) && value == 1);
    CHECK(queue.pop(value) && value == 2);
    CHECK(!queue.pop(value));                  // only now
    CHECK_EQ(queue.finishedProducers(), 2);
}

// Stopping has to reach a consumer that is waiting and a producer that is blocked, at once.
void stoppingWakesEveryone() {
    Queue queue(1, 1);
    std::atomic<bool> consumer_returned{false};
    std::atomic<bool> producer_returned{false};

    queue.push(1);                             // the queue is now full
    std::thread producer([&] {
        queue.push(2);                         // blocks: no room
        producer_returned = true;
    });
    std::thread consumer([&] {
        int value = 0;
        while (queue.pop(value)) {}            // drains 1, then waits
        consumer_returned = true;
    });

    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    queue.stop();
    producer.join();
    consumer.join();

    CHECK(producer_returned.load());
    CHECK(consumer_returned.load());
    CHECK(queue.stopped());
    CHECK(!queue.push(3));                     // and it stays stopped
}

void severalProducersAllArrive() {
    const int producers = 4;
    const int each = 250;
    Queue queue(16, producers);
    std::vector<std::thread> threads;
    for (int producer = 0; producer < producers; ++producer)
        threads.emplace_back([&, producer] {
            for (int value = 0; value < each; ++value) queue.push(producer * each + value);
            queue.finish();
        });

    int drained = 0;
    int value = 0;
    while (queue.pop(value)) drained += 1;
    for (std::thread& thread : threads) thread.join();

    CHECK_EQ(drained, producers * each);
    CHECK_EQ(queue.pushed(), static_cast<long long>(producers * each));
}

}  // namespace

int main() {
    oneProducerOneConsumer();
    aFullQueueBlocksTheProducer();
    finishingIsNotEmptying();
    stoppingWakesEveryone();
    severalProducersAllArrive();
    return check::finish("store_queue");
}
