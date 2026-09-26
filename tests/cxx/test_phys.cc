// What `Phys` promises (P8-S02, 13 §2).
//
// Three of these blocks are `legacy/tests/test_utils_hardening.cc` ported: the property table's
// bounds check, the PDG table's lookups, and the kinematics edge cases. They were the only tests the
// legacy `Physics` had and each one was written after the bug it describes.
//
// The rest are this step's own, and two of them are its Verification rows:
//
//   * **PDG** — the thirteen rows are checked against Pythia's `ParticleData`, which is the only
//     way a hand-written mass table stays true. Pythia keeps five decimals, so that is the
//     tolerance; anything looser would not notice a digit transposed;
//   * **Jets** — `jetDefinition("antikt:0.4")` is compared with the `fastjet::JetDefinition` written
//     out by hand, through FastJet's own `description()`, since it has no equality operator.
//
// And one that is neither: **Δφ terminates**. The legacy wrap was a `while` loop, and ±∞ made it
// spin forever. So does HepMC3's own `FourVector::delta_phi`. If this file ever hangs, that is the
// bug back.

#include <chrono>
#include <cmath>
#include <limits>
#include <optional>
#include <string>
#include <vector>

#include "Core/Errors.hh"
#include "Phys.hh"
#include "check.hh"

#include "HepMC3/GenEvent.h"
#include "HepMC3/GenParticle.h"
#include "HepMC3/GenVertex.h"
#include "Pythia8/Pythia.h"
#include "fastjet/JetDefinition.hh"

namespace {

    constexpr double kProtonMass = 0.938272;

    bool near(double left, double right, double tolerance) {
        return std::abs(left - right) <= tolerance;
    }

    // ── ported: the property table ───────────────────────────────────────────
    // `EventIndex` has no extractor on purpose, and asking for one used to read past the end of the
    // table. The bounds check is the test.
    void propertyTable() {
        const Phys::FourVector particle{1.0, 2.0, 3.0, 10.0};   // px py pz E

        CHECK(near(Phys::valueOf(particle, Phys::ParticleProperty::Energy_Net), 10.0, 1e-12));
        CHECK(near(Phys::valueOf(particle, Phys::ParticleProperty::Momentum_Transverse),
                   std::sqrt(5.0), 1e-12));
        CHECK(near(Phys::valueOf(particle, Phys::ParticleProperty::Momentum_Z), 3.0, 1e-12));
        CHECK_EQ(std::string(Phys::nameOf(Phys::ParticleProperty::Rapidity)),
                 std::string("Rapidity"));

        CHECK_THROWS(Phys::traitsOf(Phys::ParticleProperty::EventIndex), Core::Error);

        const std::vector<Phys::FourVector> event{particle, particle, particle};
        CHECK(near(Phys::valueOf(event, Phys::EventProperty::Multiplicity), 3.0, 1e-12));

        // Names round-trip, including the two historical short spellings.
        CHECK(Phys::particleProperty("Momentum_Transverse") ==
              Phys::ParticleProperty::Momentum_Transverse);
        CHECK(Phys::particleProperty("Mass") == Phys::ParticleProperty::Mass_Invariant);
        CHECK(Phys::particleProperty("Energy") == Phys::ParticleProperty::Energy_Net);
        CHECK(!Phys::particleProperty("Nonsense").has_value());
        CHECK_THROWS(Phys::requireParticleProperty("Nonsense"), Core::Error);
        CHECK(Phys::eventProperty("Multiplicity") == Phys::EventProperty::Multiplicity);
    }

