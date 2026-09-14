// Tests for the audit-driven hardening passes (Phases 1–3):
//   - Physics::traitsOf bounds checks (EventIndex must throw, not read OOB)
//   - Physics::Particles PDG table lookups
//   - Physics::Kinematics edge cases (m² < 0, Δφ wrapping)
//   - Utility::Toml validators reject invalid numerics
//   - Utility::Paths project-root anchoring
//   - Config readers reject negative/zero values that previously wrapped
//   - Monitor::writeTextFile survives unwritable paths (warns, no throw)

#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>

#include "test_assert.hh"

#include "Physics.hh"
#include "Utility.hh"
#include "Config.hh"
#include "Monitor.hh"

namespace {
    std::string writeTempConfig(const std::string& name, const std::string& body) {
        const std::filesystem::path dir = "output/Lambda/test_hardening";
        std::filesystem::create_directories(dir);
        const std::filesystem::path path = dir / name;
        std::ofstream out(path);
        out << body;
        return path.string();
    }

    bool readThrows(const std::string& configBody, const std::string& fileName) {
        Config::Events   events;
        Config::Watch    watch;
        Config::Register reg;
        const std::string path = writeTempConfig(fileName, configBody);
        try {
            Config::readConfigValues(path, "test_hardening", events, watch, reg);
        } catch (const std::runtime_error&) {
            return true;
        }
        return false;
    }
}

int main() {
    std::cout << "── test_utils_hardening ─────────────────────────────────────\n";

    // ── Physics::traitsOf ────────────────────────────────────────────────────
    {
        const Physics::Lorentz p(1.0, 2.0, 3.0, 10.0);  // px py pz E
        TEST_NEAR(Physics::traitsOf(Physics::ParticleProperty::Energy_Net).extract(p), 10.0, 1e-12);
        TEST_NEAR(Physics::traitsOf(Physics::ParticleProperty::Momentum_Transverse).extract(p),
                  std::sqrt(5.0), 1e-12);

        bool threw = false;
        try {
            (void)Physics::traitsOf(Physics::ParticleProperty::EventIndex);
        } catch (const std::logic_error&) {
            threw = true;
        }
        TEST_TRUE(threw);
        TEST_PASS("traitsOf extracts correctly and rejects branch-only EventIndex");
    }

    // ── Physics::Particles ───────────────────────────────────────────────────
    {
        TEST_NEAR(Physics::particleMass(3122), 1.115683, 1e-9);   // Lambda
        TEST_NEAR(Physics::particleMass(2212), 0.938272, 1e-9);   // proton
        TEST_EQ(std::string(Physics::particle(-211).name), std::string("pi+")); // antiparticle → same entry
        TEST_EQ(Physics::particle(211).charge3, 3);

        bool threw = false;
        try {
            (void)Physics::particle(999999);
        } catch (const std::runtime_error&) {
            threw = true;
        }
        TEST_TRUE(threw);
        TEST_PASS("PDG table lookups and antiparticle resolution");
    }

    // ── Physics::Kinematics edges ────────────────────────────────────────────
    {
        // Spacelike (m² < 0) input must clamp to 0, not NaN.
        TEST_EQ(Physics::invariantMass(1.0, 2.0, 0.0, 0.0), 0.0);
        // Δφ wraps into (-π, π].
        TEST_NEAR(Physics::deltaPhi(3.0, -3.0), 6.0 - 2.0 * M_PI, 1e-12);
        TEST_PASS("kinematics edge cases (spacelike mass, deltaPhi wrap)");
    }

    // ── Utility::Toml validators ─────────────────────────────────────────────
    {
        TEST_EQ(Utility::Toml::requirePositive(static_cast<std::int64_t>(5), "k"), 5);
        TEST_EQ(Utility::Toml::requireNonNegative(static_cast<std::int64_t>(0), "k"), 0);
        bool threw = false;
        try { Utility::Toml::requirePositive(static_cast<std::int64_t>(0), "k"); }
        catch (const std::runtime_error&) { threw = true; }
        TEST_TRUE(threw);
        threw = false;
        try { Utility::Toml::requireNonNegative(static_cast<std::int64_t>(-1), "k"); }
        catch (const std::runtime_error&) { threw = true; }
        TEST_TRUE(threw);
        TEST_PASS("Toml validators accept valid and reject invalid numerics");
    }

    // ── Utility::Paths ───────────────────────────────────────────────────────
    {
        // Absolute and CWD-existing paths pass through unchanged.
        TEST_EQ(Utility::Paths::resolveProjectPath("/tmp"), std::string("/tmp"));
        TEST_EQ(Utility::Paths::resolveProjectPath("tests"), std::string("tests"));
        // Repo-relative paths resolve to something that exists (run from repo
        // root the path is returned as-is; from elsewhere it is anchored).
        const std::string limits = Utility::Paths::resolveProjectPath("configs/Lambda_Limits.toml");
        TEST_TRUE(std::filesystem::exists(limits));
        TEST_PASS("project-root path anchoring");
    }

    // ── Config numeric rejection ─────────────────────────────────────────────
    {
        TEST_TRUE(readThrows("[events]\nevent_count = -5\n", "neg_events.toml"));
        TEST_TRUE(readThrows("[record]\nbin_count = 0\n", "zero_bins.toml"));
        TEST_TRUE(readThrows("[record]\nhist_scaling = -1.0\n", "neg_scale.toml"));
        TEST_TRUE(readThrows("[record]\nwriter_queue_capacity = -1\n", "neg_queue.toml"));
        TEST_FALSE(readThrows("[events]\nevent_count = 0\n", "zero_events.toml")); // 0 = all events, legal
        TEST_PASS("config rejects negative/zero values that previously wrapped");
    }

    // ── Utility::Sha256 — FIPS 180-4 test vectors ────────────────────────────
    {
        TEST_EQ(Utility::sha256Hex(""),
                std::string("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"));
        TEST_EQ(Utility::sha256Hex("abc"),
                std::string("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
        TEST_EQ(Utility::sha256Hex("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"),
                std::string("248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"));
        // 1,000,000 × 'a' — exercises multi-block streaming.
        Utility::Sha256 h;
        const std::string chunk(1000, 'a');
        for (int i = 0; i < 1000; ++i) h.update(chunk.data(), chunk.size());
        TEST_EQ(h.hexDigest(),
                std::string("cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"));
        // File digest: must match the in-memory digest of the same bytes.
        const std::string p = writeTempConfig("sha_probe.bin", "high-energy\n");
        TEST_EQ(Utility::sha256File(p), Utility::sha256Hex("high-energy\n"));
        TEST_EQ(Utility::sha256File("/nonexistent_xyz"), std::string(""));
        TEST_PASS("Sha256 matches FIPS 180-4 vectors, streaming and file modes");
    }

    // ── Monitor::writeTextFile failure path ──────────────────────────────────
    {
        // Unwritable path: must warn on stderr and return, never throw.
        Monitor::writeTextFile("/nonexistent_dir_xyz/out.log", "text");
        TEST_PASS("writeTextFile survives unwritable path without throwing");
    }

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
