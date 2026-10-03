// utils/App_PythiaCheck.cc — Pythia reads a card and says which lines it rejects (V59).
// requires: pythia8
//
//     App_PythiaCheck.exe CARD
//
// The runner's card check for the pythia folder ([checks] card): every line is given to Pythia's own
// reader, in order, so a setting Pythia does not know, a value of the wrong kind, or a particle the
// table lacks (until an `id:new` line earlier in the card makes it) is found before anything runs,
// with no hand-written list of keys. Nothing is initialised and no event is made.
//
// Prints one JSON line per rejected line: {"line": N, "text": "..."}. Exit codes: 0 every line read,
// 1 a line rejected, 2 usage, 4 the card cannot be read.

#include "Pythia8/Pythia.h"

#include <cstdio>
#include <fstream>
#include <iostream>
#include <string>

namespace {

    std::string quote(const std::string& text) {
        std::string out = "\"";
        for (char c : text) {
            if (c == '"' || c == '\\') out += '\\';
            if (static_cast<unsigned char>(c) >= 0x20) out += c;
        }
        return out + "\"";
    }

    // Pythia reads a line only when it starts with a letter or a digit; the rest are comments.
    bool isSetting(const std::string& line) {
        const auto at = line.find_first_not_of(" \t");
        return at != std::string::npos && std::isalnum(static_cast<unsigned char>(line[at]));
    }

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::fputs("usage: App_PythiaCheck.exe CARD\n", stderr);
        return 2;
    }
    std::ifstream card(argv[1]);
    if (!card) {
        std::fprintf(stderr, "App_PythiaCheck: cannot read %s\n", argv[1]);
        return 4;
    }
    Pythia8::Pythia pythia("", false);           // the xmldoc from PYTHIA8DATA or the install; no banner
    pythia.readString("Print:quiet = on");
    int rejected = 0, number = 0;
    for (std::string line; std::getline(card, line);) {
        ++number;
        if (!isSetting(line)) continue;
        if (!pythia.readString(line, false)) {
            std::cout << "{\"line\": " << number << ", \"text\": " << quote(line) << "}\n";
            ++rejected;
        }
    }
    return rejected ? 1 : 0;
}
