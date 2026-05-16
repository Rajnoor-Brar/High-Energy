#pragma once

#include <algorithm>
#include <stdexcept>
#include <utility>
#include <vector>

#include "Config.hh"
#include "Probe/Administration.hh"
#include "Probe/ConfigAid.hh"
#include "Probe/Parallel.hh"
#include "Probe/ParallelIMT.hh"

namespace Probe {

inline void ProbeParallel::configureProbe(std::string inputFile,
                                          std::vector<CollectionSpec> particleSpecs,
                                          std::size_t threadCount,
                                          std::size_t requestedEvents,
                                          bool userRequestedEvents) {
            BranchControl::enableRootThreadSafety();

            inputFile_      = std::move(inputFile);
            particleSpecs_  = std::move(particleSpecs);
            threadCount_    = Config::resolveThreadCount(threadCount);
            configured_     = false;
            eventCount_     = 0;
            eventRange_     = {};
            eventPartitions_.clear();
            entryBoundsByWorker_.clear();

            if (inputFile_.empty())
                throw std::runtime_error("[Probe] ProbeParallel: input file is empty");
            if (particleSpecs_.empty())
                throw std::runtime_error("[Probe] ProbeParallel: no particle specs configured");
            if (threadCount_ == 0)
                throw std::runtime_error("[Probe] ProbeParallel: resolved thread count is zero");

            determineStreamType();

            std::vector<Long64_t> bruteKeys;
            if (userRequestedEvents) {
                eventCount_ = requestedEvents;
            } else {
                eventCount_ = Probe::resolveEventCount(inputFile_);
                if (eventCount_ == 0) {
                    if (streamType_ == StreamType::Events) {
                        bruteKeys = scanFlatEventKeys();
                        eventCount_ = bruteKeys.size();
                    } else if (streamType_ == StreamType::Vectors) {
                        eventCount_ = vectorEntryCount();
                    }
                }
            }

            if (eventCount_ == 0) {
                configured_ = true;
                return;
            }

            prepareEventPartitions(bruteKeys);
            prepareEntryBounds();

            queueCapacity_ = 10 * threadCount_;

            configured_ = true;
        }

inline void ProbeParallel::setCallbackMode(CallbackMode mode) { callbackMode_ = mode; }

inline void ProbeParallel::setQueueCapacity(std::size_t capacity) {
            queueCapacity_ = capacity;
        }

inline void ProbeParallel::setAnalysisThreadCount(std::size_t n) {
            analysisThreadCount_ = n;
        }

inline void ProbeIMT::configureProbe(std::string inputFile,
                                     std::vector<CollectionSpec> particleSpecs,
                                     std::size_t threadCount,
                                     std::size_t requestedEvents,
                                     bool userRequestedEvents) {
            BranchControl::enableRootThreadSafety();

            inputFile_     = std::move(inputFile);
            specs_         = std::move(particleSpecs);
            threadCount_   = Config::resolveThreadCount(threadCount);
            configured_    = false;
            eventCount_    = 0;
            firstEventKey_ = 0;

            if (inputFile_.empty())
                throw std::runtime_error("[Probe::IMT] empty input file");
            if (specs_.empty())
                throw std::runtime_error("[Probe::IMT] no particle specs");
            if (threadCount_ == 0)
                throw std::runtime_error("[Probe::IMT] thread count is zero");

            for (const auto& spec : specs_) {
                if (spec.indexBranches.empty())
                    throw std::runtime_error(
                        "[Probe::IMT] vector-stream specs not supported in IMT mode (spec '" +
                        spec.label + "' has no index branch)");
            }

            if (userRequestedEvents) eventCount_ = requestedEvents;
            else                     eventCount_ = Probe::resolveEventCount(inputFile_);

            if (eventCount_ == 0) {
                configured_ = true;
                return;
            }

            firstEventKey_ = BranchControl::probeFirstKey(inputFile_, specs_);
            configured_    = true;
        }

} // namespace Probe
