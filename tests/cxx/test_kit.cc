// tests/cxx/test_kit.cc — utils/Kit.hh (V73): the arguments, the JSON writer and its flat reader.
// requires: none

#include "Kit.hh"

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

static int failures = 0;
#define CHECK(cond)                                                                   \
    do {                                                                              \
        if (!(cond)) {                                                                \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);      \
            ++failures;                                                               \
        }                                                                             \
    } while (0)

static Kit::Args parse(std::vector<std::string> words, std::set<std::string> valued, std::set<std::string> flags = {}) {
    static std::vector<std::string> keep;
    keep = words;
    keep.insert(keep.begin(), "prog");
    static std::vector<char*> argv;
    argv.clear();
    for (auto& w : keep) argv.push_back(w.data());
    return Kit::Args(static_cast<int>(argv.size()), argv.data(), valued, flags);
}

int main() {
    // ── arguments ──
    {
        const auto a = parse({"--input=in.hepmc", "--events", "10", "--keep-raw", "config.toml", "--select", "a",
                              "--select=b"}, {"input", "events", "select"}, {"keep-raw"});
        CHECK(a.ok());
        CHECK(a.get("input") == "in.hepmc" && a.get("events") == "10" && a.has("keep-raw"));
        CHECK(a.all("select") == (std::vector<std::string>{"a", "b"}) && a.get("select") == "b");
        CHECK(a.positional() == std::vector<std::string>{"config.toml"});
        CHECK(a.get("missing", "fallback") == "fallback" && !a.has("missing"));
    }
    {
        const auto unknown = parse({"--nope"}, {"input"});
        CHECK(!unknown.ok() && unknown.error() == "unknown option --nope");
        const auto short_ = parse({"--input"}, {"input"});
        CHECK(!short_.ok() && short_.error() == "--input needs a value");
        const auto help = parse({"--help"}, {});
        CHECK(!help.ok() && help.error().empty());
        const auto flagWithValue = parse({"--keep-raw=1"}, {}, {"keep-raw"});
        CHECK(!flagWithValue.ok());
    }
    // ── the writer ──
    {
        Kit::Json::Object inner;
        inner.add("a.hepmc", 3L).add("b.hepmc", 4L);
        const std::string text = Kit::Json::Object()
                                     .add("tool", "App_Pythia").add("written", 7L).add("sigma_pb", 73664.5981736)
                                     .add("stopped", false).add("outputs", std::vector<std::string>{"a \"q\"", "b"})
                                     .numbers("seeds", std::vector<long>{1, 2}).add("per", inner).str();
        CHECK(text.find("\n  \"tool\": \"App_Pythia\",\n") != std::string::npos);
        CHECK(text.find("\"sigma_pb\": 73664.5981736") != std::string::npos);
        CHECK(text.find("\"outputs\": [\"a \\\"q\\\"\", \"b\"]") != std::string::npos);
        CHECK(text.find("\"per\": {\"a.hepmc\": 3, \"b.hepmc\": 4}") != std::string::npos);
        CHECK(Kit::Json::Object().add("x", 1).fields() == "\"x\": 1");
        // ── read back ──
        const auto flat = Kit::Json::Flat::parse(text);
        CHECK(flat.has_value());
        CHECK(flat->text("tool") == std::optional<std::string>("App_Pythia"));
        CHECK(flat->number("written") == std::optional<double>(7.0));
        CHECK(std::fabs(*flat->number("sigma_pb") - 73664.5981736) < 1e-6);
        CHECK(flat->flag("stopped") == std::optional<bool>(false));
        CHECK(!flat->number("outputs") && !flat->number("per") && !flat->number("missing"));   // nested: skipped
    }
    CHECK(!Kit::Json::Flat::parse("not json").has_value());
    CHECK(!Kit::Json::Flat::parse("{\"a\": }").has_value());
    std::printf("%s\n", failures ? "FAILED" : "ok");
    return failures ? 1 : 0;
}
