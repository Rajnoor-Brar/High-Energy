#pragma once

#include <algorithm>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <utility>

#include "Probe/Parallel.hh"
#include "Probe/ParallelIMT.hh"

namespace Probe {

inline ProbeParallel::ProbeParallel() = default;

inline ProbeParallel::~ProbeParallel() = default;

inline const std::string& ProbeParallel::inputFile() const { return inputFile_; }

inline std::size_t ProbeParallel::threadCount() const { return threadCount_; }

inline std::size_t ProbeParallel::analysisThreadCount() const {
            return analysisThreadCount_ > 0 ? analysisThreadCount_ : threadCount_;
        }

inline std::size_t ProbeParallel::eventCount() const { return eventCount_; }

inline StreamType ProbeParallel::streamType() const { return streamType_; }

inline std::string ProbeParallel::stats() const {
            std::lock_guard<std::mutex> lock(queueMutex_);

            std::ostringstream out;
            out << "ProbeParallel{"
                << "streamType=" << streamTypeName(streamType_)
                << ", callbackMode=" << callbackModeName(callbackMode_)
                << ", threadCount=" << threadCount_
                << ", activeWorkers=" << eventPartitions_.size()
                << ", eventCount=" << eventCount_
                << ", queueCapacity=" << queueCapacity_
                << ", produced=" << produced_
                << ", consumed=" << consumed_
                << ", progress=[";
            for (std::size_t i = 0; i < progress_.size(); ++i) {
                if (i) out << ',';
                out << progress_[i].load(std::memory_order_relaxed);
            }
            out << "]}";
            return out.str();
        }

inline const char* ProbeParallel::streamTypeName(StreamType type) {
            switch (type) {
                case StreamType::Unset:   return "Unset";
                case StreamType::Events:  return "Events";
                case StreamType::Vectors: return "Vectors";
            }
            return "Unknown";
        }

inline const char* ProbeParallel::callbackModeName(CallbackMode mode) {
            switch (mode) {
                case CallbackMode::WorkerThread:    return "WorkerThread";
                case CallbackMode::CollectorThread: return "CollectorThread";
            }
            return "Unknown";
        }

inline void ProbeParallel::determineStreamType() {
            bool anyFlat = false;
            bool anyVec  = false;
            for (const auto& spec : particleSpecs_) {
                if (spec.indexBranches.empty()) anyVec  = true;
                else                            anyFlat = true;
            }

            if (anyFlat && anyVec)
                throw std::runtime_error("[Probe] ProbeParallel: cannot mix indexed and vector particle specs");

            streamType_ = anyVec ? StreamType::Vectors : StreamType::Events;
        }

inline std::vector<Long64_t> ProbeParallel::scanFlatEventKeys() const {
            std::unique_ptr<TFile> file(TFile::Open(inputFile_.c_str(), "READ"));
            if (!file || file->IsZombie())
                throw std::runtime_error("[Probe] Failed to open file '" + inputFile_ + "'");

            std::set<Long64_t> keySet;
            for (const auto& spec : particleSpecs_) {
                if (!spec.indexBranches.empty())
                    BranchControl::scanIndexBranch(
                        file.get(), spec.tree, spec.indexBranches[0].name, keySet, inputFile_);
            }
            return {keySet.begin(), keySet.end()};
        }

inline std::size_t ProbeParallel::vectorEntryCount() const {
            std::unique_ptr<TFile> file(TFile::Open(inputFile_.c_str(), "READ"));
            if (!file || file->IsZombie())
                throw std::runtime_error("[Probe] Failed to open file '" + inputFile_ + "'");

            TTree* tree = dynamic_cast<TTree*>(file->Get(particleSpecs_[0].tree.c_str()));
            if (!tree) return 0;
            return static_cast<std::size_t>(std::max<Long64_t>(0, tree->GetEntries()));
        }

inline std::vector<BranchControl::Partition>
ProbeParallel::partitionDenseRange(Long64_t first, Long64_t last, std::size_t n) {
            std::vector<BranchControl::Partition> parts;
            if (n == 0 || first > last) return parts;

            const Long64_t total = last - first + 1;
            const Long64_t chunk = (total + static_cast<Long64_t>(n) - 1)
                                 / static_cast<Long64_t>(n);
            for (Long64_t start = first; start <= last; start += chunk)
                parts.push_back({start, std::min(last, start + chunk - 1)});
            return parts;
        }

inline void ProbeParallel::prepareEventPartitions(const std::vector<Long64_t>& bruteKeys) {
            if (streamType_ == StreamType::Vectors) {
                eventRange_ = {0, static_cast<Long64_t>(eventCount_) - 1};
                eventPartitions_ = partitionDenseRange(eventRange_.first, eventRange_.last, threadCount_);
                return;
            }

            if (!bruteKeys.empty()) {
                eventRange_ = {bruteKeys.front(), bruteKeys.back()};
                eventPartitions_ = BranchControl::partitionEvents(bruteKeys, threadCount_);
                return;
            }

            const Long64_t first = BranchControl::probeFirstKey(inputFile_, particleSpecs_);
            const Long64_t last  = first + static_cast<Long64_t>(eventCount_) - 1;
            eventRange_ = {first, last};
            eventPartitions_ = partitionDenseRange(first, last, threadCount_);
        }

inline Long64_t ProbeParallel::indexValue(BranchType type, Long64_t longValue, Int_t intValue) {
            return type == BranchType::Int64 ? longValue : static_cast<Long64_t>(intValue);
        }

inline void ProbeParallel::prepareEntryBounds() {
            entryBoundsByWorker_.clear();
            if (streamType_ != StreamType::Events || eventPartitions_.empty()) return;

            entryBoundsByWorker_.assign(
                eventPartitions_.size(), std::vector<Bounds>(particleSpecs_.size()));

            std::unique_ptr<TFile> file(TFile::Open(inputFile_.c_str(), "READ"));
            if (!file || file->IsZombie())
                throw std::runtime_error("[Probe] Failed to open file '" + inputFile_ + "'");

            for (std::size_t p = 0; p < particleSpecs_.size(); ++p) {
                const auto& spec = particleSpecs_[p];
                if (spec.indexBranches.empty()) continue;

                TTree* tree = dynamic_cast<TTree*>(file->Get(spec.tree.c_str()));
                if (!tree)
                    throw std::runtime_error(
                        "[Probe] Missing tree '" + spec.tree + "' in file '" + inputFile_ + "'");

                const std::string& idxName = spec.indexBranches[0].name;
                TBranch* branch = BranchControl::requireBranch(tree, idxName, inputFile_);
                const BranchType type = RootUtil::detectBranchType(branch);
                if (type != BranchType::Int32 && type != BranchType::Int64 && type != BranchType::UInt32)
                    throw std::runtime_error(
                        "[Probe] Index branch '" + idxName + "' in tree '" + spec.tree +
                        "' of file '" + inputFile_ + "': must be Int_t, UInt_t, or Long64_t");

                tree->SetBranchStatus("*", 0);
                tree->SetBranchStatus(idxName.c_str(), 1);

                Long64_t longValue = 0;
                Int_t    intValue  = 0;
                if (type == BranchType::Int64) tree->SetBranchAddress(idxName.c_str(), &longValue);
                else                           tree->SetBranchAddress(idxName.c_str(), &intValue);

                const Long64_t entries = tree->GetEntries();
                std::size_t part = 0;
                bool havePrevious = false;
                Long64_t previous = 0;

                for (Long64_t row = 0; row < entries && part < eventPartitions_.size(); ++row) {
                    tree->GetEntry(row);
                    const Long64_t value = indexValue(type, longValue, intValue);

                    if (havePrevious && value < previous) {
                        tree->ResetBranchAddresses();
                        throw std::runtime_error(
                            "[Probe] Index branch '" + idxName + "' in tree '" + spec.tree +
                            "' (file '" + inputFile_ + "'): row " + std::to_string(row) +
                            " value " + std::to_string(value) +
                            " < previous " + std::to_string(previous) +
                            "; CollectorThread event bounds require ascending index data");
                    }
                    havePrevious = true;
                    previous = value;

                    while (part < eventPartitions_.size()
                        && value > eventPartitions_[part].lastEvent)
                        ++part;

                    if (part >= eventPartitions_.size()) break;
                    if (value < eventPartitions_[part].firstEvent) continue;

                    Bounds& bounds = entryBoundsByWorker_[part][p];
                    if (!bounds.valid()) bounds.first = row;
                    bounds.last = row;
                }

                tree->ResetBranchAddresses();
            }
        }

inline std::size_t ProbeParallel::eventsInPartition(const BranchControl::Partition& part) const {
            if (part.lastEvent < part.firstEvent) return 0;
            return static_cast<std::size_t>(part.lastEvent - part.firstEvent + 1);
        }

inline void ProbeParallel::resetRuntimeState() {
            stopRequested_.store(false, std::memory_order_release);
            workersFinished_ = 0;
            produced_ = 0;
            consumed_ = 0;
            progress_ = std::vector<std::atomic<std::size_t>>(eventPartitions_.size());
            for (auto& p : progress_) p.store(0, std::memory_order_relaxed);
            queue_.clear();
        }

inline void ProbeParallel::requestStop() {
            stopRequested_.store(true, std::memory_order_release);
            queueNotEmpty_.notify_all();
            queueNotFull_.notify_all();
        }

inline bool ProbeParallel::pushQueuedEvent(QueuedEvent event) {
            std::unique_lock<std::mutex> lock(queueMutex_);
            queueNotFull_.wait(lock, [&] {
                return stopRequested_.load(std::memory_order_acquire)
                    || queue_.size() < queueCapacity_;
            });

            if (stopRequested_.load(std::memory_order_acquire)) return false;

            const std::size_t worker = event.workerIndex;
            queue_.push_back(std::move(event));
            ++produced_;

            lock.unlock();
            queueNotEmpty_.notify_one();
            if (worker < progress_.size()) progress_[worker].fetch_add(1, std::memory_order_relaxed);
            return true;
        }

inline bool ProbeParallel::popQueuedEvent(QueuedEvent& event) {
            std::unique_lock<std::mutex> lock(queueMutex_);
            queueNotEmpty_.wait(lock, [&] {
                return stopRequested_.load(std::memory_order_acquire)
                    || !queue_.empty()
                    || workersFinished_ >= eventPartitions_.size();
            });

            if (queue_.empty()) return false;

            event = std::move(queue_.front());
            queue_.pop_front();
            ++consumed_;

            lock.unlock();
            queueNotFull_.notify_one();
            return true;
        }

inline void ProbeParallel::markWorkerFinished() {
            {
                std::lock_guard<std::mutex> lock(queueMutex_);
                ++workersFinished_;
            }
            queueNotEmpty_.notify_all();
        }

inline ProbeIMT::ProbeIMT() = default;

inline const std::string& ProbeIMT::inputFile() const { return inputFile_; }

inline std::size_t ProbeIMT::threadCount() const { return threadCount_; }

inline std::size_t ProbeIMT::eventCount() const { return eventCount_; }

inline StreamType ProbeIMT::streamType() const { return StreamType::Events; }

inline std::string ProbeIMT::stats() const {
            std::ostringstream out;
            out << "ProbeIMT{streamType=Events"
                << ", threadCount=" << threadCount_
                << ", eventCount="  << eventCount_
                << ", firstKey="    << firstEventKey_
                << ", consumed="    << consumed_.load()
                << "}";
            return out.str();
        }

} // namespace Probe