    // ── ported: the PDG table, plus the charge defect it had ─────────────────
    void pdgTable() {
        CHECK(near(Phys::Pdg::mass(3122), 1.115683, 1e-9));      // Lambda
        CHECK(near(Phys::Pdg::mass(2212), kProtonMass, 1e-9));
        CHECK_EQ(std::string(Phys::Pdg::name(-211)), std::string("pi+"));  // resolves to |id|
        CHECK_THROWS(Phys::Pdg::info(999999), Core::Error);
        CHECK(!Phys::Pdg::known(999999));
        CHECK(Phys::Pdg::known(-2212));

        // The legacy defect: `Physics::particle(-211).charge3` was +3, so a pi- was positive.
        CHECK_EQ(Phys::Pdg::charge3(211), 3);
        CHECK_EQ(Phys::Pdg::charge3(-211), -3);
        CHECK_EQ(Phys::Pdg::charge3(-2212), -3);
        CHECK(near(Phys::Pdg::charge(-11), 1.0, 1e-12));         // a positron is +1
        CHECK_EQ(Phys::Pdg::info(-211).charge3, 3);              // the entry is the positive state's
    }

    // ── the numbering scheme, which is arithmetic rather than a table ────────
    void pdgPredicates() {
        CHECK(Phys::Pdg::isNeutrino(12) && Phys::Pdg::isNeutrino(-14) && Phys::Pdg::isNeutrino(16));
        CHECK(!Phys::Pdg::isNeutrino(11) && !Phys::Pdg::isNeutrino(13));
        CHECK(Phys::Pdg::isChargedLepton(11) && Phys::Pdg::isChargedLepton(-15));
        CHECK(!Phys::Pdg::isChargedLepton(12));
        CHECK(Phys::Pdg::isLepton(12) && Phys::Pdg::isLepton(11) && !Phys::Pdg::isLepton(211));

        CHECK(Phys::Pdg::isQuark(5) && !Phys::Pdg::isQuark(21));
        CHECK(Phys::Pdg::isGluon(21) && Phys::Pdg::isPhoton(22));
        CHECK(Phys::Pdg::isBoson(23) && Phys::Pdg::isBoson(24) && Phys::Pdg::isBoson(25));

        CHECK(Phys::Pdg::isMeson(211) && Phys::Pdg::isMeson(111) && Phys::Pdg::isMeson(-321));
        CHECK(Phys::Pdg::isMeson(130) && Phys::Pdg::isMeson(310));   // K0_L and K0_S are mesons
        CHECK(Phys::Pdg::isBaryon(2212) && Phys::Pdg::isBaryon(-2112) && Phys::Pdg::isBaryon(3122));
        CHECK(!Phys::Pdg::isBaryon(211) && !Phys::Pdg::isMeson(2212));
        CHECK(Phys::Pdg::isHadron(211) && Phys::Pdg::isHadron(2212) && !Phys::Pdg::isHadron(11));

        // A nucleus is ten digits and must not read as a baryon.
        const int deuteron = 1000010020;
        CHECK(Phys::Pdg::isNucleus(deuteron));
        CHECK(!Phys::Pdg::isBaryon(deuteron) && !Phys::Pdg::isMeson(deuteron));
    }

    // ── Verification row: the table against Pythia's ─────────────────────────
    // Pythia's `ParticleData` is the authority the rest of the run already uses, so a mass here that
    // disagrees with it would put two different numbers in one analysis.
    void pdgAgreesWithPythia() {
        Pythia8::Pythia pythia("", /*printBanner=*/false);
        if (pythia.particleData.findParticle(2212) == nullptr) {
            std::fprintf(stderr, "NOTE: no Pythia particle data (PYTHIA8DATA); PDG row skipped\n");
            return;
        }
        for (const Phys::Pdg::Info& entry : Phys::Pdg::kParticles) {
            const Pythia8::ParticleDataEntryPtr known =
                pythia.particleData.findParticle(entry.pdgId);
            CHECK(known != nullptr);
            if (known == nullptr) continue;
            // Pythia stores five decimals, so that is as close as two tables can agree.
            CHECK(near(entry.mass, known->m0(), 1e-5));
            CHECK_EQ(entry.charge3, known->chargeType());
            CHECK_EQ(std::string(entry.name), known->name());
        }
    }

