#pragma once

// A test harness small enough to read in one sitting (adapted from `legacy/tests/test_assert.hh`).
// No framework: these tests are executables that ctest runs, and a failure has to print what it
// expected and what it got, on the line where it happened.

#include <cstdio>
#include <iostream>
#include <sstream>
#include <string>

namespace check {

    inline int failures = 0;
    inline int checks = 0;

    inline void report(bool ok, const char* expression, const char* file, int line,
                       const std::string& detail = {}) {
        checks += 1;
        if (ok) return;
        failures += 1;
        std::fprintf(stderr, "FAIL %s:%d  %s%s%s\n", file, line, expression,
                     detail.empty() ? "" : "\n     ", detail.c_str());
    }

    template <typename A, typename B>
    std::string compare(const A& left, const B& right) {
        std::ostringstream out;
        out << "left = " << left << "  right = " << right;
        return out.str();
    }

    inline int finish(const char* name) {
        std::fprintf(stderr, "%s: %d checks, %d failed\n", name, checks, failures);
        return failures == 0 ? 0 : 1;
    }

}  // namespace check

#define CHECK(expression) ::check::report((expression), #expression, __FILE__, __LINE__)
#define CHECK_EQ(left, right)                                                                  \
    ::check::report((left) == (right), #left " == " #right, __FILE__, __LINE__,                \
                    ::check::compare((left), (right)))
#define CHECK_THROWS(expression, type)                                                         \
    do {                                                                                       \
        bool threw = false;                                                                    \
        try {                                                                                  \
            expression;                                                                        \
        } catch (const type&) {                                                                \
            threw = true;                                                                      \
        } catch (...) {                                                                        \
        }                                                                                      \
        ::check::report(threw, "throws " #type ": " #expression, __FILE__, __LINE__);           \
    } while (false)
