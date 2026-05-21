#include <chrono>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include "test_assert.hh"

#include "Record.hh"
#include "TH1.h"
#include "TFile.h"

namespace {
    enum class HistId : std::size_t { Values, Missing };
    enum class OtherHistId : std::size_t { Values };

    void openWriter(Record::Writer& writer, const std::string& stem) {
        std::filesystem::create_directories("output/test_writer/checkpoints");

        Record::Paths paths;
        paths.outName = ("output/test_writer/" + stem + ".root").c_str();
        paths.checkpointOutName = ("output/test_writer/checkpoints/" + stem + "_checkpoint.root").c_str();
        paths.logName = ("output/test_writer/" + stem + ".log").c_str();
        paths.runStatName = ("output/test_writer/" + stem + "_runstat.log").c_str();
        paths.threadStatDirectory = "output/test_writer/threads/";
        paths.fileTitle = stem.c_str();

        Record::HistConfig hist;
        hist.histScale = 1.0;
        hist.binCount = 10;

        writer.open(paths, hist, Record::Meta::Record{});
    }
}

int main() {
    std::cout << "── test_record_writer ───────────────────────────────────────\n";

    TEST_EQ(RootUtil::leafListSuffix(RootUtil::DataType::Double), std::string("D"));
    TEST_NEAR(RootUtil::toDouble(Record::Value{std::int32_t{7}}), 7.0, 1e-12);
    bool stringRejected = false;
    try {
        (void)RootUtil::toDouble(Record::Value{std::string("x")});
    } catch (const std::runtime_error&) {
        stringRejected = true;
    }
    TEST_TRUE(stringRejected);
    TEST_PASS("RootUtil leaf suffix and numeric conversion");

    const Record::RecordKey keyA = Record::keyOf(HistId::Values);
    const Record::RecordKey keyB = Record::keyOf(OtherHistId::Values);
    TEST_FALSE(keyA == keyB);
    std::unordered_map<Record::RecordKey, int, Record::RecordKeyHash> keyed;
    keyed[keyA] = 1;
    keyed[keyB] = 2;
    TEST_EQ(keyed[keyA], 1);
    TEST_EQ(keyed[keyB], 2);
    TEST_PASS("RecordKey separates enum domains");

    Record::BranchRecord branch;
    branch.name = "x";
    branch.type = Record::DataType::Double;
    branch.buffer = Record::makeBranchBuffer(branch.type);
    Record::setBranchBuffer(branch, Record::Value{2.5});
    bool wrongValueRejected = false;
    try {
        Record::setBranchBuffer(branch, Record::Value{std::int32_t{2}});
    } catch (const std::runtime_error&) {
        wrongValueRejected = true;
    }
    TEST_TRUE(wrongValueRejected);
    TEST_PASS("BranchBuffer validates value type");

    {
        Record::Writer writer;
        openWriter(writer, "declaration_errors");
        writer.declareHist1D(HistId::Values, "values", "values", 10, 0.0, 10.0);
        bool duplicateRejected = false;
        try {
            writer.declareHist1D(HistId::Values, "values2", "values2", 10, 0.0, 10.0);
        } catch (const std::runtime_error&) {
            duplicateRejected = true;
        }
        TEST_TRUE(duplicateRejected);

        writer.start();
        bool lateDeclarationRejected = false;
        try {
            writer.declareHist1D(HistId::Missing, "late", "late", 10, 0.0, 10.0);
        } catch (const std::runtime_error&) {
            lateDeclarationRejected = true;
        }
        TEST_TRUE(lateDeclarationRejected);
        writer.finish(0);
        TEST_PASS("Writer declaration validation");
    }

    {
        std::string outputPath;
        {
            Record::Writer writer;
            openWriter(writer, "queued_fills");
            writer.setQueueCapacity(2);
            writer.declareHist1D(HistId::Values, "values", "values", 10, 0.0, 10.0);
            writer.start();

            std::vector<std::thread> producers;
            for (int t = 0; t < 4; ++t) {
                producers.emplace_back([&writer] {
                    for (int i = 0; i < 25; ++i)
                        writer.fillHist1D(HistId::Values, Record::Value{1.0});
                });
            }
            for (auto& producer : producers) producer.join();

            writer.checkpoint(100);
            outputPath = writer.paths().outName.Data();
            writer.finish(100);
        }

        std::unique_ptr<TFile> out(TFile::Open(outputPath.c_str(), "READ"));
        TEST_TRUE(out && !out->IsZombie());
        auto* hist = dynamic_cast<TH1*>(out->Get("values"));
        TEST_TRUE(hist != nullptr);
        const int entries = static_cast<int>(hist->GetEntries());
        TEST_EQ(entries, 100);
        TEST_PASS("Writer queue drains concurrent producers before finish");
    }

    {
        Record::Writer writer;
        openWriter(writer, "worker_exception");
        writer.declareHist1D(HistId::Values, "values", "values", 10, 0.0, 10.0);
        writer.start();
        writer.fillHist1D(HistId::Missing, Record::Value{1.0});

        bool finishRejected = false;
        try {
            writer.finish(1);
        } catch (const std::runtime_error&) {
            finishRejected = true;
        }
        TEST_TRUE(finishRejected);
        TEST_PASS("Worker exceptions propagate to finish");
    }

    {
        // Checkpoint while fill queue is under back-pressure: use a tiny
        // queue capacity with concurrent producers so the queue stays near-full.
        // checkpoint() must complete without deadlock.
        Record::Writer writer;
        openWriter(writer, "checkpoint_backpressure");
        writer.setQueueCapacity(2);
        writer.setRecordThreadCount(2);
        writer.declareHist1D(HistId::Values, "values", "values", 10, 0.0, 10.0);
        writer.start();

        std::atomic<bool> running{true};
        std::vector<std::thread> producers;
        for (int t = 0; t < 3; ++t) {
            producers.emplace_back([&] {
                while (running.load(std::memory_order_relaxed)) {
                    try { writer.fillHist1D(HistId::Values, Record::Value{1.0}); }
                    catch (...) { break; }
                }
            });
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        writer.checkpoint(99);  // must not deadlock

        running.store(false, std::memory_order_release);
        for (auto& p : producers) p.join();
        writer.finish(0);
        TEST_PASS("Checkpoint completes under fill queue back-pressure");
    }

    {
        // Worker exception + checkpoint: a bad fill triggers one worker to exit.
        // checkpoint() must return by throwing the worker's exception rather
        // than deadlocking waiting for the exited worker to arrive at quiesce.
        Record::Writer writer;
        writer.setRecordThreadCount(2);
        openWriter(writer, "checkpoint_after_worker_exit");
        writer.declareHist1D(HistId::Values, "values", "values", 10, 0.0, 10.0);
        writer.start();

        writer.fillHist1D(HistId::Missing, Record::Value{1.0});  // bad key → worker exits
        std::this_thread::sleep_for(std::chrono::milliseconds(20));

        bool threw = false;
        try {
            writer.checkpoint(1);
        } catch (const std::runtime_error&) {
            threw = true;
        }
        TEST_TRUE(threw);
        TEST_PASS("Checkpoint after worker exit throws instead of deadlocking");
    }

    {
        // signalWatch(Checkpoint) with barrier: verify the barrier is completed
        // and the fill queue drains correctly without going through checkpoint().
        Record::Writer writer;
        openWriter(writer, "watch_checkpoint_barrier");
        writer.declareHist1D(HistId::Values, "values", "values", 10, 0.0, 10.0);
        writer.start();

        for (int i = 0; i < 30; ++i)
            writer.fillHist1D(HistId::Values, Record::Value{1.0});

        auto barrier = std::make_shared<Record::BarrierState>();
        writer.signalWatch(Record::WatchRequest{
            Record::WatchRequest::Kind::Checkpoint, 30, barrier});
        {
            std::unique_lock<std::mutex> lk(barrier->mutex);
            barrier->cv.wait(lk, [&] { return barrier->done; });
            if (barrier->exception) std::rethrow_exception(barrier->exception);
        }
        TEST_TRUE(barrier->completed);
        writer.finish(30);
        TEST_PASS("signalWatch(Checkpoint) barrier completes correctly");
    }

    {
        // signalWatch(Finalize) after worker exception: barrier must carry the
        // exception, not complete successfully with partial data.
        Record::Writer writer;
        openWriter(writer, "watch_finalize_exception");
        writer.declareHist1D(HistId::Values, "values", "values", 10, 0.0, 10.0);
        writer.start();

        writer.fillHist1D(HistId::Missing, Record::Value{1.0});  // bad key
        std::this_thread::sleep_for(std::chrono::milliseconds(20));

        auto barrier = std::make_shared<Record::BarrierState>();
        writer.signalWatch(Record::WatchRequest{
            Record::WatchRequest::Kind::Finalize, 0, barrier});
        {
            std::unique_lock<std::mutex> lk(barrier->mutex);
            barrier->cv.wait(lk, [&] { return barrier->done; });
        }
        TEST_TRUE(barrier->exception != nullptr);
        TEST_FALSE(barrier->completed);
        TEST_PASS("signalWatch(Finalize) barrier carries worker exception");
    }

    {
        // fatalWrite with timeout: verify it returns without hanging even when
        // fills are still in flight.
        Record::Writer writer;
        openWriter(writer, "fatal_write");
        writer.declareHist1D(HistId::Values, "values", "values", 10, 0.0, 10.0);
        writer.start();

        for (int i = 0; i < 20; ++i)
            writer.fillHist1D(HistId::Values, Record::Value{1.0});

        const bool done = writer.fatalWrite(20, std::chrono::seconds(5));
        TEST_TRUE(done);
        TEST_PASS("fatalWrite completes within timeout");
    }

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
