#pragma once
// utils/Status.hh — the standard status protocol (docs/rework_v2/05_Tools.md §3.1).
//
// A tool writes JSON lines to the file descriptor named in $HEP_STATUS_FD:
//
//     {"t": 1790000001.500000, "k": "progress", "done": 12000, "total": 1000000, "rate": 8123.4}
//
// With the variable unset it writes plain lines to stderr instead, so a tool run by hand is still
// readable. Writes never block: the descriptor is non-blocking and a line that does not fit is
// dropped and counted, so a slow reader can never slow a generator down. A heartbeat thread sends
// `heartbeat` when nothing else was sent for half a second, which is what the runner's stall
// detection watches for.
//
// Kinds: phase, progress, xsec, log, summary, heartbeat. A reader keeps and ignores a kind it does
// not know, so the set can grow.

#ifdef Status
#error "Status is a macro here (X11's Xlib.h defines it): include Status.hh before any X11 header"
#endif

#include <atomic>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <mutex>
#include <string>
#include <thread>
#include <unistd.h>

namespace Status {

    // A JSON string literal, escaped.
    inline std::string quote(const std::string& text) {
        std::string out = "\"";
        for (char c : text) {
            switch (c) {
                case '"':  out += "\\\""; break;
                case '\\': out += "\\\\"; break;
                case '\n': out += "\\n";  break;
                case '\t': out += "\\t";  break;
                case '\r': out += "\\r";  break;
                default:
                    if (static_cast<unsigned char>(c) < 0x20) {
                        char buffer[8];
                        std::snprintf(buffer, sizeof buffer, "\\u%04x", c);
                        out += buffer;
                    } else {
                        out += c;
                    }
            }
        }
        return out + "\"";
    }

    inline std::string number(double value) {
        char buffer[32];
        std::snprintf(buffer, sizeof buffer, "%.10g", value);
        return buffer;
    }

    class Reporter {
      public:
        // Reads $HEP_STATUS_FD; `beat` = heartbeat period in milliseconds (0 = no heartbeat thread).
        explicit Reporter(int beat = 500) {
            if (const char* value = std::getenv("HEP_STATUS_FD")) {
                fd_ = std::atoi(value);
                if (fd_ >= 0) fcntl(fd_, F_SETFL, fcntl(fd_, F_GETFL) | O_NONBLOCK);
            }
            if (beat > 0 && fd_ >= 0) beat_ = std::thread([this, beat] { beatLoop(beat); });
        }
        ~Reporter() {
            {
                std::lock_guard<std::mutex> lock(mutex_);
                stopping_ = true;
            }
            wake_.notify_all();
            if (beat_.joinable()) beat_.join();
        }
        Reporter(const Reporter&) = delete;
        Reporter& operator=(const Reporter&) = delete;

        bool structured() const { return fd_ >= 0; }
        long dropped() const { return dropped_.load(); }

        void phase(const std::string& name, const std::string& detail = "") {
            send("phase", "\"phase\": " + quote(name) + (detail.empty() ? "" : ", \"detail\": " + quote(detail)),
                 "[" + name + "]" + (detail.empty() ? "" : " " + detail));
        }

        // Rate-limited to 4 per second unless `force` (the first and last call should force).
        void progress(long done, long total, double rate, bool force = false) {
            const double now = seconds();
            if (!force && now - lastProgress_ < 0.25) return;
            lastProgress_ = now;
            send("progress",
                 "\"done\": " + std::to_string(done) + ", \"total\": " + std::to_string(total) +
                     ", \"rate\": " + number(rate),
                 std::to_string(done) + "/" + std::to_string(total) + " (" + number(rate) + "/s)");
        }

        void xsec(double valuePb, double errorPb, bool final) {
            send("xsec",
                 "\"value_pb\": " + number(valuePb) + ", \"err_pb\": " + number(errorPb) +
                     ", \"final\": " + (final ? "true" : "false"),
                 "sigma = " + number(valuePb) + " +- " + number(errorPb) + " pb" + (final ? " (final)" : ""));
        }

        void log(const std::string& level, const std::string& message) {
            send("log", "\"level\": " + quote(level) + ", \"msg\": " + quote(message), level + ": " + message);
        }

        // `fields` is the inside of a JSON object: "\"written\": 5000, \"outputs\": [\"a.hepmc\"]".
        void summary(const std::string& fields) { send("summary", fields, "summary: " + fields); }

      private:
        static double seconds() {
            using namespace std::chrono;
            return duration<double>(system_clock::now().time_since_epoch()).count();
        }

        void send(const char* kind, const std::string& fields, const std::string& plain) {
            if (fd_ < 0) {
                std::fprintf(stderr, "%s\n", plain.c_str());
                return;
            }
            char stamp[32];
            std::snprintf(stamp, sizeof stamp, "%.6f", seconds());
            const std::string line = std::string("{\"t\": ") + stamp + ", \"k\": \"" + kind + "\"" +
                                     (fields.empty() ? "" : ", " + fields) + "}\n";
            std::lock_guard<std::mutex> lock(mutex_);
            // A line up to PIPE_BUF bytes is written whole or not at all; a longer one is cut.
            const ssize_t written = ::write(fd_, line.data(), line.size());
            if (written != static_cast<ssize_t>(line.size())) ++dropped_;
            lastSend_ = seconds();
        }

        void beatLoop(int periodMs) {
            std::unique_lock<std::mutex> lock(mutex_);
            while (!stopping_) {
                wake_.wait_for(lock, std::chrono::milliseconds(periodMs));
                if (stopping_) break;
                if (seconds() - lastSend_ >= periodMs / 1000.0) {
                    lock.unlock();
                    send("heartbeat", "", "");
                    lock.lock();
                }
            }
        }

        int fd_ = -1;
        std::atomic<long> dropped_{0};
        double lastProgress_ = 0.0;
        double lastSend_ = 0.0;
        std::mutex mutex_;
        std::condition_variable wake_;
        bool stopping_ = false;
        std::thread beat_;
    };

}  // namespace Status
