// Core::Spec — the structural checks hep-run makes on a resolved spec (03 §7), including the two
// invariants it refuses to trust: the seed-list length (D-SEEDS) and the seed range.

#include <fstream>
#include <string>

#include "Core.hh"
#include "check.hh"

namespace {

const std::string kGood = R"(
[meta]
schema = 2
point = "eic_5x41_ep_MSTW08lo"
aliases = ["eic_5x41_ep_MSTW08lo_pth6"]
hash = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
origin = "configs/PhotoProduction/eic.v2.toml --study pdf [1]"

[run]
events = 1000
threads = 2
seed = 4242

[run.seeds]
point = 4242
instances = [4242, 4243]

[source]
kind = "pythia"
cards = ["/tmp/base.cmnd", "/tmp/point.cmnd"]

[output]
dir = "/tmp/point"
yoda = "analysis.yoda"
summary = "run.summary.json"

[[analyzer]]
kind = "rivet"
analyses = ["photo_eic:R=0.4"]
paths = ["/tmp/analyses"]
xsec = "generator"
weights = "nominal"
dump_every = 0
check_beams = true

[[analyzer]]
kind = "store"
dir = "/tmp/point/events"
compression = "gz"

[status]
fd = 3
heartbeat_ms = 500
)";

std::string without(const std::string& text, const std::string& fragment) {
    const std::size_t at = text.find(fragment);
    return at == std::string::npos ? text : text.substr(0, at) + text.substr(at + fragment.size());
}

std::string replaced(const std::string& text, const std::string& from, const std::string& to) {
    const std::size_t at = text.find(from);
    return at == std::string::npos ? text : text.substr(0, at) + to + text.substr(at + from.size());
}

}  // namespace

int main() {
    const Core::Spec spec = Core::parseSpec(kGood);
    CHECK_EQ(spec.point, std::string("eic_5x41_ep_MSTW08lo"));
    CHECK_EQ(spec.aliases.size(), std::size_t(1));
    CHECK_EQ(spec.events, 1000LL);
    CHECK_EQ(spec.threads, 2);
    CHECK_EQ(spec.seed, 4242LL);
    CHECK_EQ(spec.instance_seeds.size(), std::size_t(2));
    CHECK_EQ(spec.source_kind, std::string("pythia"));
    CHECK_EQ(spec.cards.size(), std::size_t(2));
    CHECK_EQ(spec.output_dir, std::string("/tmp/point"));
    CHECK_EQ(spec.analyzers.size(), std::size_t(2));
    CHECK_EQ(spec.analyzers[0].analyses.at(0), std::string("photo_eic:R=0.4"));
    CHECK(spec.analyzers[0].check_beams);
    CHECK_EQ(spec.analyzers[1].compression, std::string("gz"));
    CHECK(spec.wants("rivet"));
    CHECK(spec.wants("store"));
    CHECK(!spec.wants("module"));
    CHECK_EQ(spec.status_fd, 3);

    // A different schema is refused with the version in the message, not silently half-read.
    CHECK_THROWS(Core::parseSpec(replaced(kGood, "schema = 2", "schema = 3")), Core::Error);
    // Missing tables.
    CHECK_THROWS(Core::parseSpec(without(kGood, "[output]\ndir = \"/tmp/point\"")), Core::Error);
    // Wrong types.
    CHECK_THROWS(Core::parseSpec(replaced(kGood, "threads = 2", "threads = \"two\"")), Core::Error);
    CHECK_THROWS(Core::parseSpec(replaced(kGood, "cards = [\"/tmp/base.cmnd\", \"/tmp/point.cmnd\"]",
                                          "cards = \"/tmp/base.cmnd\"")),
                 Core::Error);
    // Not TOML at all.
    CHECK_THROWS(Core::parseSpec("this is not toml"), Core::Error);

    // D-SEEDS: a seed list that does not match the thread count is undefined behaviour in Pythia, so
    // hep-run refuses it here.
    CHECK_THROWS(Core::parseSpec(replaced(kGood, "instances = [4242, 4243]", "instances = [4242]")),
                 Core::Error);
    CHECK_THROWS(Core::parseSpec(replaced(kGood, "instances = [4242, 4243]",
                                          "instances = [4242, 4243, 4244]")),
                 Core::Error);
    // Seeds outside Pythia's range, and a point seed that is not the base of its block.
    CHECK_THROWS(Core::parseSpec(replaced(kGood, "instances = [4242, 4243]",
                                          "instances = [0, 4243]")),
                 Core::Error);
    CHECK_THROWS(Core::parseSpec(replaced(kGood, "instances = [4242, 4243]",
                                          "instances = [4242, 900000001]")),
                 Core::Error);
    CHECK_THROWS(Core::parseSpec(replaced(kGood, "point = 4242\ninstances", "point = 9999\ninstances")),
                 Core::Error);

    // Analyzers must carry what they need.
    CHECK_THROWS(Core::parseSpec(replaced(kGood, "analyses = [\"photo_eic:R=0.4\"]", "analyses = []")),
                 Core::Error);
    CHECK_THROWS(Core::parseSpec(replaced(kGood, "kind = \"store\"\ndir = \"/tmp/point/events\"",
                                          "kind = \"store\"\ncompression = \"gz\"")),
                 Core::Error);

    // A hash that is not a sha256 reference means the spec did not come from `hep plan`.
    CHECK_THROWS(Core::parseSpec(replaced(kGood, "hash = \"sha256:", "hash = \"md5:")), Core::Error);

    // From a file, including the missing-file message.
    const std::string path = "/tmp/hekit_spec_test.toml";
    {
        std::ofstream out(path);
        out << kGood;
    }
    CHECK_EQ(Core::parseSpecFile(path).point, std::string("eic_5x41_ep_MSTW08lo"));
    std::remove(path.c_str());
    CHECK_THROWS(Core::parseSpecFile("/tmp/hekit_absent_spec.toml"), Core::Error);

    // threads = 0 means "all cores", and then the seed list is deliberately absent (P2-S02).
    const std::string automatic = replaced(
        replaced(kGood, "threads = 2", "threads = 0"), "instances = [4242, 4243]", "instances = []");
    CHECK_EQ(Core::parseSpec(automatic).instance_seeds.size(), std::size_t(0));

    return check::finish("core_spec");
}