    // ── ported: kinematics edges, and the guard this step added ──────────────
    void kinematicsEdges() {
        // A spacelike four-vector (m^2 < 0, from rounding) clamps to 0 rather than giving NaN.
        CHECK_EQ(Phys::invariantMass(1.0, 2.0, 0.0, 0.0), 0.0);
        CHECK(near(Phys::invariantMass(10.0, 1.0, 2.0, 3.0), std::sqrt(100.0 - 14.0), 1e-12));

        // Delta-phi wraps into [-pi, pi], the same range the legacy loop produced.
        CHECK(near(Phys::deltaPhi(3.0, -3.0), 6.0 - 2.0 * M_PI, 1e-12));
        CHECK(near(Phys::deltaPhi(0.1, -0.1), 0.2, 1e-12));
        CHECK(near(std::abs(Phys::deltaPhi(M_PI, 0.0)), M_PI, 1e-12));
        CHECK(std::abs(Phys::deltaPhi(100.0, 0.0)) <= M_PI);

        // The design note. The legacy `while` loop never returns for these, and neither does
        // HepMC3's `FourVector::delta_phi`; a run would hang rather than fail.
        const auto started = std::chrono::steady_clock::now();
        const double infinite = std::numeric_limits<double>::infinity();
        CHECK(std::isnan(Phys::deltaPhi(infinite, 0.0)));
        CHECK(std::isnan(Phys::deltaPhi(-infinite, 0.0)));
        CHECK(std::isnan(Phys::deltaPhi(std::numeric_limits<double>::quiet_NaN(), 0.0)));
        const auto took = std::chrono::steady_clock::now() - started;
        CHECK(std::chrono::duration_cast<std::chrono::milliseconds>(took).count() < 1000);

        // Two vectors, and the separation between them.
        const Phys::FourVector one{1.0, 0.0, 0.0, 1.0};
        const Phys::FourVector two{0.0, 1.0, 0.0, 1.0};
        CHECK(near(Phys::deltaPhi(one, two), -M_PI / 2.0, 1e-12));
        CHECK(near(Phys::deltaR(one, two), M_PI / 2.0, 1e-12));
        CHECK(near(Phys::invariantMass(one, two), std::sqrt(4.0 - 2.0), 1e-12));

        // A particle along the beam has infinite eta, and deltaR with it is infinite rather than a
        // large number that would sit in the outermost bin.
        const Phys::FourVector along{0.0, 0.0, 5.0, 5.0};
        CHECK(std::isinf(along.eta()));
        CHECK(std::isinf(Phys::deltaR(along, one)));

        // The system's mass adds the vectors first.
        CHECK(near(Phys::invariantMass(std::vector<Phys::FourVector>{one, two}),
                   std::sqrt(2.0), 1e-12));
    }

