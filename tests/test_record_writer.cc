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
        openWriter(writer, "scribe_exception");
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
        TEST_PASS("Scribe exceptions propagate to finish");
    }

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
