#pragma once

// ── Status/Writer.hh ─────────────────────────────────────────────────────────
// JSON lines on fd 3, or plain lines on stderr when nobody passed fd 3 (06 §3).
//
// Three properties the event loop depends on:
//
//   * **It never formats JSON.** The loop updates atomic counters; the heartbeat thread turns them into
//     a message at most `interval` apart (06 §3.1). At 20 threads and 10⁵ events/s, formatting per
//     event would cost more than the analysis.
//   * **A blocked reader never blocks the run.** fd 3 is made non-blocking, and a short write is
//     dropped rather than retried: status is disposable, events are not.
//   * **It is safe from any thread.** One mutex around the write, and the counters are atomic.
//
// The JSON is written by hand. The alternative is a dependency for nine message shapes, none of which
// contains anything harder to escape than a tool's warning text.

#include <atomic>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

#include <fcntl.h>
#include <unistd.h>

#include "Core/Clock.hh"
#include "Status/Plain.hh"
#include "Status/Types.hh"

namespace Status {

    // Minimal JSON string escaping: quotes, backslashes and control characters.
    inline std::string escape(const std::string& text) {
        std::string out;
        out.reserve(text.size() + 8);
        for (const char character : text) {
            switch (character) {
                case '"': out += "\\\""; break;
                case '\\': out += "\\\\"; break;
                case '\n': out += "\\n"; break;
                case '\r': out += "\\r"; break;
                case '\t': out += "\\t"; break;
                default:
                    if (static_cast<unsigned char>(character) < 0x20) {
                        char buffer[8];
                        std::snprintf(buffer, sizeof buffer, "\\u%04x", character);
                        out += buffer;
                    } else {
                        out += character;
                    }
            }
        }
        return out;
    }

    inline std::string number(double value) {
        char buffer[32];
        std::snprintf(buffer, sizeof buffer, "%.10g", value);
        return buffer;
    }

    template <typename T>
    std::string jsonList(const std::vector<T>& values) {
        std::string out = "[";
        for (std::size_t index = 0; index < values.size(); ++index) {
            if (index) out += ",";
            if constexpr (std::is_floating_point_v<T>) {
                out += number(values[index]);
            } else if constexpr (std::is_integral_v<T>) {
                out += std::to_string(values[index]);
            } else {
                out += "\"" + escape(values[index]) + "\"";
            }
        }
        return out + "]";
    }

    class Writer {
      public:
        // `fd` is the descriptor to write JSON lines to; anything not open falls back to stderr.
        explicit Writer(int fd = 3, double interval = 0.5) : interval_(interval) {
            if (fd >= 0 && ::fcntl(fd, F_GETFD) != -1) {
                fd_ = fd;
                // Status must never hold up generation: a full pipe drops a message instead of blocking.
                const int flags = ::fcntl(fd_, F_GETFL);
                if (flags != -1) ::fcntl(fd_, F_SETFL, flags | O_NONBLOCK);
            }
            started_ = Core::tick();
        }

        bool structured() const { return fd_ >= 0; }
        long long dropped() const { return dropped_.load(std::memory_order_relaxed); }

        void phase(const std::string& phase, const std::string& detail = {}) {
            emit(Kind::Phase, "\"phase\":\"" + escape(phase) + "\"" +
                                  (detail.empty() ? "" : ",\"detail\":\"" + escape(detail) + "\""),
                 phase + (detail.empty() ? "" : ": " + detail));
        }

        void init(const std::vector<int>& beam_ids, const std::vector<double>& beam_energies,
                  double sqrt_s, int threads, const std::string& mode,
                  const std::vector<std::string>& sinks) {
            emit(Kind::Init,
                 "\"beam_ids\":" + jsonList(beam_ids) + ",\"beam_energies\":" + jsonList(beam_energies) +
                     ",\"sqrt_s\":" + number(sqrt_s) + ",\"threads\":" + std::to_string(threads) +
                     ",\"mode\":\"" + escape(mode) + "\",\"sinks\":" + jsonList(sinks),
                 "sqrt(s) = " + number(sqrt_s) + " GeV, " + std::to_string(threads) + " threads, " + mode);
        }

        // Called from the event loop: cheap, and dropped when it arrives too soon after the last one.
        void progress(const Progress& progress, bool force = false) {
            if (!force && Core::since(last_progress_) < interval_) return;
            last_progress_ = Core::tick();
            emit(Kind::Progress,
                 "\"done\":" + std::to_string(progress.done) + ",\"total\":" +
                     std::to_string(progress.total) + ",\"rate\":" + number(progress.rate) +
                     ",\"workers\":" + jsonList(progress.workers),
                 progressLine(progress));
        }

        void xsec(double value_pb, double error_pb, bool final_value) {
            emit(Kind::Xsec,
                 "\"value_pb\":" + number(value_pb) + ",\"err_pb\":" + number(error_pb) +
                     ",\"final\":" + (final_value ? "true" : "false"),
                 "sigma = " + number(value_pb) + " +- " + number(error_pb) + " pb");
        }

        void log(Level level, const std::string& source, const std::string& message) {
            emit(Kind::Log,
                 "\"level\":\"" + std::string(name(level)) + "\",\"source\":\"" + escape(source) +
                     "\",\"msg\":\"" + escape(message) + "\"",
                 std::string(name(level)) + " [" + source + "] " + message);
        }

        void checkpoint(long long done, const std::vector<std::string>& outputs) {
            emit(Kind::Checkpoint,
                 "\"done\":" + std::to_string(done) + ",\"outputs\":" + jsonList(outputs),
                 "checkpoint at " + std::to_string(done) + " events");
        }

        void summary(const std::string& fields, const std::string& plain) {
            emit(Kind::Summary, fields, plain);
        }

        void heartbeat() { emit(Kind::Heartbeat, "", ""); }

        // One raw message, for kinds a caller composes itself (`event` with --list).
        void emit(Kind kind, const std::string& fields, const std::string& plain) {
            const std::lock_guard<std::mutex> lock(mutex_);
            if (fd_ >= 0) {
                std::string line = "{\"t\":" + number(Core::now()) + ",\"k\":\"" + name(kind) + "\"";
                if (!fields.empty()) line += "," + fields;
                line += "}\n";
                write(line);
            } else if (!plain.empty() && kind != Kind::Heartbeat) {
                std::fprintf(stderr, "%s\n", plain.c_str());
            }
            last_message_ = Core::tick();
        }

        double sinceLastMessage() const { return Core::since(last_message_); }

      private:
        void write(const std::string& line) {
            const ssize_t written = ::write(fd_, line.data(), line.size());
            if (written < 0 || static_cast<std::size_t>(written) != line.size())
                dropped_.fetch_add(1, std::memory_order_relaxed);
        }

        int fd_ = -1;
        double interval_;
        std::mutex mutex_;
        std::atomic<long long> dropped_{0};
        Core::Steady::time_point started_{};
        Core::Steady::time_point last_progress_{};
        Core::Steady::time_point last_message_{Core::tick()};
    };

}  // namespace Status