    // ── DIS invariants, checked by identities rather than by repeating them ──
    void disInvariants() {
        const double lepton_energy = 27.5;
        const double scattered_energy = 10.0;
        const double proton_energy = 920.0;

        const Phys::FourVector lepton{0.0, 0.0, -lepton_energy, lepton_energy};
        const Phys::FourVector scattered{0.0, 0.0, scattered_energy, scattered_energy};  // 180 deg
        const Phys::FourVector proton{
            0.0, 0.0, proton_energy,
            std::sqrt(proton_energy * proton_energy + kProtonMass * kProtonMass)};

        const Phys::Dis found = Phys::disKinematics(lepton, scattered, proton);

        // Q^2 = 2 E E' (1 - cos theta) for massless leptons; theta = pi here.
        CHECK(near(found.q2, 2.0 * lepton_energy * scattered_energy * 2.0, 1e-6));

        // Q^2 = x y (s - M^2): ties x and y together, and fails if either is wrong.
        const Phys::FourVector total = lepton + proton;
        const double s = Phys::dot(total, total);
        CHECK(near(found.x * found.y * (s - kProtonMass * kProtonMass), found.q2, 1e-6));

        // W^2 = M^2 + Q^2 (1 - x) / x.
        CHECK(near(found.w2,
                   kProtonMass * kProtonMass + found.q2 * (1.0 - found.x) / found.x, 1e-6));

        // nu = (P.q) / M, and M nu = (W^2 + Q^2 - M^2) / 2.
        CHECK(near(kProtonMass * found.nu,
                   (found.w2 + found.q2 - kProtonMass * kProtonMass) / 2.0, 1e-6));

        CHECK(found.x > 0.0 && found.x < 1.0);
        CHECK(found.y > 0.0 && found.y <= 1.0);
        CHECK(!found.photoproduction());

        // Photoproduction is the other limit: a lepton that barely scattered.
        const Phys::FourVector grazing{0.001, 0.0, -20.0, 20.0};
        const Phys::Dis quasi_real = Phys::disKinematics(lepton, grazing, proton);
        CHECK(quasi_real.q2 < 1.0);
        CHECK(quasi_real.photoproduction());

        // A degenerate event gives zeros rather than infinities: one bad event cannot poison a
        // histogram.
        const Phys::FourVector nothing{0.0, 0.0, 0.0, 0.0};
        const Phys::Dis empty = Phys::disKinematics(nothing, nothing, nothing);
        CHECK(empty.x == 0.0 && empty.y == 0.0 && empty.nu == 0.0);
    }

    // ── selectors, on an event built by hand ─────────────────────────────────
    HepMC3::GenEvent buildEvent() {
        using namespace HepMC3;
        GenEvent event(Units::GEV, Units::MM);

        GenParticlePtr beam_lepton = std::make_shared<GenParticle>(
            FourVector{0.0, 0.0, -27.5, 27.5}, 11, Phys::Status::Beam);
        GenParticlePtr beam_proton = std::make_shared<GenParticle>(
            FourVector{0.0, 0.0, 920.0, 920.0004}, 2212, Phys::Status::Beam);

        GenVertexPtr vertex = std::make_shared<GenVertex>();
        vertex->add_particle_in(beam_lepton);
        vertex->add_particle_in(beam_proton);

        // The scattered lepton, a softer one to be outranked by it, a pion, a neutrino, and a
        // decayed particle that must not count as final.
        GenParticlePtr scattered = std::make_shared<GenParticle>(
            FourVector{1.0, 0.0, 10.0, 10.05}, 11, Phys::Status::Final);
        GenParticlePtr soft = std::make_shared<GenParticle>(
            FourVector{0.2, 0.1, 1.0, 1.03}, 11, Phys::Status::Final);
        GenParticlePtr pion = std::make_shared<GenParticle>(
            FourVector{2.0, 1.0, 3.0, 3.8}, 211, Phys::Status::Final);
        GenParticlePtr neutrino = std::make_shared<GenParticle>(
            FourVector{0.5, 0.5, 4.0, 4.06}, 12, Phys::Status::Final);
        GenParticlePtr decayed = std::make_shared<GenParticle>(
            FourVector{0.0, 0.0, 6.0, 6.5}, 3122, Phys::Status::Decayed);

        for (const GenParticlePtr& particle : {scattered, soft, pion, neutrino, decayed})
            vertex->add_particle_out(particle);
        event.add_vertex(vertex);
        event.set_beam_particles(beam_lepton, beam_proton);
        return event;
    }

