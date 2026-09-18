#pragma once

// ── Core/Errors.hh ───────────────────────────────────────────────────────────
// Exit codes and the one exception type that carries them (06 §3.3).
//
// Every failure `hep-run` can have maps to a code that `hep` knows how to show, so the terminal never
// has to guess from a message. Throw `Core::Error{Core::Exit::Init, "..."}` and let `main` turn it into
// an exit code and a status message.

#include <exception>
#include <string>
#include <utility>

namespace Core {

    // The codes of 06 §3.3. Values are part of the contract with `hep`, so they never shift.
    enum class Exit : int {
        Ok = 0,
        Config = 1,        // spec or card error: a rejected setting, a missing file
        Usage = 2,
        Init = 3,          // the generator failed to initialise (vanishing cross section, bad beams)
        Source = 4,        // input I/O: a FIFO closed early, an unparsable event
        Sink = 5,          // output: a failed finalize or write
        Stopped = 6,       // a signal stopped the run; partial outputs were finalised
        Stalled = 7,       // set by the supervisor, never by us
        Internal = 70,     // a bug: an invariant we hold ourselves to
    };

    inline int code(Exit exit) { return static_cast<int>(exit); }

    inline const char* name(Exit exit) {
        switch (exit) {
            case Exit::Ok: return "ok";
            case Exit::Config: return "config";
            case Exit::Usage: return "usage";
            case Exit::Init: return "init";
            case Exit::Source: return "input";
            case Exit::Sink: return "output";
            case Exit::Stopped: return "partial";
            case Exit::Stalled: return "stall";
            case Exit::Internal: return "bug";
        }
        return "unknown";
    }

    // A failure with its exit code and, where it helps, what to do about it.
    class Error : public std::exception {
      public:
        Error(Exit exit, std::string message, std::string hint = {})
            : exit_(exit), message_(std::move(message)), hint_(std::move(hint)) {
            what_ = message_;
            if (!hint_.empty()) what_ += "\n  hint: " + hint_;
        }

        const char* what() const noexcept override { return what_.c_str(); }
        Exit exit() const noexcept { return exit_; }
        const std::string& message() const noexcept { return message_; }
        const std::string& hint() const noexcept { return hint_; }

      private:
        Exit exit_;
        std::string message_;
        std::string hint_;
        std::string what_;
    };

}  // namespace Core
