// Results::Writer — the rule that a reader never sees a half-written file, and that a stopped run's
// output is never mistaken for a finished one (07 §1, 00/B3, D22).
//
// The interesting cases are the ones a real run only reaches on a bad day: a stale file from an earlier
// attempt, a directory that does not exist yet, a name YODA cannot write.

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

#include "YODA/AnalysisObject.h"
#include "YODA/Counter.h"

#include "Results.hh"
#include "check.hh"

namespace {

namespace fs = std::filesystem;

fs::path freshDirectory(const std::string& name) {
    const fs::path directory = fs::temp_directory_path() / ("hekit_results_" + name);
    fs::remove_all(directory);
    return directory;
}

std::vector<std::string> names(const fs::path& directory) {
    std::vector<std::string> found;
    for (const fs::directory_entry& entry : fs::directory_iterator(directory))
        found.push_back(entry.path().filename().string());
    std::sort(found.begin(), found.end());
    return found;
}

// YODA does not name a shared-pointer alias of its own (Rivet defines `Rivet::AnalysisObjectPtr`),
// so the test spells it out; `writeYoda` takes any range of pointer-like objects.
std::vector<std::shared_ptr<YODA::AnalysisObject>> oneCounter() {
    auto counter = std::make_shared<YODA::Counter>("/TEST/count");
    counter->fill(2.0);
    return {counter};
}

// The marker goes before the suffix, because `analysis.yoda.partial` is not a YODA file as far as YODA
// is concerned — it identifies the format from the extension (P0-S03 hit exactly this).
void naming() {
    CHECK_EQ(Results::marked("analysis.yoda", "partial"), std::string{"analysis.partial.yoda"});
    CHECK_EQ(Results::marked("analysis.yoda", "tmp"), std::string{"analysis.tmp.yoda"});
    CHECK_EQ(Results::marked("run.summary.json", "tmp"), std::string{"run.summary.tmp.json"});
    CHECK_EQ(Results::marked("noextension", "tmp"), std::string{"noextension.tmp"});
}

void writesAtomically() {
    const fs::path directory = freshDirectory("atomic");
    Results::Writer writer(directory.string());                 // creates the directory
    CHECK(fs::is_directory(directory));

    const std::string written = writer.writeYoda("analysis.yoda", oneCounter(), /*stopped=*/false);
    CHECK_EQ(written, (directory / "analysis.yoda").string());
    // Nothing else is left behind: no temporary, no partial.
    const std::vector<std::string> found = names(directory);
    CHECK_EQ(found.size(), std::size_t{1});
    CHECK_EQ(found.front(), std::string{"analysis.yoda"});
    CHECK(fs::file_size(directory / "analysis.yoda") > 0);
    fs::remove_all(directory);
}

// 07 §1: a stopped run writes `analysis.partial.yoda`, *never* `analysis.yoda` — and never both, or a
// plot could silently pick up the finished-looking file from a previous attempt.
void stoppedRunsAreNamedDifferently() {
    const fs::path directory = freshDirectory("partial");
    Results::Writer writer(directory.string());

    writer.writeYoda("analysis.yoda", oneCounter(), /*stopped=*/false);
    const std::string partial = writer.writeYoda("analysis.yoda", oneCounter(), /*stopped=*/true);
    CHECK_EQ(partial, (directory / "analysis.partial.yoda").string());
    CHECK_EQ(names(directory).size(), std::size_t{1});
    CHECK(!fs::exists(directory / "analysis.yoda"));            // the stale complete file is gone

    // And the other way round: finishing a rerun clears the partial from the attempt before.
    const std::string complete = writer.writeYoda("analysis.yoda", oneCounter(), /*stopped=*/false);
    CHECK_EQ(complete, (directory / "analysis.yoda").string());
    CHECK_EQ(names(directory).size(), std::size_t{1});
    CHECK(!fs::exists(directory / "analysis.partial.yoda"));
    fs::remove_all(directory);
}

void writesText() {
    const fs::path directory = freshDirectory("text");
    Results::Writer writer(directory.string());
    const std::string written = writer.writeText("run.summary.json", "{\"ok\": true}\n");
    CHECK_EQ(written, (directory / "run.summary.json").string());
    std::ifstream in(written);
    std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    CHECK_EQ(content, std::string{"{\"ok\": true}\n"});
    CHECK_EQ(names(directory).size(), std::size_t{1});
    fs::remove_all(directory);
}

// A file that cannot be written is an analyzer error (exit 5), and it must not leave a temporary behind.
void failureLeavesNothing() {
    const fs::path directory = freshDirectory("failure");
    Results::Writer writer(directory.string());
    CHECK_THROWS(writer.writeYoda("analysis.nosuchformat", oneCounter(), false), Core::Error);
    CHECK(names(directory).empty());
    fs::remove_all(directory);
}

// The summary is the only place `hep-run` reports numbers no one else has; it must carry them all.
void summaryCarriesTheRun() {
    Core::RunRecord record;
    record.point = "eic_5x41_ep";
    record.hash = "sha256:abc";
    record.origin = "configs/PhotoProduction/eic.v2.toml --study pdf [1]";
    record.started = "2026-09-18T04:00:00Z";
    record.events_requested = 1000;
    record.attempted = 1024;
    record.accepted = 1000;
    record.threads = 2;
    record.chunk = 20;
    record.seed = 4242;
    record.seeds = {4242, 4243};
    record.xsec_pb = 70818.73;
    record.xsec_error_pb = 2212.24;
    record.wall_seconds = 1.5;
    record.warnings = {{"maximum for cross section violated", 3}};
    const std::vector<Analyzer::Output> outputs{{"yoda", "/tmp/point/analysis.yoda", false}};

    const std::string json = Results::summaryJson(record, outputs, "2026-09-18T04:00:02Z");
    for (const char* fragment :
         {"\"schema\": 2", "\"point\": \"eic_5x41_ep\"", "\"events_requested\": 1000",
          "\"events\": 1000", "\"attempted\": 1024", "\"threads\": 2", "\"chunk\": 20",
          "\"mode\": \"serial\"", "\"stopped\": false", "\"xsec_pb\": 70818.73",
          "\"xsec_err_pb\": 2212.24", "\"instances\": [4242,4243]", "\"point\": 4242",
          "\"maximum for cross section violated\": 3", "\"kind\": \"yoda\"",
          "\"partial\": false", "\"finished\": \"2026-09-18T04:00:02Z\""})
        CHECK(json.find(fragment) != std::string::npos ? true : (std::fprintf(stderr, "missing: %s\n", fragment), false));

    // A stopped run says so, and its output is marked partial, so `hep` reruns it rather than
    // treating it as a result (07 §2).
    record.stopped = true;
    const std::string stopped =
        Results::summaryJson(record, {{"yoda", "/tmp/point/analysis.partial.yoda", true}}, "now");
    CHECK(stopped.find("\"stopped\": true") != std::string::npos);
    CHECK(stopped.find("\"partial\": true") != std::string::npos);

    // No outputs at all is legal (a generation-only run) and must still be valid JSON.
    const std::string empty = Results::summaryJson(Core::RunRecord{}, {}, "now");
    CHECK(empty.find("\"outputs\": []") != std::string::npos);
}

}  // namespace

int main() {
    naming();
    writesAtomically();
    stoppedRunsAreNamedDifferently();
    writesText();
    failureLeavesNothing();
    summaryCarriesTheRun();
    return check::finish("results_writer");
}
