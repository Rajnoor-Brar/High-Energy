// Status::Writer and Status::Heartbeat — the messages hep reads (06 §3).
//
// Run with fd 3 redirected (`./test_status_roundtrip 3>status.jsonl`) and it writes that stream; the
// Python side parses the same file in tests/python/run/test_status.py, so the two halves are checked
// against each other rather than against two copies of the same assumption.

#include <cstdio>
#include <string>
#include <unistd.h>
#include <vector>

#include "Core.hh"
#include "Status.hh"
#include "check.hh"

int main(int argc, char* argv[]) {
    const bool emit_stream = argc > 1 && std::string(argv[1]) == "--emit";

    if (emit_stream) {
        // One of every kind, for the Python reader.
        Status::Writer writer(3);
        writer.phase("init", "reading 2 cards");
        writer.init({2212, 11}, {41.0, 5.0}, 28.6404, 2, "serial", {"rivet", "store"});
        Status::Progress progress;
        progress.done = 500;
        progress.total = 1000;
        progress.rate = 1180.4;
        progress.workers = {250, 250};
        writer.progress(progress, true);
        writer.xsec(71422.16, 95.0, false);
        writer.log(Status::Level::Warn, "pythia", "SpaceShower::pT2nextQCD: weight above unity");
        writer.log(Status::Level::Error, "rivet", "quote \" backslash \\ newline\nend");
        writer.checkpoint(500, {"analysis.partial.yoda"});
        writer.heartbeat();
        writer.summary("\"events\":1000,\"xsec_pb\":71422.16,\"err_pb\":95,\"stopped\":false",
                       "1000 events");
        return 0;
    }

    // Structured mode: fd 3 is open (ctest runs this with fd 3 on a file).
    {
        Status::Writer writer(3);
        CHECK(writer.structured());
        writer.phase("check", "structured");
        CHECK_EQ(writer.dropped(), 0LL);
    }

    // Plain mode: a descriptor that is not open falls back to stderr instead of failing.
    {
        Status::Writer writer(99);
        CHECK(!writer.structured());
        writer.phase("check", "plain");
    }

    // Escaping: the reader must survive a tool's message verbatim.
    CHECK_EQ(Status::escape("a\"b\\c"), std::string("a\\\"b\\\\c"));
    CHECK_EQ(Status::escape("line\nbreak"), std::string("line\\nbreak"));
    CHECK_EQ(Status::escape(std::string("bell\x07")), std::string("bell\\u0007"));

    // Rate limiting: the event loop may call progress() as often as it likes.
    {
        Status::Writer writer(99, /*interval=*/10.0);
        Status::Progress progress;
        progress.total = 10;
        for (int index = 0; index < 100; ++index) {
            progress.done = index;
            writer.progress(progress);           // all but the first are dropped by the interval
        }
        CHECK(writer.sinceLastMessage() >= 0.0);
    }

    // The plain progress line says the three things a person wants.
    Status::Progress progress;
    progress.done = 450;
    progress.total = 1000;
    progress.rate = 1180.0;
    const std::string line = Status::progressLine(progress);
    CHECK(line.find("45%") != std::string::npos);
    CHECK(line.find("450/1000") != std::string::npos);
    CHECK(line.find("ev/s") != std::string::npos);

    // The heartbeat thread starts, reports and stops promptly.
    {
        Status::Writer writer(99);
        Status::Heartbeat heartbeat(writer, 0.01);
        heartbeat.start();
        for (long long done = 0; done < 1000; done += 100) heartbeat.update(done, 1000);
        heartbeat.workers({500, 500});
        const Core::Steady::time_point stopping = Core::tick();
        heartbeat.stop();
        CHECK(Core::since(stopping) < 1.0);      // stopping waits for the predicate, not the next tick
        heartbeat.stop();                        // idempotent
    }

    // Scope timers accumulate per name.
    {
        Status::Timers timers;
        CHECK(timers.empty());
        {
            Status::Scope first(timers, "generate");
            Status::Scope second(timers, "generate");
        }
        const auto snapshot = timers.snapshot();
        CHECK_EQ(snapshot.at("generate").calls, 2LL);
        CHECK(snapshot.at("generate").seconds >= 0.0);
    }

    return check::finish("status_roundtrip");
}
