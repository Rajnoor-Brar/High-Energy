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

// ── configureProbe (ProbeConfig) ─────────────────────────────────────────────
inline void ProbeParallel::configureProbe(std::string inputFile,
                                          ProbeConfig config,
                                          std::size_t threadCount,
                                          std::size_t requestedEvents,
                                          bool userRequestedEvents) {
    BranchControl::enableRootThreadSafety();

    inputFile_   = std::move(inputFile);
    config_      = std::move(config);
    threadCount_ = Config::resolveThreadCount(threadCount);
    configured_  = false;
    eventCount_  = 0;
    eventRange_  = {};
    eventPartitions_.clear();
    entryBoundsByWorker_.clear();

    if (inputFile_.empty())
        throw std::runtime_error("[Probe] ProbeParallel: input file is empty");
    if (!config_.hasEventData() && !config_.hasFeedData())
        throw std::runtime_error("[Probe] ProbeParallel: ProbeConfig has no specs");
    if (threadCount_ == 0)
        throw std::runtime_error("[Probe] ProbeParallel: resolved thread count is zero");

    // Resolve activeMode
    const bool hasEvent = config_.hasEventData();
    const bool hasFeed  = config_.hasFeedData();
    switch (config_.requestedMode) {
        case StreamMode::Auto:
            activeMode_ = (hasEvent && hasFeed) ? ActiveMode::Mixed
                        : hasEvent ? ActiveMode::Events : ActiveMode::Feed;
            break;
        case StreamMode::Events:
            if (!hasEvent) throw std::runtime_error(
                "[Probe] configureProbe: stream='events' but no event specs");
            activeMode_ = ActiveMode::Events;
            break;
        case StreamMode::Feed:
            if (!hasFeed) throw std::runtime_error(
                "[Probe] configureProbe: stream='feed' but no feed specs");
            activeMode_ = ActiveMode::Feed;
            break;
    }

    if (hasEvent) {
        determineStreamType();
    } else {
        streamType_ = StreamType::Events; // placeholder; not used for feed-only
    }

    // Resolve event count
    std::vector<Long64_t> bruteKeys;
    if (userRequestedEvents) {
        eventCount_ = requestedEvents;
    } else if (hasEvent) {
        eventCount_ = Probe::resolveEventCount(inputFile_);
        if (eventCount_ == 0) {
            if (streamType_ == StreamType::Events) {
                bruteKeys = scanFlatEventKeys();
                eventCount_ = bruteKeys.size();
            } else {
                eventCount_ = vectorEntryCount();
            }
        }
    } else {
        // Feed-only: derive event count from first feed tree
        std::unique_ptr<TFile> f(TFile::Open(inputFile_.c_str(), "READ"));
        if (!f || f->IsZombie())
            throw std::runtime_error("[Probe] Failed to open file '" + inputFile_ + "'");
        const std::string treeName = !config_.feedParticles.empty()
            ? config_.feedParticles[0].tree : config_.feedNodes[0].tree;
        TTree* t = dynamic_cast<TTree*>(f->Get(treeName.c_str()));
        eventCount_ = t ? static_cast<std::size_t>(
                              std::max<Long64_t>(0, t->GetEntries())) : 0;
    }

    if (eventCount_ == 0) {
        configured_ = true;
        return;
    }

    prepareEventPartitions(bruteKeys);
    if (hasEvent && streamType_ == StreamType::Events)
        prepareEntryBounds();

    queueCapacity_ = 10 * threadCount_;
    configured_ = true;
}

inline void ProbeIMT::configureProbe(std::string inputFile,
                                     ProbeConfig config,
                                     std::size_t threadCount,
                                     std::size_t requestedEvents,
                                     bool userRequestedEvents) {
    configureProbe(std::move(inputFile),
                   std::move(config.eventParticles),
                   threadCount, requestedEvents, userRequestedEvents);
}

inline void ProbeParallel::setCallbackMode(CallbackMode mode) { callbackMode_ = mode; }

inline void ProbeParallel::setQueueCapacity(std::size_t capacity) {
    queueCapacity_ = capacity;
}

inline void ProbeParallel::setAnalysisThreadCount(std::size_t n) {
    analysisThreadCount_ = n;
}

inline void ProbeIMT::configureProbe(std::string inputFile,
                                     std::vector<EventParticleSpec> particleSpecs,
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
