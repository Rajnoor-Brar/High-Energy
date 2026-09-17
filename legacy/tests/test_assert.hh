#pragma once

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

// ── Lightweight test-assertion macros ────────────────────────────────────────
// No external dependencies; every test binary includes this header directly.
// On failure the macro prints FILE:LINE, the failed expression, and exits(1).
// On success nothing is printed — call TEST_PASS to mark a named checkpoint.

#define TEST_EQ(a, b) do { \
    if (!((a) == (b))) { \
        std::cerr << "FAIL [" __FILE__ ":" << __LINE__ << "]  " \
                  << #a " == " #b "\n" \
                  << "  lhs = " << (a) << "\n  rhs = " << (b) << '\n'; \
        std::exit(1); \
    } \
} while (0)

#define TEST_NE(a, b) do { \
    if ((a) == (b)) { \
        std::cerr << "FAIL [" __FILE__ ":" << __LINE__ << "]  " \
                  << #a " != " #b "\n" \
                  << "  value = " << (a) << '\n'; \
        std::exit(1); \
    } \
} while (0)

#define TEST_TRUE(expr) do { \
    if (!(expr)) { \
        std::cerr << "FAIL [" __FILE__ ":" << __LINE__ << "]  " #expr "\n"; \
        std::exit(1); \
    } \
} while (0)

#define TEST_FALSE(expr) do { \
    if (!!(expr)) { \
        std::cerr << "FAIL [" __FILE__ ":" << __LINE__ << "]  !" #expr "\n"; \
        std::exit(1); \
    } \
} while (0)

// |a - b| <= tol
#define TEST_NEAR(a, b, tol) do { \
    const auto _diff_ = std::abs(static_cast<double>(a) - static_cast<double>(b)); \
    if (!(_diff_ <= static_cast<double>(tol))) { \
        std::cerr << "FAIL [" __FILE__ ":" << __LINE__ << "]  |" #a " - " #b "| <= " #tol "\n" \
                  << "  lhs  = " << (a) << "\n  rhs  = " << (b) \
                  << "\n  diff = " << _diff_ << "\n  tol  = " << (tol) << '\n'; \
        std::exit(1); \
    } \
} while (0)

// a < b
#define TEST_LT(a, b) do { \
    if (!((a) < (b))) { \
        std::cerr << "FAIL [" __FILE__ ":" << __LINE__ << "]  " \
                  << #a " < " #b "\n" \
                  << "  lhs = " << (a) << "\n  rhs = " << (b) << '\n'; \
        std::exit(1); \
    } \
} while (0)

#define TEST_PASS(name) std::cout << "  PASS  " << (name) << '\n'
