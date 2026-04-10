#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <thread>

#include "Config.hh"
#include "Record.hh"

int main() {
    Config::Root root;
    root.rootDirectory = "output/Record_FatalStall_Harness/";
    root.logDirectory = "output/Record_FatalStall_Harness/logs/";
    root.logName = "output/Record_FatalStall_Harness/logs/harness.log";
    root.runStatName = "output/Record_FatalStall_Harness/logs/harness_runstat.log";
    root.threadStatDirectory = "output/Record_FatalStall_Harness/logs/threads/";
    root.fileTitle = "Record_FatalStall_Harness";

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
        Record::AsyncLogger logger;
        logger.setFatalStallHandler([&](const Record::RunSnapshot&) {
            {
                std::lock_guard<std::mutex> lock(mutex);
                ++fatalCallbackCount;
            }
            cv.notify_one();
        });

        logger.start(root, logging);
        logger.publish(logging, Record::RunPhase::Starting, 0, Record::DontRenderStatus, Record::DontRenderBar, Record::WriteRunStat);
        logger.publish(logging, Record::RunPhase::Analysis, 1, Record::DontRenderStatus, Record::DontRenderBar, Record::WriteRunStat);

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
        Record::AsyncLogger logger;
        logger.setFatalStallHandler([&](const Record::RunSnapshot&) {
            std::lock_guard<std::mutex> lock(mutex);
            ++fatalCallbackCount;
        });

        logging.start = std::chrono::system_clock::now();
        logger.start(root, logging);
        logger.publish(logging, Record::RunPhase::Starting, 0, Record::DontRenderStatus, Record::DontRenderBar, Record::WriteRunStat);
        std::this_thread::sleep_for(std::chrono::seconds(6));
        logger.stop();
    }

    {
        Record::AsyncLogger logger;
        logger.setFatalStallHandler([&](const Record::RunSnapshot&) {
            std::lock_guard<std::mutex> lock(mutex);
            ++fatalCallbackCount;
        });

        logging.start = std::chrono::system_clock::now();
        logger.start(root, logging);
        logger.publish(logging, Record::RunPhase::Finished, logging.nEvents, Record::DontRenderStatus, Record::DontRenderBar, Record::WriteRunStat);
        std::this_thread::sleep_for(std::chrono::seconds(6));
        logger.stop();
    }

    if (fatalCallbackCount != 1) {
        std::cerr << "starting/finished phases incorrectly triggered fatal detection\n";
        return EXIT_FAILURE;
    }

    std::cout << "Record fatal stall harness passed\n";
    return EXIT_SUCCESS;
}
