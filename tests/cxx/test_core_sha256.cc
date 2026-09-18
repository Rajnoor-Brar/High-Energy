// Core::Sha256 against the FIPS 180-4 vectors (kept from `legacy/tests/test_utils_hardening.cc`), plus
// the file behaviour the identity hash and store verification rely on.

#include <cstdio>
#include <fstream>
#include <string>

#include "Core.hh"
#include "check.hh"

int main() {
    // FIPS 180-4 examples and the classic long-message vector.
    CHECK_EQ(Core::sha256Hex(""),
             std::string("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"));
    CHECK_EQ(Core::sha256Hex("abc"),
             std::string("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
    CHECK_EQ(Core::sha256Hex("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"),
             std::string("248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"));

    // A message that crosses the 64-byte block boundary and the padding edge (55, 56, 64 bytes).
    CHECK_EQ(Core::sha256Hex(std::string(55, 'a')),
             std::string("9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318"));
    CHECK_EQ(Core::sha256Hex(std::string(56, 'a')),
             std::string("b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a"));
    CHECK_EQ(Core::sha256Hex(std::string(64, 'a')),
             std::string("ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb"));
    CHECK_EQ(Core::sha256Hex(std::string(1000000, 'a')),
             std::string("cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"));

    // Incremental updates must match a single one, since cards are hashed in chunks.
    Core::Sha256 incremental;
    incremental.update("abc", 3);
    incremental.update("def", 3);
    const std::string chunked = incremental.hexDigest();
    CHECK_EQ(chunked, Core::sha256Hex("abcdef"));
    // Finalising is idempotent: the digest does not change when it is read twice.
    CHECK_EQ(incremental.hexDigest(), chunked);
    CHECK_EQ(incremental.hexDigest(), chunked);
    // After a reset the same object starts again.
    incremental.reset();
    incremental.update("abc", 3);
    CHECK_EQ(incremental.hexDigest(), Core::sha256Hex("abc"));

    // Files: a regular file hashes like its bytes; anything else is refused rather than guessed.
    const std::string path = "/tmp/hekit_sha256_test.txt";
    {
        std::ofstream out(path, std::ios::binary);
        out << "abc";
    }
    CHECK_EQ(Core::sha256File(path), Core::sha256Hex("abc"));
    CHECK_EQ(Core::sha256File("/tmp"), std::string());               // a directory
    CHECK_EQ(Core::sha256File("/tmp/hekit_absent_file"), std::string());
    CHECK(Core::isRegularFile(path));
    CHECK(!Core::isRegularFile("/tmp"));
    std::remove(path.c_str());

    return check::finish("core_sha256");
}
