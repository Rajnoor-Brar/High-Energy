// tests/cxx/test_module_kit.cc — utils/Module.hh: the config view, events from HepMC3, σ and ΣW, the
// scaling rule (fill raw, scale once), the report, and a truncated stream.
// requires: hepmc3 toml root

#include "Module.hh"

#include "HepMC3/WriterAscii.h"
#include "TFile.h"
#include "TH1D.h"

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>

static int failures = 0;
#define CHECK(cond)                                                                   \
    do {                                                                              \
        if (!(cond)) {                                                                \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);      \
            ++failures;                                                               \
        }                                                                             \
    } while (0)

namespace fs = std::filesystem;
static const fs::path HERE = "output/tests/cxx/module_kit";

// Ten events: event i has weight 1 + i/10 and σ = 100 + i pb; a beam proton in, one pion of pT = i + 0.5 out.
static void writeEvents(const fs::path& path, int n) {
    HepMC3::WriterAscii writer(path.string());
    for (int i = 0; i < n; ++i) {
        HepMC3::GenEvent event(HepMC3::Units::GEV, HepMC3::Units::MM);
        event.set_event_number(i);
        event.weights() = {1.0 + i / 10.0};
        auto xs = std::make_shared<HepMC3::GenCrossSection>();
        event.set_cross_section(xs);
        xs->set_cross_section(100.0 + i, 1.0);
        auto vertex = std::make_shared<HepMC3::GenVertex>();
        vertex->add_particle_in(std::make_shared<HepMC3::GenParticle>(HepMC3::FourVector(0, 0, 10, 10), 2212, 4));
        vertex->add_particle_out(std::make_shared<HepMC3::GenParticle>(HepMC3::FourVector(i + 0.5, 0, 0, i + 0.5), 211, 1));
        event.add_vertex(vertex);
        writer.write_event(event);
    }
    writer.close();
}

static std::string slurp(const fs::path& path) {
    std::ifstream in(path);
    return std::string(std::istreambuf_iterator<char>(in), {});
}

static Module::Job job(const std::vector<std::string>& args) {
    std::vector<char*> argv{const_cast<char*>("test_module_kit")};
    for (const auto& a : args) argv.push_back(const_cast<char*>(a.c_str()));
    return Module::Job(static_cast<int>(argv.size()), argv.data());
}

int main() {
    fs::remove_all(HERE);
    fs::create_directories(HERE);
    const fs::path events = HERE / "ten.hepmc", config = HERE / "config.toml", output = HERE / "out.partial.root";
    writeEvents(events, 10);
    std::ofstream(config) << "tolerance = 0.25\nbins = 4\nname = \"x\"\nlist = [\"a\", \"b\"]\n"
                             "[quantities]\nenergy = 7000\n"
                             "[standard.pythia_cmnd]\npath = \"/tmp/card.cmnd\"\nparts = [\"base.cmnd\", \"point.cmnd\"]\n";

    // ── the config, with defaults following the type ──
    {
        auto j = job({config.string(), "--input=" + events.string(), "--output", output.string(), "--events=10"});
        CHECK(j.config().get("tolerance", 0.15) == 0.25);
        CHECK(j.config().get("bins", 100) == 4);
        CHECK(j.config().get("absent", 7) == 7);
        CHECK(j.config().get("name", "y") == "x");
        CHECK(j.config().list("list") == (std::vector<std::string>{"a", "b"}));
        CHECK(j.quantities().get("energy", 0.0) == 7000.0);                 // an integer read as a double
        CHECK(j.standard("pythia_cmnd") == "/tmp/card.cmnd");
        CHECK(j.standardParts("pythia_cmnd").size() == 2);
        CHECK(j.hasInput() && j.input() == events.string() && j.output() == output.string());

        // ── events, ΣW, σ from the last event; fill raw, scale once, as a density ──
        Module::RootOut out(j.output());
        auto* pt = out.book<TH1D>("Kit/pt", ";p_{T}", 5, 0.0, 10.0);
        double sumW = 0;
        long seen = 0;
        for (const Module::Event& event : j.events()) {
            CHECK(event.index == seen);
            ++seen, sumW += event.weight();
            pt->Fill(event.hepmc().particles().back()->momentum().perp(), event.weight());
        }
        CHECK(seen == 10 && j.count() == 10);
        CHECK(std::fabs(j.sumW() - sumW) < 1e-12 && std::fabs(sumW - 14.5) < 1e-12);
        CHECK(j.crossSectionPb() == 109.0);                                    // the last event's (L2)
        out.scale(j.crossSectionPb() / j.sumW(), "width");
        CHECK(std::fabs(pt->Integral("width") - 109.0) < 1e-9);               // σ exactly, as a density
        CHECK(j.finish() == Module::Ok);
    }
    {
        std::unique_ptr<TFile> file(TFile::Open(output.string().c_str()));
        CHECK(file && !file->IsZombie());
        auto* pt = file ? dynamic_cast<TH1D*>(file->Get("Kit/pt")) : nullptr;
        CHECK(pt && std::fabs(pt->Integral("width") - 109.0) < 1e-9);
        const std::string report = slurp(output.string() + ".json");
        CHECK(report.find("\"events\": 10") != std::string::npos);
        CHECK(report.find("\"sigma_from\": \"events\"") != std::string::npos);
    }

    // ── σ from a sidecar when one is given ──
    {
        std::ofstream(HERE / "side.json") << "{\n  \"written\": 10,\n  \"sigma_pb\": 123.5,\n  \"sigma_err_pb\": 0.5\n}\n";
        auto j = job({config.string(), "--input=" + events.string(), "--sidecar=" + (HERE / "side.json").string()});
        for (const Module::Event& event : j.events()) (void)event;
        CHECK(j.crossSectionPb() == 123.5 && j.crossSectionErrPb() == 0.5);
    }

    // ── a truncated stream: the complete events are read, the count says how many ──
    {
        const std::string text = slurp(events);
        const auto cut = text.rfind("\nE ");                                   // the last event starts here
        std::ofstream(HERE / "cut.hepmc") << text.substr(0, cut + 1) << "E 9 1 1\nU GEV MM\n";
        auto j = job({config.string(), "--input=" + (HERE / "cut.hepmc").string(), "--output=" + (HERE / "cut.root").string()});
        long seen = 0;
        for (const Module::Event& event : j.events()) (void)event, ++seen;
        CHECK(seen < 10 && j.count() == seen);
        CHECK(j.finish() == Module::Ok);
        CHECK(slurp((HERE / "cut.root").string() + ".json").find("\"events\": " + std::to_string(seen)) != std::string::npos);
    }

    std::printf("test_module_kit: %s\n", failures ? "FAILED" : "ok");
    return failures ? 1 : 0;
}
