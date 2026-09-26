// Core::Signals — the cooperative stop the run loop polls between chunks (P2-S02, D-Q2).

#include <csignal>

#include "Core.hh"
#include "check.hh"

int main() {
    Core::Signals::resetStopFlag();
    CHECK(!Core::Signals::stopRequested());

    Core::Signals::installGracefulStop();
    CHECK(!Core::Signals::stopRequested());

    // The first signal asks for a stop; the process keeps running, which is the whole point.
    ::raise(SIGINT);
    CHECK(Core::Signals::stopRequested());

    // The flag is sticky: a run must not "un-stop" itself between chunks.
    Core::Signals::resetStopFlag();
    CHECK(!Core::Signals::stopRequested());
    Core::Signals::requestStop();
    CHECK(Core::Signals::stopRequested());

    // SIGTERM (what the supervisor sends) behaves the same way.
    Core::Signals::resetStopFlag();
    Core::Signals::installGracefulStop();
    ::raise(SIGTERM);
    CHECK(Core::Signals::stopRequested());

    // Exit codes are part of the contract with hep (06 §3.3).
    CHECK_EQ(Core::code(Core::Exit::Stopped), 6);
    CHECK_EQ(Core::code(Core::Exit::Config), 1);
    CHECK_EQ(std::string(Core::name(Core::Exit::Stopped)), std::string("partial"));

    const Core::Error error{Core::Exit::Init, "vanishing cross section", "check Photon:ProcessType"};
    CHECK_EQ(Core::code(error.exit()), 3);
    CHECK(std::string(error.what()).find("hint: check Photon:ProcessType") != std::string::npos);

    return check::finish("core_signals");
}