    void selectors() {
        const HepMC3::GenEvent event = buildEvent();

        // Status 1 and nothing else: the decayed Lambda is present in the event and is not final.
        CHECK_EQ(Phys::finalState(event).size(), std::size_t{4});
        CHECK_EQ(Phys::withStatus(event, Phys::Status::Decayed).size(), std::size_t{1});
        CHECK_EQ(Phys::beams(event).size(), std::size_t{2});

        CHECK_EQ(Phys::withPid(event, 11).size(), std::size_t{3});         // two final and the beam
        CHECK_EQ(Phys::withPid(event, 211).size(), std::size_t{1});

        const Phys::Particle lepton_beam = Phys::beam(event, 11);
        CHECK(lepton_beam && lepton_beam->status() == Phys::Status::Beam);
        CHECK(!Phys::beam(event, 22));                                     // no photon beam

        const Phys::Particle scattered = Phys::scatteredLepton(event);
        CHECK(scattered != nullptr);
        if (scattered) CHECK(near(scattered->momentum().e(), 10.05, 1e-9));  // not the soft one

        // An acceptance is a cut written as data.
        Phys::Acceptance acceptance;
        acceptance.pt_min = 1.0;
        CHECK_EQ(Phys::finalState(event, acceptance).size(), std::size_t{2});  // scattered and pion

        acceptance = Phys::Acceptance{};
        acceptance.visible = true;
        CHECK_EQ(Phys::finalState(event, acceptance).size(), std::size_t{3});  // no neutrino

        acceptance = Phys::Acceptance{};
        acceptance.eta_max = 2.0;
        const Phys::Particles central = Phys::finalState(event, acceptance);
        for (const Phys::Particle& particle : central)
            CHECK(std::abs(particle->momentum().eta()) <= 2.0);

        // No cut set keeps everything, including a particle with infinite eta.
        CHECK_EQ(Phys::finalState(event, Phys::Acceptance{}).size(), std::size_t{4});

        CHECK_EQ(Phys::momenta(Phys::finalState(event)).size(), std::size_t{4});

        // The event's own DIS invariants, found from its beams.
        const std::optional<Phys::Dis> invariants = Phys::disKinematics(event);
        CHECK(invariants.has_value());
        if (invariants) CHECK(invariants->q2 > 0.0);

        // An event with no scattered lepton — the Whizard EPA case (P7-S04) — says so.
        HepMC3::GenEvent photonic(HepMC3::Units::GEV, HepMC3::Units::MM);
        CHECK(!Phys::disKinematics(photonic).has_value());
        CHECK(!Phys::scatteredLepton(photonic));
    }

