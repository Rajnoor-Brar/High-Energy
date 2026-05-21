// Focused tests for Probe::ProbeParallel execution modes.

#include <algorithm>
#include <atomic>
#include <exception>
#include <filesystem>
#include <iostream>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include <toml++/toml.hpp>

#include "test_assert.hh"

#include "Probe.hh"
#include "TFile.h"

namespace fs = std::filesystem;

namespace {
    constexpr int kNEvents = 50;
    const std::string kFixtureToml = "tests/fixtures/lambda_fixture.toml";
    const std::string kFixtureRoot = "tests/fixtures/lambda_fixture.root";

    Probe::ProbeConfig fixtureConfig() {
        const toml::table config = toml::parse_file(kFixtureToml);
        return Probe::parseProbeConfig(config);
    }

    bool fixtureAvailable() {
        std::unique_ptr<TFile> file(TFile::Open(kFixtureRoot.c_str(), "READ"));
        return file && !file->IsZombie();
    }
}

int main() {
    std::cout << "── test_probe_parallel ──────────────────────────────────────\n";

    if (!fixtureAvailable()) {
        std::cerr << "Fixture not found: " << kFixtureRoot << '\n'
                  << "Run: tests/fixtures/make_lambda_fixture.exe\n";
        return 77;
    }

    const auto cfg = fixtureConfig();

    {
        Probe::ProbeParallel probe;
        probe.setQueueCapacity(2);
        probe.configureProbe(kFixtureRoot, cfg, 4, kNEvents, true);

        TEST_EQ(probe.eventCount(), static_cast<std::size_t>(kNEvents));
        TEST_EQ(probe.threadCount(), std::size_t(4));
        TEST_TRUE(probe.activeMode() == Probe::ActiveMode::Events);

        // CollectorThread now spawns analysis_threads collectors (defaults
        // to thread_count).  User callbacks under multi-collector must be
        // thread-safe; this test protects `seen` with a mutex.
        std::vector<Long64_t> seen;
        std::mutex            seenMutex;
        probe.streamEvents([&](const Probe::Event& ev, int workerIndex) {
            TEST_TRUE(workerIndex >= 0);
            TEST_EQ(ev.n("protons"), std::size_t(4));
            TEST_EQ(ev.n("pions"),   std::size_t(5));
            std::lock_guard<std::mutex> lock(seenMutex);
            seen.push_back(ev.index);
        });

        TEST_EQ(seen.size(), static_cast<std::size_t>(kNEvents));
        std::set<Long64_t> unique(seen.begin(), seen.end());
        TEST_EQ(unique.size(), static_cast<std::size_t>(kNEvents));
        TEST_EQ(*unique.begin(), Long64_t(1));
        TEST_EQ(*unique.rbegin(), Long64_t(kNEvents));
        TEST_TRUE(probe.stats().find("produced=50") != std::string::npos);
        TEST_TRUE(probe.stats().find("consumed=50") != std::string::npos);
        TEST_PASS("CollectorThread dispatches exactly one callback per event");
    }

    {
        Probe::ProbeParallel probe;
        probe.setCallbackMode(Probe::CallbackMode::WorkerThread);
        probe.configureProbe(kFixtureRoot, cfg, 4, kNEvents, true);

        std::atomic<std::size_t> callbacks{0};
        probe.streamEvents([&](const Probe::Event& ev, int workerIndex) {
            TEST_TRUE(workerIndex >= 0);
            TEST_TRUE(ev.index >= 1 && ev.index <= kNEvents);
            callbacks.fetch_add(1, std::memory_order_relaxed);
        });
        TEST_EQ(callbacks.load(std::memory_order_relaxed), static_cast<std::size_t>(kNEvents));
        TEST_PASS("WorkerThread mode preserves direct worker callbacks");
    }

    {
        Probe::ProbeParallel probe;
        probe.configureProbe(kFixtureRoot, cfg, 4, kNEvents, true);

        bool caught = false;
        try {
            probe.streamEvents([](const Probe::Event&, int) {
                throw std::runtime_error("collector callback failure");
            });
        } catch (const std::runtime_error&) {
            caught = true;
        }
        TEST_TRUE(caught);
        TEST_PASS("CollectorThread callback exceptions propagate");
    }

    // (Phase 11: [probe.index] / parseCollectionsFromToml removed;
    //  per-spec index flags covered by "parseProbeConfig: per-section index flags".)

    {
        // Explicit multi-collector count: analysis_threads different from
        // probe_threads.  Verify all events are still delivered exactly once.
        Probe::ProbeParallel probe;
        probe.setAnalysisThreadCount(2);  // 2 collectors, 4 reader threads
        probe.configureProbe(kFixtureRoot, cfg, 4, kNEvents, true);

        std::atomic<std::size_t> count{0};
        probe.streamEvents([&](const Probe::Event& /*ev*/, int workerIndex) {
            TEST_TRUE(workerIndex >= 0 && workerIndex < 2);
            count.fetch_add(1, std::memory_order_relaxed);
        });
        TEST_EQ(count.load(std::memory_order_relaxed), static_cast<std::size_t>(kNEvents));
        TEST_PASS("CollectorThread with analysis_threads=2 delivers all events");
    }

    {
        // Error path: non-existent input file throws during configureProbe.
        Probe::ProbeParallel probe;
        bool caught = false;
        try {
            probe.configureProbe("/no/such/file.root", cfg, 1, kNEvents, true);
        } catch (const std::runtime_error&) {
            caught = true;
        }
        TEST_TRUE(caught);
        TEST_PASS("configureProbe throws for non-existent input file");
    }

    // (Phase 5 cleanup: docs/WriterMT.md.  The Splitter / shard-cache tests
    //  were removed along with the Splitter feature itself.  ProbeParallel +
    //  multithreaded Writer is the production path; splitting was never the
    //  right fix for the original bottleneck.)

    // ── ProbeIMT tests (Phase 2) ──────────────────────────────────────────────
    // ProbeIMT must deliver the same set of events with the same particle
    // counts as ProbeParallel.  Drop-in substitution at the driver site;
    // identical user-callback semantics.
    {
        Probe::ProbeIMT probe;
        probe.configureProbe(kFixtureRoot, cfg, 4, kNEvents, true);

        TEST_EQ(probe.eventCount(),  static_cast<std::size_t>(kNEvents));
        TEST_EQ(probe.threadCount(), std::size_t(4));

        // ProbeIMT's flush is parallel; callback must be thread-safe.
        std::vector<Long64_t>    seen;
        std::mutex               seenMutex;
        std::atomic<std::size_t> totalProtons{0};
        std::atomic<std::size_t> totalPions{0};
        probe.run([&](const Probe::Event& ev, int workerIndex) {
            TEST_TRUE(workerIndex >= 0);
            TEST_EQ(ev.n("protons"), std::size_t(4));
            TEST_EQ(ev.n("pions"),   std::size_t(5));
            {
                std::lock_guard<std::mutex> lock(seenMutex);
                seen.push_back(ev.index);
            }
            totalProtons.fetch_add(ev.n("protons"), std::memory_order_relaxed);
            totalPions.fetch_add(ev.n("pions"),   std::memory_order_relaxed);
        });

        TEST_EQ(seen.size(),                std::size_t(kNEvents));
        TEST_EQ(totalProtons.load(),        std::size_t(kNEvents * 4));
        TEST_EQ(totalPions.load(),          std::size_t(kNEvents * 5));

        std::set<Long64_t> unique(seen.begin(), seen.end());
        TEST_EQ(unique.size(), static_cast<std::size_t>(kNEvents));
        TEST_EQ(*unique.begin(),  Long64_t(1));
        TEST_EQ(*unique.rbegin(), Long64_t(kNEvents));
        TEST_PASS("ProbeIMT delivers all events with correct particle counts");
    }

    {
        // Output equivalence: ProbeIMT and ProbeParallel must produce the
        // same per-event particle 4-momenta sums.  Sum components to avoid
        // depending on within-event particle order.
        auto accumulate = [&](std::vector<double>& sums, const Probe::Event& ev) {
            const std::size_t i = static_cast<std::size_t>(ev.index - 1);
            if (i >= static_cast<std::size_t>(kNEvents)) return;
            for (const auto& p : ev["protons"]) {
                sums[i * 8 + 0] += p.Px(); sums[i * 8 + 1] += p.Py();
                sums[i * 8 + 2] += p.Pz(); sums[i * 8 + 3] += p.E();
            }
            for (const auto& p : ev["pions"]) {
                sums[i * 8 + 4] += p.Px(); sums[i * 8 + 5] += p.Py();
                sums[i * 8 + 6] += p.Pz(); sums[i * 8 + 7] += p.E();
            }
        };

        Probe::ProbeParallel manual;
        manual.configureProbe(kFixtureRoot, cfg, 4, kNEvents, true);
        std::vector<double> manualSums(kNEvents * 8, 0.0);
        manual.streamEvents([&](const Probe::Event& ev, int /*t*/) { accumulate(manualSums, ev); });

        Probe::ProbeIMT imt;
        imt.configureProbe(kFixtureRoot, cfg, 4, kNEvents, true);
        std::vector<double> imtSums(kNEvents * 8, 0.0);
        imt.run([&](const Probe::Event& ev, int /*t*/) { accumulate(imtSums, ev); });

        TEST_EQ(manualSums.size(), imtSums.size());
        bool allClose = true;
        for (std::size_t i = 0; i < manualSums.size(); ++i) {
            if (std::abs(manualSums[i] - imtSums[i]) > 1e-9) { allClose = false; break; }
        }
        TEST_TRUE(allClose);
        TEST_PASS("ProbeIMT output equivalence with ProbeParallel (per-event momentum sums)");
    }

    {
        // IMT mode rejects vector-stream specs (no index branches) with a
        // clear error.  Construct a malformed config to exercise the path.
        Probe::ProbeConfig badCfg;
        {
            Probe::EventParticleSpec bad = cfg.eventParticles.front();
            bad.indexBranches.clear();
            badCfg.eventParticles.push_back(std::move(bad));
        }

        Probe::ProbeIMT probe;
        bool caught = false;
        try {
            probe.configureProbe(kFixtureRoot, badCfg, 2, kNEvents, true);
        } catch (const std::runtime_error&) {
            caught = true;
        }
        TEST_TRUE(caught);
        TEST_PASS("ProbeIMT rejects vector-stream specs with a clear error");
    }

    // ── Phase 2: dual-syntax branch parser ───────────────────────────────────
    {
        // Form 1: inline table  { name = "pt", type = "F" }
        const auto cfg = toml::parse(R"(b = [{ name = "pt", type = "F" }])");
        const auto& elem = (*cfg["b"].as_array())[0];
        const auto b = Probe::detail::parseBranchEntry(elem, false, "test");
        TEST_EQ(b.name, std::string("pt"));
        TEST_TRUE(b.type == Probe::BranchType::Float);
        TEST_PASS("parseBranchEntry: inline table {name,type}");
    }
    {
        // Form 2: two-element array  ["eta", "D"]
        const auto cfg = toml::parse(R"(b = [["eta", "D"]])");
        const auto& elem = (*cfg["b"].as_array())[0];
        const auto b = Probe::detail::parseBranchEntry(elem, false, "test");
        TEST_EQ(b.name, std::string("eta"));
        TEST_TRUE(b.type == Probe::BranchType::Double);
        TEST_PASS("parseBranchEntry: two-element array [name,type]");
    }
    {
        // Form 3: bare string "phi" (allowBareString=true)
        const auto cfg = toml::parse(R"(b = ["phi"])");
        const auto& elem = (*cfg["b"].as_array())[0];
        const auto b = Probe::detail::parseBranchEntry(elem, true, "test");
        TEST_EQ(b.name, std::string("phi"));
        TEST_TRUE(b.type == Probe::BranchType::Other);
        TEST_PASS("parseBranchEntry: bare string yields BranchType::Other");
    }
    {
        // Error: bare string rejected when allowBareString=false
        const auto cfg = toml::parse(R"(b = ["phi"])");
        const auto& elem = (*cfg["b"].as_array())[0];
        bool caught = false;
        try { Probe::detail::parseBranchEntry(elem, false, "test"); }
        catch (const std::runtime_error&) { caught = true; }
        TEST_TRUE(caught);
        TEST_PASS("parseBranchEntry: bare string rejected when allowBareString=false");
    }
    {
        // Error: array with wrong element count
        const auto cfg = toml::parse(R"(b = [["pt", "F", "extra"]])");
        const auto& elem = (*cfg["b"].as_array())[0];
        bool caught = false;
        try { Probe::detail::parseBranchEntry(elem, false, "test"); }
        catch (const std::runtime_error&) { caught = true; }
        TEST_TRUE(caught);
        TEST_PASS("parseBranchEntry: wrong array element count throws");
    }
    {
        // Error: unknown type code in two-element array
        const auto cfg = toml::parse(R"(b = [["pt", "Z"]])");
        const auto& elem = (*cfg["b"].as_array())[0];
        bool caught = false;
        try { Probe::detail::parseBranchEntry(elem, false, "test"); }
        catch (const std::runtime_error&) { caught = true; }
        TEST_TRUE(caught);
        TEST_PASS("parseBranchEntry: unknown type code throws");
    }
    {
        // parseBranchList: mixed forms in one array
        const auto cfg = toml::parse(R"(b = [{ name="genWeight", type="F" }, ["pu_weight","F"]])");
        const auto* arr = cfg["b"].as_array();
        const auto specs = Probe::detail::parseBranchList(*arr, false, "test");
        TEST_EQ(specs.size(), std::size_t(2));
        TEST_EQ(specs[0].name, std::string("genWeight"));
        TEST_EQ(specs[1].name, std::string("pu_weight"));
        TEST_PASS("parseBranchList: mixed table and array forms");
    }

    // ── Phase 3: parseProbeConfig ─────────────────────────────────────────────
    {
        // Events-only: bare-string kinematic branches + row-indexed node.
        // Labels are auto-discovered from [probe.events.particles.*] sub-tables.
        const auto cfg = toml::parse(R"toml(
[probe]
stream = "events"

[probe.events.particles.muon]
tree     = "Events"
spec     = 2
branches = ["Muon_pt", "Muon_eta", "Muon_phi", "Muon_mass"]
index    = ["event_number", "I"]

[probe.events.nodes.hits]
tree     = "Hits"
index    = ["event_number", "I"]
branches = [["energy", "F"], ["channel", "I"]]
)toml");
        const auto pc = Probe::parseProbeConfig(cfg);
        TEST_EQ(pc.eventParticles.size(), std::size_t(1));
        TEST_EQ(pc.eventParticles[0].label, std::string("muon"));
        TEST_EQ(pc.eventParticles[0].tree,  std::string("Events"));
        TEST_EQ(pc.eventParticles[0].indexBranches.size(), std::size_t(1));
        TEST_EQ(pc.eventParticles[0].indexBranches[0].name, std::string("event_number"));
        TEST_EQ(pc.eventNodes.size(), std::size_t(1));
        TEST_EQ(pc.eventNodes[0].label, std::string("hits"));
        TEST_EQ(pc.eventNodes[0].branches.size(), std::size_t(2));
        TEST_EQ(pc.feedParticles.size(), std::size_t(0));
        TEST_EQ(pc.feedNodes.size(), std::size_t(0));
        TEST_TRUE(pc.requestedMode == Probe::StreamMode::Events);
        TEST_PASS("parseProbeConfig: events-only config with particle + node");
    }
    {
        // Feed-only config
        const auto cfg = toml::parse(R"toml(
[probe]
stream = "feed"

[probe.feed.particles.leading_jet]
tree     = "Events"
spec     = 2
branches = ["Jet_pt", "Jet_eta", "Jet_phi", "Jet_mass"]

[probe.feed.nodes.weights]
tree     = "Events"
branches = [["genWeight", "F"], ["pu_weight", "F"]]
)toml");
        const auto pc = Probe::parseProbeConfig(cfg);
        TEST_EQ(pc.feedParticles.size(), std::size_t(1));
        TEST_EQ(pc.feedParticles[0].label, std::string("leading_jet"));
        TEST_EQ(pc.feedNodes.size(), std::size_t(1));
        TEST_EQ(pc.feedNodes[0].branches.size(), std::size_t(2));
        TEST_EQ(pc.eventParticles.size(), std::size_t(0));
        TEST_TRUE(pc.requestedMode == Probe::StreamMode::Feed);
        TEST_PASS("parseProbeConfig: feed-only config");
    }
    {
        // Mixed auto config: both events and feed defined
        const auto cfg = toml::parse(R"toml(
[probe]

[probe.events.particles.muon]
tree     = "Events"
spec     = 2
branches = ["Muon_pt", "Muon_eta", "Muon_phi", "Muon_mass"]

[probe.feed.nodes.met]
tree     = "Events"
branches = [["MET_pt", "F"]]
)toml");
        const auto pc = Probe::parseProbeConfig(cfg);
        TEST_TRUE(pc.requestedMode == Probe::StreamMode::Auto);
        TEST_TRUE(pc.hasEventData());
        TEST_TRUE(pc.hasFeedData());
        TEST_PASS("parseProbeConfig: mixed auto config (events+feed)");
    }
    {
        // Rule 6: stream='events' but no event specs → throws
        const auto cfg = toml::parse(R"toml(
[probe]
stream = "events"

[probe.feed.nodes.met]
tree     = "Events"
branches = [["MET_pt", "F"]]
)toml");
        bool caught = false;
        try { Probe::parseProbeConfig(cfg); }
        catch (const std::runtime_error&) { caught = true; }
        TEST_TRUE(caught);
        TEST_PASS("parseProbeConfig rule 6: stream='events' with no event specs throws");
    }
    {
        // Rule 7: same label in events and feed → throws
        const auto cfg = toml::parse(R"toml(
[probe]

[probe.events.particles.muon]
tree     = "Events"
spec     = 2
branches = ["a", "b", "c", "d"]

[probe.feed.particles.muon]
tree     = "Events"
spec     = 2
branches = ["a", "b", "c", "d"]
)toml");
        bool caught = false;
        try { Probe::parseProbeConfig(cfg); }
        catch (const std::runtime_error&) { caught = true; }
        TEST_TRUE(caught);
        TEST_PASS("parseProbeConfig rule 7: shared label in events and feed throws");
    }
    {
        // Rule 3: index key in feed node → throws
        const auto cfg = toml::parse(R"toml(
[probe]

[probe.feed.nodes.hits]
tree     = "Events"
index    = ["event_number", "I"]
branches = [["energy", "F"]]
)toml");
        bool caught = false;
        try { Probe::parseProbeConfig(cfg); }
        catch (const std::runtime_error&) { caught = true; }
        TEST_TRUE(caught);
        TEST_PASS("parseProbeConfig rule 3: index key in feed node throws");
    }
    {
        // Rule 8: particle with wrong branch count → throws
        const auto cfg = toml::parse(R"toml(
[probe]

[probe.events.particles.bad]
tree     = "Events"
spec     = 0
branches = ["only_three", "branches", "here"]
)toml");
        bool caught = false;
        try { Probe::parseProbeConfig(cfg); }
        catch (const std::runtime_error&) { caught = true; }
        TEST_TRUE(caught);
        TEST_PASS("parseProbeConfig rule 8: particle with != 4 branches throws");
    }
    {
        // Per-section index flags parsed correctly
        const auto cfg = toml::parse(R"toml(
[probe]

[probe.events.particles.muon]
tree            = "Events"
spec            = 2
branches        = ["a", "b", "c", "d"]
index           = ["idx", "I"]
index_sorted    = false
index_ascending = true
index_monotonic = false
)toml");
        const auto pc = Probe::parseProbeConfig(cfg);
        TEST_TRUE(pc.eventParticles[0].indexSorted    == false);
        TEST_TRUE(pc.eventParticles[0].indexAscending == true);
        TEST_TRUE(pc.eventParticles[0].indexMonotonic == false);
        TEST_PASS("parseProbeConfig: per-section index flags");
    }

    // ── Phase 4: EventParticleReaderRowJoin via EventReader interface ─────────
    if (fixtureAvailable()) {
        // Verify EventParticleReaderRowJoin reads the same events as the
        // existing FlatReader-based EventStream for the lambda fixture.
        const auto& collSpecs = cfg.eventParticles;
        const Long64_t first = 1, last = kNEvents;  // fixture events 1..50

        std::unique_ptr<TFile> f(TFile::Open(kFixtureRoot.c_str(), "READ"));
        TEST_TRUE(f && !f->IsZombie());

        // Build one EventParticleReaderRowJoin for the "protons" spec
        // Look up by label — parseProbeConfig iterates sub-tables alphabetically,
        // so collSpecs[0] is "pions" not "protons" in the new TOML format.
        const auto pIt = std::find_if(collSpecs.begin(), collSpecs.end(),
            [](const Probe::EventParticleSpec& s){ return s.label == "protons"; });
        TEST_TRUE(pIt != collSpecs.end());
        const auto& pSpec = *pIt;
        Probe::EventParticleReaderRowJoin prjp(f.get(), pSpec, kFixtureRoot, first, last);

        std::size_t eventsSeen = 0;
        bool allHave4Protons = true;
        for (Long64_t K = first; K <= last; ++K) {
            Probe::Event ev;
            prjp.seekToEvent(K);
            prjp.readForEvent(K, ev);
            ++eventsSeen;
            if (ev.n("protons") != 4) allHave4Protons = false;
        }
        TEST_EQ(eventsSeen, static_cast<std::size_t>(kNEvents));
        TEST_TRUE(allHave4Protons);
        TEST_PASS("EventParticleReaderRowJoin: reads 4 protons per event from fixture");

        // EventReader abstract interface: the reader IS-A EventReader
        Probe::EventReader* er = &prjp;
        TEST_EQ(er->eventRange().first,  Long64_t(1));
        TEST_EQ(er->eventRange().last,   Long64_t(kNEvents));
        TEST_FALSE(er->treeName().empty());
        TEST_TRUE(er->treePtr() != nullptr);
        TEST_PASS("EventParticleReaderRowJoin: EventReader interface accessible polymorphically");
    }

    // ── Phase 5: FeedParticleReader and FeedNodeReader ────────────────────────
    {
        namespace fs = std::filesystem;

        // Build a small in-memory ROOT file with two trees:
        //   "FeedParts" — four scalar float kinematic branches (PtEtaPhiE)
        //   "FeedNodes" — one scalar float branch + one fixed-size float array branch
        const auto tmpPath = fs::temp_directory_path() / "probe_p5_test.root";
        const std::string tmpStr = tmpPath.string();

        // ── Write fixture ──
        {
            TFile wf(tmpStr.c_str(), "RECREATE");
            if (wf.IsZombie())
                throw std::runtime_error("Phase 5: cannot create temp file " + tmpStr);

            // Particle tree
            TTree* pt = new TTree("FeedParts", "FeedParts");
            float fpt = 0, feta = 0, fphi = 0, fen = 0;
            pt->Branch("pt",  &fpt, "pt/F");
            pt->Branch("eta", &feta, "eta/F");
            pt->Branch("phi", &fphi, "phi/F");
            pt->Branch("en",  &fen,  "en/F");
            for (int i = 0; i < 10; ++i) {
                fpt = 1.0f + i; feta = 0.1f * i; fphi = 0.2f * i; fen = 5.0f + i;
                pt->Fill();
            }

            // Node tree: scalar + fixed-size array
            TTree* nt = new TTree("FeedNodes", "FeedNodes");
            float weight = 0;
            float arr[4] = {};
            nt->Branch("weight", &weight, "weight/F");
            nt->Branch("arr",     arr,    "arr[4]/F");
            for (int i = 0; i < 10; ++i) {
                weight = 10.0f + i;
                for (int j = 0; j < 4; ++j) arr[j] = static_cast<float>((i + 1) * (j + 1));
                nt->Fill();
            }

            wf.Write();
        }

        // ── FeedParticleReader test ──
        {
            std::unique_ptr<TFile> rf(TFile::Open(tmpStr.c_str(), "READ"));
            TEST_TRUE(rf && !rf->IsZombie());

            Probe::FeedParticleSpec pspec;
            pspec.label  = "photon";
            pspec.tree   = "FeedParts";
            pspec.coords = Probe::PtEtaPhiESpec{std::vector<Probe::BranchSpec>{
                {"pt",  Probe::BranchType::Float},
                {"eta", Probe::BranchType::Float},
                {"phi", Probe::BranchType::Float},
                {"en",  Probe::BranchType::Float}
            }};

            Probe::FeedParticleReader fpr(rf.get(), pspec, tmpStr);
            TEST_EQ(fpr.entryCount(), Long64_t(10));
            TEST_FALSE(fpr.treeName().empty());
            TEST_TRUE(fpr.treePtr() != nullptr);
            TEST_PASS("FeedParticleReader: entryCount / treeName / treePtr");

            // Read entry 0: pt=1, eta=0, phi=0, en=5
            Probe::Feed feed0;
            fpr.readEntry(0, feed0);
            TEST_EQ(feed0.index, Long64_t(0));
            TEST_TRUE(feed0.particle.count("photon") == 1);
            const Probe::Lorentz& p0 = feed0.particles("photon");
            TEST_TRUE(std::abs(p0.pt()  - 1.0) < 1e-4);
            TEST_TRUE(std::abs(p0.eta() - 0.0) < 1e-4);
            TEST_PASS("FeedParticleReader: readEntry(0) populates Feed.particle");

            // Read entry 3: pt=4, eta=0.3, phi=0.6, en=8
            Probe::Feed feed3;
            fpr.readEntry(3, feed3);
            const Probe::Lorentz& p3 = feed3.particles("photon");
            TEST_TRUE(std::abs(p3.pt()  - 4.0) < 1e-4);
            TEST_TRUE(std::abs(p3.eta() - 0.3) < 1e-4);
            TEST_PASS("FeedParticleReader: readEntry(3) correct kinematics");

            // FeedReader abstract interface
            Probe::FeedReader* fr = &fpr;
            TEST_EQ(fr->entryCount(), Long64_t(10));
            TEST_TRUE(fr->treePtr() != nullptr);
            TEST_PASS("FeedParticleReader: FeedReader interface accessible polymorphically");
        }

        // ── FeedNodeReader test ──
        {
            std::unique_ptr<TFile> rf(TFile::Open(tmpStr.c_str(), "READ"));
            TEST_TRUE(rf && !rf->IsZombie());

            Probe::FeedNodeSpec nspec;
            nspec.label    = "info";
            nspec.tree     = "FeedNodes";
            nspec.branches = {{"weight", Probe::BranchType::Float},
                              {"arr",    Probe::BranchType::Float}};

            Probe::FeedNodeReader fnr(rf.get(), nspec, tmpStr);
            TEST_EQ(fnr.entryCount(), Long64_t(10));
            TEST_PASS("FeedNodeReader: entryCount correct");

            // Entry 0: weight=10, arr=[1,2,3,4]
            Probe::Feed fn0;
            fnr.readEntry(0, fn0);
            TEST_EQ(fn0.index, Long64_t(0));
            TEST_TRUE(fn0.node.count("info") == 1);

            // Scalar branch → float AuxValue
            const float w0 = fn0.value<float>("info", "weight");
            TEST_TRUE(std::abs(w0 - 10.0f) < 1e-4f);
            TEST_PASS("FeedNodeReader: scalar branch read as float AuxValue");

            // Array branch → vector<float> AuxValue
            using VF = std::vector<float>;
            const VF& a0 = fn0.value<VF>("info", "arr");
            TEST_EQ(a0.size(), std::size_t(4));
            TEST_TRUE(std::abs(a0[0] - 1.0f) < 1e-4f);
            TEST_TRUE(std::abs(a0[3] - 4.0f) < 1e-4f);
            TEST_PASS("FeedNodeReader: array branch read as vector<float> AuxValue");

            // Entry 2: weight=12, arr=[3,6,9,12]
            Probe::Feed fn2;
            fnr.readEntry(2, fn2);
            const float w2 = fn2.value<float>("info", "weight");
            TEST_TRUE(std::abs(w2 - 12.0f) < 1e-4f);
            const VF& a2 = fn2.value<VF>("info", "arr");
            TEST_TRUE(std::abs(a2[2] - 9.0f) < 1e-4f);
            TEST_PASS("FeedNodeReader: readEntry(2) correct scalar + array values");

            // FeedReader abstract interface
            Probe::FeedReader* fr = &fnr;
            TEST_EQ(fr->entryCount(), Long64_t(10));
            TEST_FALSE(fr->treeName().empty());
            TEST_PASS("FeedNodeReader: FeedReader interface accessible polymorphically");
        }

        fs::remove(tmpPath);
    }

    // ── Phase 6: EventStream (ProbeConfig ctor) and FeedStream ───────────────
    if (fixtureAvailable()) {
        // Build a ProbeConfig matching the lambda fixture "protons" tree.
        Probe::ProbeConfig cfg;
        {
            Probe::EventParticleSpec pspec;
            pspec.label  = "protons";
            pspec.tree   = "Protons";
            pspec.coords = Probe::CartesianSpec{std::vector<Probe::BranchSpec>{
                {"pX",     Probe::BranchType::Double},
                {"pY",     Probe::BranchType::Double},
                {"pZ",     Probe::BranchType::Double},
                {"Energy", Probe::BranchType::Double}
            }};
            pspec.indexBranches = {{"event_index", Probe::BranchType::Int32}};
            cfg.eventParticles.push_back(std::move(pspec));
        }

        // New ctor: ProbeConfig + pre-computed bounds.
        Probe::EventStream evStream(kFixtureRoot, cfg, /*first=*/1, /*last=*/kNEvents);
        TEST_EQ(evStream.nEvents(), static_cast<std::size_t>(kNEvents));

        std::size_t eventCount = 0;
        bool allHave4 = true;
        while (evStream.next()) {
            ++eventCount;
            if (evStream.event().n("protons") != 4) allHave4 = false;
        }
        TEST_EQ(eventCount, static_cast<std::size_t>(kNEvents));
        TEST_TRUE(allHave4);
        TEST_PASS("EventStream (ProbeConfig ctor): iterates all events with correct particle counts");

        // index() tracks position
        TEST_EQ(evStream.index(), static_cast<std::size_t>(kNEvents - 1));
        TEST_PASS("EventStream (ProbeConfig ctor): index() correct after iteration");
    }

    {
        // FeedStream: build a temp file with one FeedParticle tree + one FeedNode tree.
        const auto tmpPath = fs::temp_directory_path() / "probe_p6_feed.root";
        const std::string tmpStr = tmpPath.string();

        {
            TFile wf(tmpStr.c_str(), "RECREATE");
            TTree* pt = new TTree("FeedParts", "FeedParts");
            float fpt = 0, feta = 0, fphi = 0, fen = 0;
            pt->Branch("pt",  &fpt, "pt/F");
            pt->Branch("eta", &feta, "eta/F");
            pt->Branch("phi", &fphi, "phi/F");
            pt->Branch("en",  &fen,  "en/F");
            TTree* nt = new TTree("FeedNodes", "FeedNodes");
            float wt = 0;
            nt->Branch("weight", &wt, "weight/F");
            for (int i = 0; i < 8; ++i) {
                fpt = float(i + 1); feta = 0.1f * i; fphi = 0.0f; fen = float(i + 10);
                wt  = float(i + 100);
                pt->Fill();
                nt->Fill();
            }
            wf.Write();
        }

        Probe::ProbeConfig fcfg;
        {
            Probe::FeedParticleSpec fps;
            fps.label  = "gamma";
            fps.tree   = "FeedParts";
            fps.coords = Probe::PtEtaPhiESpec{std::vector<Probe::BranchSpec>{
                {"pt",  Probe::BranchType::Float},
                {"eta", Probe::BranchType::Float},
                {"phi", Probe::BranchType::Float},
                {"en",  Probe::BranchType::Float}
            }};
            fcfg.feedParticles.push_back(std::move(fps));

            Probe::FeedNodeSpec fns;
            fns.label    = "meta";
            fns.tree     = "FeedNodes";
            fns.branches = {{"weight", Probe::BranchType::Float}};
            fcfg.feedNodes.push_back(std::move(fns));
        }

        Probe::FeedStream fstream(tmpStr, fcfg, /*first=*/0, /*last=*/7);
        TEST_EQ(fstream.entryCount(), Long64_t(8));
        TEST_PASS("FeedStream: entryCount() correct");

        std::size_t feedCount = 0;
        bool ptOk = true, weightOk = true;
        while (fstream.next()) {
            const auto& f = fstream.current();
            const float expectedPt = float(feedCount + 1);
            if (std::abs(f.particles("gamma").pt() - expectedPt) > 0.01f) ptOk = false;
            const float expectedW = float(feedCount + 100);
            if (std::abs(f.value<float>("meta", "weight") - expectedW) > 0.01f) weightOk = false;
            ++feedCount;
        }
        TEST_EQ(feedCount, std::size_t(8));
        TEST_TRUE(ptOk);
        TEST_TRUE(weightOk);
        TEST_PASS("FeedStream: iterates all entries with correct particle pt and node weight");

        fs::remove(tmpPath);
    }

    // ── Phase 7: configureProbe(ProbeConfig), activeMode, streamEvents/streamFeed
    if (fixtureAvailable()) {
        // configureProbe(ProbeConfig) — Event-only path uses the fixture "protons" tree.
        Probe::ProbeConfig evCfg;
        {
            Probe::EventParticleSpec pspec;
            pspec.label  = "protons";
            pspec.tree   = "Protons";
            pspec.coords = Probe::CartesianSpec{std::vector<Probe::BranchSpec>{
                {"pX",     Probe::BranchType::Double},
                {"pY",     Probe::BranchType::Double},
                {"pZ",     Probe::BranchType::Double},
                {"Energy", Probe::BranchType::Double}
            }};
            pspec.indexBranches = {{"event_index", Probe::BranchType::Int32}};
            evCfg.eventParticles.push_back(std::move(pspec));
        }

        Probe::ProbeParallel probe7ev;
        probe7ev.setCallbackMode(Probe::CallbackMode::WorkerThread);
        probe7ev.configureProbe(kFixtureRoot, evCfg, /*threads=*/2,
                                kNEvents, /*userRequested=*/true);

        TEST_EQ(probe7ev.eventCount(), static_cast<std::size_t>(kNEvents));
        TEST_TRUE(probe7ev.activeMode() == Probe::ActiveMode::Events);
        TEST_PASS("configureProbe(ProbeConfig) Event-only: eventCount + activeMode");

        // streamEvents callback receives all events with 4 protons each
        std::atomic<std::size_t> evSeen{0};
        std::atomic<bool> allHave4{true};
        probe7ev.streamEvents([&](const Probe::Event& ev, int) {
            ++evSeen;
            if (ev.n("protons") != 4) allHave4.store(false);
        });
        TEST_EQ(evSeen.load(), static_cast<std::size_t>(kNEvents));
        TEST_TRUE(allHave4.load());
        TEST_PASS("streamEvents: all events received with correct particle counts");
    }

    {
        // configureProbe(ProbeConfig) — Feed-only path.
        const auto tmpPath = fs::temp_directory_path() / "probe_p7_feed.root";
        const std::string tmpStr = tmpPath.string();
        {
            TFile wf(tmpStr.c_str(), "RECREATE");
            TTree* nt = new TTree("InfoTree", "InfoTree");
            float energy = 0;
            nt->Branch("energy", &energy, "energy/F");
            for (int i = 0; i < 12; ++i) { energy = float(i + 1); nt->Fill(); }
            wf.Write();
        }

        Probe::ProbeConfig fdCfg;
        {
            Probe::FeedNodeSpec fns;
            fns.label    = "info";
            fns.tree     = "InfoTree";
            fns.branches = {{"energy", Probe::BranchType::Float}};
            fdCfg.feedNodes.push_back(std::move(fns));
        }

        Probe::ProbeParallel probe7fd;
        probe7fd.setCallbackMode(Probe::CallbackMode::WorkerThread);
        probe7fd.configureProbe(tmpStr, fdCfg, /*threads=*/2,
                                12, /*userRequested=*/true);

        TEST_EQ(probe7fd.eventCount(), std::size_t(12));
        TEST_TRUE(probe7fd.activeMode() == Probe::ActiveMode::Feed);
        TEST_PASS("configureProbe(ProbeConfig) Feed-only: eventCount + activeMode");

        std::atomic<std::size_t> fdSeen{0};
        std::atomic<bool> energyOk{true};
        std::mutex fdMu;
        std::vector<float> energies;
        probe7fd.streamFeed([&](const Probe::Feed& f, int) {
            ++fdSeen;
            const float e = f.value<float>("info", "energy");
            std::lock_guard<std::mutex> lk(fdMu);
            energies.push_back(e);
            if (e < 0.9f || e > 12.1f) energyOk.store(false);
        });
        TEST_EQ(fdSeen.load(), std::size_t(12));
        TEST_TRUE(energyOk.load());
        TEST_PASS("streamFeed: all 12 feed entries received with valid energy values");

        fs::remove(tmpPath);
    }

    // ── Phase 8: validation — stream method dispatch and throw guards ─────────
    {
        // Build a tiny temp file for dispatch tests (Feed-only: scalar node tree).
        const auto tmpPath8 = fs::temp_directory_path() / "probe_p8_test.root";
        const std::string tmp8 = tmpPath8.string();
        {
            TFile wf(tmp8.c_str(), "RECREATE");
            TTree* nt = new TTree("NodeTree", "NodeTree");
            float v = 0;
            nt->Branch("val", &v, "val/F");
            for (int i = 0; i < 4; ++i) { v = float(i); nt->Fill(); }
            wf.Write();
        }

        // Feed-only ProbeConfig
        Probe::ProbeConfig fdOnly;
        {
            Probe::FeedNodeSpec fns;
            fns.label    = "data";
            fns.tree     = "NodeTree";
            fns.branches = {{"val", Probe::BranchType::Float}};
            fdOnly.feedNodes.push_back(std::move(fns));
        }

        // streamEvents on feed-only → throws
        if (fixtureAvailable()) {
            // Events-only probe (already configured above as probe7ev)
            // We need a freshly configured events-only probe for the streamFeed test.
            Probe::ProbeConfig evOnly;
            {
                Probe::EventParticleSpec ps;
                ps.label  = "protons"; ps.tree = "Protons";
                ps.coords = Probe::CartesianSpec{std::vector<Probe::BranchSpec>{
                    {"pX",Probe::BranchType::Double},{"pY",Probe::BranchType::Double},
                    {"pZ",Probe::BranchType::Double},{"Energy",Probe::BranchType::Double}}};
                ps.indexBranches = {{"event_index", Probe::BranchType::Int32}};
                evOnly.eventParticles.push_back(std::move(ps));
            }
            Probe::ProbeParallel probeEvOnly;
            probeEvOnly.setCallbackMode(Probe::CallbackMode::WorkerThread);
            probeEvOnly.configureProbe(kFixtureRoot, evOnly, 1, kNEvents, true);

            bool caught = false;
            try { probeEvOnly.streamFeed([](const Probe::Feed&, int){}); }
            catch (const std::runtime_error&) { caught = true; }
            TEST_TRUE(caught);
            TEST_PASS("streamFeed on events-only config throws");
        }

        {
            Probe::ProbeParallel probeFdOnly;
            probeFdOnly.setCallbackMode(Probe::CallbackMode::WorkerThread);
            probeFdOnly.configureProbe(tmp8, fdOnly, 1, 4, true);

            // streamEvents on feed-only → throws
            bool caught = false;
            try { probeFdOnly.streamEvents([](const Probe::Event&, int){}); }
            catch (const std::runtime_error&) { caught = true; }
            TEST_TRUE(caught);
            TEST_PASS("streamEvents on feed-only config throws");

            // stream(ce, cf) on Feed-only: only cf is invoked, ce never called
            std::atomic<std::size_t> ceCalled{0}, cfCalled{0};
            probeFdOnly.stream(
                [&](const Probe::Event&, int) { ++ceCalled; },
                [&](const Probe::Feed&,  int) { ++cfCalled; }
            );
            TEST_EQ(ceCalled.load(), std::size_t(0));
            TEST_EQ(cfCalled.load(), std::size_t(4));
            TEST_PASS("stream(ce,cf) on Feed-only: only cf invoked");
        }

        // stream(ce, cf) on Events-only: only ce is invoked
        if (fixtureAvailable()) {
            Probe::ProbeConfig evOnly2;
            {
                Probe::EventParticleSpec ps;
                ps.label  = "protons"; ps.tree = "Protons";
                ps.coords = Probe::CartesianSpec{std::vector<Probe::BranchSpec>{
                    {"pX",Probe::BranchType::Double},{"pY",Probe::BranchType::Double},
                    {"pZ",Probe::BranchType::Double},{"Energy",Probe::BranchType::Double}}};
                ps.indexBranches = {{"event_index", Probe::BranchType::Int32}};
                evOnly2.eventParticles.push_back(std::move(ps));
            }
            Probe::ProbeParallel probeEvOnly2;
            probeEvOnly2.setCallbackMode(Probe::CallbackMode::WorkerThread);
            probeEvOnly2.configureProbe(kFixtureRoot, evOnly2, 1, kNEvents, true);

            std::atomic<std::size_t> ceCalled2{0}, cfCalled2{0};
            probeEvOnly2.stream(
                [&](const Probe::Event&, int) { ++ceCalled2; },
                [&](const Probe::Feed&,  int) { ++cfCalled2; }
            );
            TEST_EQ(ceCalled2.load(), static_cast<std::size_t>(kNEvents));
            TEST_EQ(cfCalled2.load(), std::size_t(0));
            TEST_PASS("stream(ce,cf) on Events-only: only ce invoked");
        }

        fs::remove(tmpPath8);
    }

    // ── Phase 9: NanoAOD-shaped fixture + Mixed-mode end-to-end ──────────────
    {
        // Build a synthetic NanoAOD-shaped TTree: "Events" tree with variable-length
        // muon arrays (Muon_pt/eta/phi/mass) and per-entry scalars (genWeight, MET_pt).
        const auto nanoPath = fs::temp_directory_path() / "probe_p9_nano.root";
        const std::string nanoStr = nanoPath.string();
        constexpr int kNanoEvents = 10;

        {
            TFile wf(nanoStr.c_str(), "RECREATE");
            TTree* t = new TTree("Events", "Events");

            int   nMuon = 0;
            float muPt[10]{}, muEta[10]{}, muPhi[10]{}, muMass[10]{};
            float genWeight = 0, metPt = 0;

            t->Branch("nMuon",    &nMuon,   "nMuon/I");
            t->Branch("Muon_pt",   muPt,    "Muon_pt[nMuon]/F");
            t->Branch("Muon_eta",  muEta,   "Muon_eta[nMuon]/F");
            t->Branch("Muon_phi",  muPhi,   "Muon_phi[nMuon]/F");
            t->Branch("Muon_mass", muMass,  "Muon_mass[nMuon]/F");
            t->Branch("genWeight", &genWeight, "genWeight/F");
            t->Branch("MET_pt",    &metPt,     "MET_pt/F");

            for (int i = 0; i < kNanoEvents; ++i) {
                nMuon = (i % 2 == 0) ? 2 : 3;
                for (int j = 0; j < nMuon; ++j) {
                    muPt[j]   = 10.f * (i + 1) + j;
                    muEta[j]  = 0.1f * j;
                    muPhi[j]  = 0.2f * j;
                    muMass[j] = 0.105f;
                }
                genWeight = 1.0f + 0.1f * i;
                metPt     = 50.f + 5.f * i;
                t->Fill();
            }
            wf.Write();
        }

        // Build Mixed ProbeConfig:
        //   EventParticleSpec — reads Muon arrays (array-style, no index branch)
        //   FeedNodeSpec      — reads genWeight + MET_pt scalars from same tree
        Probe::ProbeConfig mixCfg;
        {
            Probe::EventParticleSpec ms;
            ms.label  = "muon";
            ms.tree   = "Events";
            ms.coords = Probe::PtEtaPhiMSpec{std::vector<Probe::BranchSpec>{
                {"Muon_pt",   Probe::BranchType::Float},
                {"Muon_eta",  Probe::BranchType::Float},
                {"Muon_phi",  Probe::BranchType::Float},
                {"Muon_mass", Probe::BranchType::Float}
            }};
            // indexBranches empty → per-entry array source
            mixCfg.eventParticles.push_back(std::move(ms));

            Probe::FeedNodeSpec fs;
            fs.label    = "evInfo";
            fs.tree     = "Events";
            fs.branches = {{"genWeight", Probe::BranchType::Float},
                           {"MET_pt",    Probe::BranchType::Float}};
            mixCfg.feedNodes.push_back(std::move(fs));
        }

        Probe::ProbeParallel probeMix;
        probeMix.setCallbackMode(Probe::CallbackMode::WorkerThread);
        // Use 1 thread so ce/cf for the same entry are called in order from one thread
        probeMix.configureProbe(nanoStr, mixCfg, /*threads=*/1,
                                kNanoEvents, /*userRequested=*/true);

        TEST_EQ(probeMix.eventCount(), std::size_t(kNanoEvents));
        TEST_TRUE(probeMix.activeMode() == Probe::ActiveMode::Mixed);
        TEST_PASS("Phase 9: configureProbe Mixed mode — eventCount + activeMode");

        // Run stream(ce, cf): verify both callbacks are called per entry,
        // muon count alternates 2/3, and e.index == f.index (synchronization).
        std::vector<std::size_t> muonCounts;
        std::vector<float>       genWeights;
        bool indicesMatch = true;
        Long64_t lastEvIndex = -2;

        probeMix.stream(
            [&](const Probe::Event& e, int) {
                muonCounts.push_back(e.n("muon"));
                lastEvIndex = e.index;
            },
            [&](const Probe::Feed& f, int) {
                genWeights.push_back(f.value<float>("evInfo", "genWeight"));
                if (f.index != lastEvIndex) indicesMatch = false;
            }
        );

        TEST_EQ(muonCounts.size(), std::size_t(kNanoEvents));
        TEST_EQ(genWeights.size(), std::size_t(kNanoEvents));
        TEST_TRUE(indicesMatch);
        TEST_PASS("Phase 9: stream(ce,cf) Mixed — both callbacks called, e.index == f.index");

        // Verify muon counts alternate 2, 3, 2, 3...
        bool muonCountOk = true;
        for (std::size_t i = 0; i < muonCounts.size(); ++i)
            if (muonCounts[i] != (i % 2 == 0 ? 2u : 3u)) muonCountOk = false;
        TEST_TRUE(muonCountOk);
        TEST_PASS("Phase 9: alternating muon counts (2,3,2,3,...) correct");

        // Verify genWeights: entry i → 1.0 + 0.1*i
        bool genWeightOk = true;
        for (std::size_t i = 0; i < genWeights.size(); ++i) {
            const float expected = 1.0f + 0.1f * static_cast<float>(i);
            if (std::abs(genWeights[i] - expected) > 0.01f) genWeightOk = false;
        }
        TEST_TRUE(genWeightOk);
        TEST_PASS("Phase 9: genWeight values match expected 1.0 + 0.1*i");

        fs::remove(nanoPath);
    }

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
