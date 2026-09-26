// tests/cxx/test_status.cc — utils/Status.hh: the JSON envelope, never blocking, the plain fallback.
// requires: none

#include "Status.hh"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <unistd.h>

static int failures = 0;
#define CHECK(cond)                                                                   \
    do {                                                                              \
        if (!(cond)) {                                                                \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);      \
            ++failures;                                                               \
        }                                                                             \
    } while (0)

static std::string drain(int fd) {
    std::string out;
    char buffer[65536];
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK);
    for (ssize_t n; (n = read(fd, buffer, sizeof buffer)) > 0;) out.append(buffer, n);
    return out;
}

int main() {
    // ── the envelope ──
    {
        int fds[2];
        CHECK(pipe(fds) == 0);
        setenv("HEP_STATUS_FD", std::to_string(fds[1]).c_str(), 1);
        {
            Status::Reporter status(0);
            CHECK(status.structured());
            status.phase("generating", "5000 events");
            status.progress(10, 100, 5.5, true);
            status.xsec(71422.16, 415.6, true);
            status.log("warn", "a \"quoted\"\nline");
            status.summary("\"written\": 10");
        }
        const std::string out = drain(fds[0]);
        CHECK(out.find("\"k\": \"phase\", \"phase\": \"generating\", \"detail\": \"5000 events\"}") != std::string::npos);
        CHECK(out.find("\"k\": \"progress\", \"done\": 10, \"total\": 100, \"rate\": 5.5}") != std::string::npos);
        CHECK(out.find("\"value_pb\": 71422.16, \"err_pb\": 415.6, \"final\": true") != std::string::npos);
        CHECK(out.find("\"msg\": \"a \\\"quoted\\\"\\nline\"") != std::string::npos);
        CHECK(out.find("\"k\": \"summary\", \"written\": 10}") != std::string::npos);
        int lines = 0;
        for (char c : out) lines += c == '\n';
        CHECK(lines == 5);
        CHECK(out.rfind("{\"t\": ", 0) == 0);
        close(fds[0]);
        close(fds[1]);
    }

    // ── a reader that never reads: writes drop, they never block ──
    {
        int fds[2];
        CHECK(pipe(fds) == 0);
        setenv("HEP_STATUS_FD", std::to_string(fds[1]).c_str(), 1);
        Status::Reporter status(0);
        for (int i = 0; i < 20000; ++i) status.log("info", std::string(200, 'x'));  // ~4 MB into a 64 kB pipe
        CHECK(status.dropped() > 0);
        close(fds[0]);
        close(fds[1]);
    }

    // ── the heartbeat, when nothing else is said ──
    {
        int fds[2];
        CHECK(pipe(fds) == 0);
        setenv("HEP_STATUS_FD", std::to_string(fds[1]).c_str(), 1);
        {
            Status::Reporter status(50);
            usleep(300000);
        }
        CHECK(drain(fds[0]).find("\"k\": \"heartbeat\"") != std::string::npos);
        close(fds[0]);
        close(fds[1]);
    }

    // ── no descriptor: plain lines on stderr ──
    {
        unsetenv("HEP_STATUS_FD");
        int fds[2];
        CHECK(pipe(fds) == 0);
        const int saved = dup(2);
        dup2(fds[1], 2);
        {
            Status::Reporter status;
            CHECK(!status.structured());
            status.progress(3, 9, 1.0, true);
        }
        std::fflush(stderr);
        dup2(saved, 2);
        close(fds[1]);
        const std::string out = drain(fds[0]);
        CHECK(out == "3/9 (1/s)\n");
        close(fds[0]);
    }

    CHECK(Status::quote("tab\there") == "\"tab\\there\"");
    if (failures) {
        std::fprintf(stderr, "test_status: %d failure(s)\n", failures);
        return 1;
    }
    std::puts("test_status: ok");
    return 0;
}
