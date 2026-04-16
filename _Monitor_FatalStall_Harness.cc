#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <thread>

#include "Config.hh"
#include "Monitor.hh"

int main() {
    Config::Root root;
    root.rootDirectory = "output/Monitor_FatalStall_Harness/";
    root.logDirectory = "output/Monitor_FatalStall_Harness/logs/";
    root.logName = "output/Monitor_FatalStall_Harness/logs/harness.log";
    root.runStatName = "output/Monitor_FatalStall_Harness/logs/harness_runstat.log";
    root.threadStatDirectory = "output/Monitor_FatalStall_Harness/logs/threads/";
    root.fileTitle = "Monitor_FatalStall_Harness";

    Config::Log logging;
    logging.serial = 99;
    logging.nEvents = 10;
    logging.heartbeat_interval = std::chrono::microseconds(100000);
    logging.terminal_refresh_interval = std::chrono::seconds(1);
    logging.program_stall_threshold = std::chrono::seconds(1);
    logging.start = std::chrono::system_clock::now();

    std::mutex mutex;
    std::condition_variable cv;
    std::size_t fatalCallbackCount = 0;

    {
        Monitor::AsyncLogger logger;
        logger.setFatalStallHandler([&](const Monitor::RunSnapshot&) {
            {
                std::lock_guard<std::mutex> lock(mutex);
                ++fatalCallbackCount;
            }
            cv.notify_one();
        });

        logger.start(root, logging);
        logger.publish(logging, Monitor::RunPhase::Starting, 0, Monitor::DontRenderStatus, Monitor::DontRenderBar, Monitor::WriteRunStat);
        logger.publish(logging, Monitor::RunPhase::Analysis, 1, Monitor::DontRenderStatus, Monitor::DontRenderBar, Monitor::WriteRunStat);

        {
            std::unique_lock<std::mutex> lock(mutex);
            const bool received = cv.wait_for(lock, std::chrono::seconds(7), [&] {
                return fatalCallbackCount == 1;
            });

            if (!received) {
                std::cerr << "fatal callback did not fire within expected time\n";
                return EXIT_FAILURE;
            }
        }

        std::this_thread::sleep_for(std::chrono::seconds(2));
        logger.stop();
    }

    if (fatalCallbackCount != 1) {
        std::cerr << "fatal callback fired " << fatalCallbackCount << " times instead of once\n";
        return EXIT_FAILURE;
    }

    {
        Monitor::AsyncLogger logger;
        logger.setFatalStallHandler([&](const Monitor::RunSnapshot&) {
            std::lock_guard<std::mutex> lock(mutex);
            ++fatalCallbackCount;
        });

        logging.start = std::chrono::system_clock::now();
        logger.start(root, logging);
        logger.publish(logging, Monitor::RunPhase::Starting, 0, Monitor::DontRenderStatus, Monitor::DontRenderBar, Monitor::WriteRunStat);
        std::this_thread::sleep_for(std::chrono::seconds(6));
        logger.stop();
    }

    {
        Monitor::AsyncLogger logger;
        logger.setFatalStallHandler([&](const Monitor::RunSnapshot&) {
            std::lock_guard<std::mutex> lock(mutex);
            ++fatalCallbackCount;
        });

        logging.start = std::chrono::system_clock::now();
        logger.start(root, logging);
        logger.publish(logging, Monitor::RunPhase::Finished, logging.nEvents, Monitor::DontRenderStatus, Monitor::DontRenderBar, Monitor::WriteRunStat);
        std::this_thread::sleep_for(std::chrono::seconds(6));
        logger.stop();
    }

    if (fatalCallbackCount != 1) {
        std::cerr << "starting/finished phases incorrectly triggered fatal detection\n";
        return EXIT_FAILURE;
    }

    std::cout << "Monitor fatal stall harness passed\n";
    return EXIT_SUCCESS;
}
