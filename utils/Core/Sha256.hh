#pragma once

// ── Core/Sha256.hh ───────────────────────────────────────────────────────────
// SHA-256 (FIPS 180-4) in process. Ported from `legacy/utils/Utility/Sha256.hh`, which replaced a
// shell-out to `sha256sum` — that was both a shell-injection hazard for odd paths and a dependency on
// the host's tools. Identity hashes, provenance and store verification all use this.
//
//   Core::Sha256 hash;  hash.update(data, size);  std::string hex = hash.hexDigest();
//   Core::sha256File(path)    → hex digest, or "" when the file cannot be read
//
// Added here: `sha256_file` refuses anything that is not a regular file, so hashing a directory or a
// FIFO fails visibly instead of blocking or returning the digest of nothing.

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <string>
#include <sys/stat.h>

namespace Core {


    class Sha256 {
      public:
        Sha256() { reset(); }

        void reset() {
            state_ = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                      0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
            bufferLen_ = 0;
            totalBits_ = 0;
            digest_.clear();
        }

        // Updating after the digest has been taken would silently continue a finished hash.
        void update(const void* data, std::size_t len) {
            if (!digest_.empty() && data != nullptr && len > 0) digest_.clear(), reset();
            const auto* bytes = static_cast<const unsigned char*>(data);
            totalBits_ += static_cast<std::uint64_t>(len) * 8;
            while (len > 0) {
                const std::size_t take = std::min(len, kBlockSize - bufferLen_);
                std::memcpy(buffer_.data() + bufferLen_, bytes, take);
                bufferLen_ += take;
                bytes      += take;
                len        -= take;
                if (bufferLen_ == kBlockSize) {
                    processBlock(buffer_.data());
                    bufferLen_ = 0;
                }
            }
        }

        // The lowercase hex digest. Finalising is idempotent: calling this twice returns the same
        // string rather than hashing the padding again. The legacy version documented "reset() before
        // reuse" instead, which is the kind of rule that holds until a test macro evaluates its
        // argument twice (it did).
        std::string hexDigest() {
            if (!digest_.empty()) return digest_;
            // Padding: 0x80, zeros, then the 64-bit big-endian bit length.
            const std::uint64_t bits = totalBits_;
            unsigned char pad = 0x80;
            update(&pad, 1);
            const unsigned char zero = 0x00;
            while (bufferLen_ != kBlockSize - 8) update(&zero, 1);
            // update() also advances totalBits_, but `bits` was captured first;
            // write the captured length directly into the final block.
            for (int i = 7; i >= 0; --i) {
                buffer_[bufferLen_++] =
                    static_cast<unsigned char>((bits >> (i * 8)) & 0xffu);
            }
            processBlock(buffer_.data());
            bufferLen_ = 0;

            static const char* kHex = "0123456789abcdef";
            std::string out;
            out.reserve(64);
            for (const std::uint32_t word : state_) {
                for (int shift = 28; shift >= 0; shift -= 4)
                    out.push_back(kHex[(word >> shift) & 0xfu]);
            }
            digest_ = out;
            return digest_;
        }

      private:
        static constexpr std::size_t kBlockSize = 64;

        static std::uint32_t rotr(std::uint32_t x, int n) {
            return (x >> n) | (x << (32 - n));
        }

        void processBlock(const unsigned char* block) {
            static constexpr std::array<std::uint32_t, 64> K = {{
                0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u,
                0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
                0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
                0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
                0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
                0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
                0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
                0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
                0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
                0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
                0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u,
                0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
                0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u,
                0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
                0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
                0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u,
            }};

            std::array<std::uint32_t, 64> w{};
            for (int i = 0; i < 16; ++i) {
                w[i] = (static_cast<std::uint32_t>(block[i * 4])     << 24)
                     | (static_cast<std::uint32_t>(block[i * 4 + 1]) << 16)
                     | (static_cast<std::uint32_t>(block[i * 4 + 2]) <<  8)
                     |  static_cast<std::uint32_t>(block[i * 4 + 3]);
            }
            for (int i = 16; i < 64; ++i) {
                const std::uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
                const std::uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2],  19) ^ (w[i - 2] >> 10);
                w[i] = w[i - 16] + s0 + w[i - 7] + s1;
            }

            std::uint32_t a = state_[0], b = state_[1], c = state_[2], d = state_[3];
            std::uint32_t e = state_[4], f = state_[5], g = state_[6], h = state_[7];

            for (int i = 0; i < 64; ++i) {
                const std::uint32_t S1    = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
                const std::uint32_t ch    = (e & f) ^ (~e & g);
                const std::uint32_t temp1 = h + S1 + ch + K[i] + w[i];
                const std::uint32_t S0    = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
                const std::uint32_t maj   = (a & b) ^ (a & c) ^ (b & c);
                const std::uint32_t temp2 = S0 + maj;
                h = g; g = f; f = e; e = d + temp1;
                d = c; c = b; b = a; a = temp1 + temp2;
            }

            state_[0] += a; state_[1] += b; state_[2] += c; state_[3] += d;
            state_[4] += e; state_[5] += f; state_[6] += g; state_[7] += h;
        }

        std::array<std::uint32_t, 8>           state_{};
        std::array<unsigned char, kBlockSize>  buffer_{};
        std::size_t                            bufferLen_ = 0;
        std::uint64_t                          totalBits_ = 0;
        std::string                            digest_;        // set once finalised
    };

    // sha256Hex — digest of an in-memory buffer.
    inline std::string sha256Hex(const std::string& data) {
        Sha256 h;
        h.update(data.data(), data.size());
        return h.hexDigest();
    }

    // A regular file only: a directory or a FIFO would otherwise hash as "" or block forever.
    inline bool isRegularFile(const std::string& path) {
        struct stat info {};
        return ::stat(path.c_str(), &info) == 0 && S_ISREG(info.st_mode);
    }

    // sha256File — streaming digest of a file; "" if it is not a readable regular file.
    inline std::string sha256File(const std::string& path) {
        if (!isRegularFile(path)) return {};
        std::ifstream in(path, std::ios::binary);
        if (!in) return {};
        Sha256 h;
        char chunk[64 * 1024];
        while (in.read(chunk, sizeof(chunk)) || in.gcount() > 0)
            h.update(chunk, static_cast<std::size_t>(in.gcount()));
        return h.hexDigest();
    }

}  // namespace Core
