// Store::Writer — the shard layout, the index, and the rule that makes a store trustworthy (11 §1–3).
//
// What is checked here is what a replay depends on and what no end-to-end run would notice going
// wrong: that the shard counts add up, that nothing is left in `.part`, that the index is written
// last, and that a codec the build lacks is refused with a message instead of a failed write.
//
// The events are synthetic — one particle each — because this tests the *store*, not the generator.

#include <filesystem>
#include <fstream>
#include <string>

#include "HepMC3/GenEvent.h"
#include "HepMC3/GenParticle.h"
#include "HepMC3/GenVertex.h"

#include "Store/Compression.hh"
#include "Store/Types.hh"
#include "Store/Writer.hh"
#include "check.hh"

namespace {

namespace fs = std::filesystem;

fs::path freshDirectory(const std::string& name) {
    const fs::path directory = fs::temp_directory_path() / ("hekit_store_" + name);
    fs::remove_all(directory);
    return directory;
}

HepMC3::GenEvent anEvent(int number) {
    HepMC3::GenEvent event(HepMC3::Units::GEV, HepMC3::Units::MM);
    auto incoming = std::make_shared<HepMC3::GenParticle>(
        HepMC3::FourVector(0.0, 0.0, 7000.0, 7000.0), 2212, 4);
    auto outgoing = std::make_shared<HepMC3::GenParticle>(
        HepMC3::FourVector(1.0 * number, 0.0, 10.0, 11.0), 211, 1);
    auto vertex = std::make_shared<HepMC3::GenVertex>();
    vertex->add_particle_in(incoming);
    vertex->add_particle_out(outgoing);
    event.add_vertex(vertex);
    event.set_event_number(number);
    return event;
}

std::vector<std::string> names(const fs::path& directory) {
    std::vector<std::string> found;
    for (const fs::directory_entry& entry : fs::directory_iterator(directory))
        found.push_back(entry.path().filename().string());
    std::sort(found.begin(), found.end());
    return found;
}

// The counts row: every event lands in its worker's shard, and the shards add up to the total.
void shardsAddUp() {
    const fs::path directory = freshDirectory("counts");
    Store::Index index;
    index.point = "test_point";
    index.hash = "sha256:" + std::string(64, 'a');
    index.threads = 3;
    index.seeds = {11, 22, 33};
    index.xsec_pb = 1234.5;
    index.xsec_err_pb = 6.7;
    {
        Store::Writer writer(directory.string(), "none");
        for (int number = 0; number < 30; ++number) {
            const HepMC3::GenEvent event = anEvent(number);
            writer.write(number % 3, event);        // round robin over three workers
        }
        CHECK_EQ(writer.events(), std::int64_t{30});
        CHECK_EQ(writer.shardCount(), std::size_t{3});
        index = writer.finish(index);
    }

    CHECK_EQ(index.events, std::int64_t{30});
    CHECK_EQ(index.shardEvents(), std::int64_t{30});
    CHECK(index.consistent());
    CHECK_EQ(index.shards.size(), std::size_t{3});
    for (const Store::Shard& shard : index.shards) {
        CHECK_EQ(shard.events, std::int64_t{10});
        CHECK(shard.bytes > 0);
        CHECK_EQ(shard.sha256.size(), std::size_t{64});
    }
    // Shards are listed by worker, which is what makes a replay's shard selection meaningful.
    CHECK_EQ(index.shards[0].worker, 0);
    CHECK_EQ(index.shards[2].worker, 2);

    const std::vector<std::string> found = names(directory);
    CHECK_EQ(found.size(), std::size_t{4});
    CHECK_EQ(found[0], std::string{"events.0.hepmc"});
    CHECK_EQ(found[3], std::string{Store::kIndexName});
    for (const std::string& name : found)
        CHECK(name.find(".part") == std::string::npos);
    fs::remove_all(directory);
}

// A store is finished when its index exists: the shards are closed and hashed before it is written.
void indexComesLast() {
    const fs::path directory = freshDirectory("order");
    {
        Store::Writer writer(directory.string(), "none");
        writer.write(0, anEvent(1));
        // Mid-run: the shard is still `.part` and there is no index, so a reader knows not to trust it.
        CHECK(fs::exists(directory / "events.0.hepmc.part"));
        CHECK(!fs::exists(directory / Store::kIndexName));
        Store::Index index;
        index.point = "p";
        writer.finish(index);
    }
    CHECK(fs::exists(directory / Store::kIndexName));
    CHECK(!fs::exists(directory / "events.0.hepmc.part"));
    fs::remove_all(directory);
}

void indexJsonSaysWhatItShould() {
    Store::Index index;
    index.point = "eic_5x41_ep";
    index.hash = "sha256:" + std::string(64, 'b');
    index.compression = "zst";
    index.threads = 2;
    index.seeds = {4242, 4243};
    index.beams.ids = {2212, -11};
    index.beams.energies = {920.0, 27.5};
    index.xsec_pb = 70818.73;
    index.xsec_err_pb = 2212.24;
    index.events = 100;
    index.stopped = true;
    index.shards.push_back(Store::Shard{"events.0.hepmc.zst", 100, 12345, std::string(64, 'c'), 0});

    const std::string json = Store::indexJson(index);
    for (const char* fragment :
         {"\"version\": 1", "\"format\": \"hepmc3-ascii\"", "\"compression\": \"zst\"",
          "\"point\": \"eic_5x41_ep\"", "\"threads\": 2", "\"seeds\": [4242,4243]",
          "\"ids\": [2212,-11]", "\"energies\": [920,27.5]", "\"xsec_pb\": 70818.73",
          "\"events\": 100", "\"stopped\": true", "\"worker\": 0", "\"bytes\": 12345"})
        CHECK(json.find(fragment) != std::string::npos
                  ? true
                  : (std::fprintf(stderr, "missing: %s\n", fragment), false));
}

// An index whose shards do not add up is a bug in us; it must never be written quietly.
void inconsistentCountsAreRefused() {
    const fs::path directory = freshDirectory("inconsistent");
    Store::Writer writer(directory.string(), "none");
    writer.write(0, anEvent(1));
    Store::Index index;
    index.events = 99;                              // a lie: one event was written
    CHECK_THROWS(writer.finish(index), Core::Error);
    fs::remove_all(directory);
}

// The "no zstd" row, from the other side: a build without a codec says so before it writes anything.
void anUnavailableCodecIsRefused() {
    const std::vector<std::string> available = Store::codecs();
    CHECK(!available.empty());
    CHECK_EQ(available.front(), std::string{"none"});
    CHECK(Store::supports("none"));
    CHECK(!Store::supports("lzma"));
    CHECK_THROWS(Store::requireCodec("lzma"), Core::Error);

    const fs::path directory = freshDirectory("codec");
    CHECK_THROWS(Store::Writer(directory.string(), "lzma"), Core::Error);
    fs::remove_all(directory);
}

void shardNamesFollowTheCodec() {
    CHECK_EQ(Store::shardName(0, "gz"), std::string{"events.0.hepmc.gz"});
    CHECK_EQ(Store::shardName(7, "zst"), std::string{"events.7.hepmc.zst"});
    CHECK_EQ(Store::shardName(1, "none"), std::string{"events.1.hepmc"});
}

// Every codec this build has must survive a round trip: written, closed, read back.
void everyCodecRoundTrips() {
    for (const std::string& codec : Store::codecs()) {
        const fs::path directory = freshDirectory("codec_" + codec);
        {
            Store::Writer writer(directory.string(), codec);
            for (int number = 0; number < 5; ++number) writer.write(0, anEvent(number));
            Store::Index index;
            index.point = "p";
            writer.finish(index);
        }
        const fs::path shard = directory / Store::shardName(0, codec);
        CHECK(fs::exists(shard));

        auto reader = Store::makeReader(shard.string(), codec);
        int read = 0;
        HepMC3::GenEvent event;
        while (!reader->failed()) {
            reader->read_event(event);
            if (reader->failed()) break;
            read += 1;
        }
        reader->close();
        CHECK_EQ(read, 5);
        fs::remove_all(directory);
    }
}

}  // namespace

int main() {
    shardsAddUp();
    indexComesLast();
    indexJsonSaysWhatItShould();
    inconsistentCountsAreRefused();
    anUnavailableCodecIsRefused();
    shardNamesFollowTheCodec();
    everyCodecRoundTrips();
    return check::finish("store_writer");
}