    // ── Verification row: a definition from a string is FastJet's own ────────
    void jetDefinitions() {
        const fastjet::JetDefinition byHand(fastjet::antikt_algorithm, 0.4);
        const fastjet::JetDefinition parsed = Phys::jetDefinition("antikt:0.4");
        CHECK_EQ(Phys::describe(parsed), byHand.description());
        CHECK(parsed.jet_algorithm() == fastjet::antikt_algorithm);
        CHECK(near(parsed.R(), 0.4, 1e-12));
        CHECK(parsed.recombination_scheme() == fastjet::E_scheme);

        // The spellings, and kT.
        for (const char* spelling : {"antikt:0.4", "anti-kt:0.4", "akt:0.4", "AntiKt:0.4"})
            CHECK_EQ(Phys::describe(Phys::jetDefinition(spelling)), byHand.description());

        const fastjet::JetDefinition kt(fastjet::kt_algorithm, 1.0);
        CHECK_EQ(Phys::describe(Phys::jetDefinition("kt:1.0")), kt.description());

        const fastjet::JetDefinition cambridge(fastjet::cambridge_algorithm, 0.7);
        CHECK_EQ(Phys::describe(Phys::jetDefinition("ca:0.7")), cambridge.description());
        CHECK_EQ(Phys::describe(Phys::jetDefinition("cambridge-aachen:0.7")),
                 cambridge.description());

        // A recombination scheme, named.
        const fastjet::JetDefinition with_et(fastjet::antikt_algorithm, 0.4, fastjet::Et_scheme);
        CHECK_EQ(Phys::describe(Phys::jetDefinition("antikt:0.4:scheme=Et")),
                 with_et.description());

        // genkt at p = -1 is anti-kT, which FastJet says itself.
        const fastjet::JetDefinition genkt(fastjet::genkt_algorithm, 0.4, -1.0);
        CHECK_EQ(Phys::describe(Phys::jetDefinition("genkt:0.4:p=-1")), genkt.description());
        const fastjet::JetDefinition genkt_half(fastjet::genkt_algorithm, 0.4, 0.5);
        CHECK_EQ(Phys::describe(Phys::jetDefinition("genkt:0.4:p=0.5")), genkt_half.description());

        // SISCone comes back as a plugin, and owns it: valgrind found this leaked once (00/B25).
        const fastjet::JetDefinition siscone = Phys::jetDefinition("siscone:0.7");
        CHECK(siscone.jet_algorithm() == fastjet::plugin_algorithm);
        CHECK(Phys::describe(siscone).find("SISCone") != std::string::npos);
        CHECK(!Phys::threadSafe(siscone));          // never, in any build (00/B31)
        CHECK(!Phys::threadSafe(byHand));           // nor this one, in this build

        // What a typo costs: a message, before the run.
        CHECK_THROWS(Phys::jetDefinition("antikt"), Core::Error);          // no radius
        CHECK_THROWS(Phys::jetDefinition("antikt:0.4:0.75"), Core::Error); // unnamed parameter
        CHECK_THROWS(Phys::jetDefinition("antikt:zero"), Core::Error);
        CHECK_THROWS(Phys::jetDefinition("antikt:0"), Core::Error);
        CHECK_THROWS(Phys::jetDefinition("antikt:-0.4"), Core::Error);
        CHECK_THROWS(Phys::jetDefinition("nosuchalgorithm:0.4"), Core::Error);
        CHECK_THROWS(Phys::jetDefinition("antikt:0.4:scheme=nonsense"), Core::Error);
        CHECK_THROWS(Phys::jetDefinition("antikt:0.4:radius=0.5"), Core::Error);
        CHECK_THROWS(Phys::jetDefinition(""), Core::Error);
    }

    // ── clustering, which is the reason the definition exists ────────────────
    void clustering() {
        // Two well-separated pairs: anti-kT with R = 0.4 must find two jets, and their energies
        // must add up to what went in.
        std::vector<Phys::FourVector> momenta{
            {10.0, 0.0, 0.0, 10.0},  {10.2, 0.3, 0.1, 10.21},
            {-8.0, 0.0, 1.0, 8.06},  {-8.1, -0.2, 1.1, 8.18},
        };
        const std::vector<Phys::FourVector> jets =
            Phys::cluster(momenta, Phys::jetDefinition("antikt:0.4"));
        CHECK_EQ(jets.size(), std::size_t{2});

        double clustered = 0.0;
        for (const Phys::FourVector& jet : jets) clustered += jet.e();
        double given = 0.0;
        for (const Phys::FourVector& momentum : momenta) given += momentum.e();
        CHECK(near(clustered, given, 1e-9));

        // Hardest first.
        if (jets.size() == 2) CHECK(jets[0].perp() >= jets[1].perp());

        // A pT cut drops the softer one; an empty event gives no jets rather than throwing.
        CHECK_EQ(Phys::cluster(momenta, Phys::jetDefinition("antikt:0.4"), 18.0).size(),
                 std::size_t{1});
        CHECK_EQ(Phys::cluster({}, Phys::jetDefinition("antikt:0.4")).size(), std::size_t{0});

        // The same four particles with R = 4.0 are one jet: the definition really is used.
        CHECK_EQ(Phys::cluster(momenta, Phys::jetDefinition("antikt:4.0")).size(), std::size_t{1});
    }

}  // namespace

int main() {
    propertyTable();
    pdgTable();
    pdgPredicates();
    pdgAgreesWithPythia();
    kinematicsEdges();
    disInvariants();
    selectors();
    jetDefinitions();
    clustering();
    return check::finish("phys");
}
