#pragma once

#include <cstdint>
#include <limits>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "TTreeReader.h"
#include "TTreeReaderArray.h"

#include "Probe/BranchControl.hh"
#include "Probe/Types.hh"

namespace Probe {

    class FlatReader {
      public:
        FlatReader(TFile* file, const CollectionSpec& spec,
                   const std::string& filepath,
                   Long64_t minKey, Long64_t maxKey,
                   Bounds entryBounds = {},
                   bool hasEntryBounds = false);

        FlatReader(const FlatReader&)            = delete;
        FlatReader& operator=(const FlatReader&) = delete;

        const std::string& label() const;
        EventKey currentKey() const;
        bool exhausted() const;
        bool beyondMax() const;
        void ensureLabel(Event& ev) const;
        void drain(const EventKey& key, Event& ev);
        bool keyRange(Long64_t lo, Long64_t hi, Long64_t& outMin, Long64_t& outMax);

      private:
        Long64_t idxValue() const;

        struct AuxBuf { float f = 0.f; double d = 0.0; int32_t i = 0; uint32_t u = 0; int64_t l = 0; uint64_t ul = 0; bool b = false; };

        void bindAux(const BranchSpec& bspec);
        static AuxColumn makeAuxCol(BranchType t);
        void appendAux(std::unordered_map<std::string, AuxColumn>& m);

        std::string              label_;
        std::string              filepath_;
        CoordSpec                coords_;
        TTree*                   tree_         = nullptr;
        std::string              idxName_;
        Long64_t                 cursor_       = 0;
        Long64_t                 totalEntries_ = 0;
        Long64_t                 entryEnd_     = 0;
        Long64_t                 minKey_;
        Long64_t                 maxKey_;
        bool                     idxIsLong_   = false;
        Int_t                    idxI_         = 0;
        Long64_t                 idxL_         = 0;
        BranchControl::KinBuf    kinBuf_[4];
        std::vector<std::string> auxNames_;
        std::vector<BranchType>  auxTypes_;
        std::vector<AuxBuf>      auxBufs_;
    };

    class VecReader {
      public:
        VecReader(TFile* file, const CollectionSpec& spec,
                  const std::string& filepath,
                  Long64_t minEntry = 0,
                  Long64_t maxEntry = std::numeric_limits<Long64_t>::max());

        VecReader(const VecReader&)            = delete;
        VecReader& operator=(const VecReader&) = delete;

        bool next();
        Long64_t totalEntries() const;
        void fill(Event& ev);

      private:
        std::string  label_;
        std::string  filepath_;
        CoordSpec    coords_;
        TTreeReader  reader_;
        Long64_t     totalEntries_ = 0;
        std::unique_ptr<TTreeReaderArray<float>> kinArrays_[4];
        std::vector<std::string> auxNames_;
        std::vector<std::unique_ptr<TTreeReaderArray<float>>> auxArrays_;
    };

    class EventStream {
      public:
        EventStream(const std::string& filepath,
                    const std::vector<CollectionSpec>& collections,
                    Long64_t minBound = std::numeric_limits<Long64_t>::min(),
                    Long64_t maxBound = std::numeric_limits<Long64_t>::max(),
                    std::size_t nEventsHint = 0,
                    const std::vector<Bounds>& entryBounds = {});
        ~EventStream();

        EventStream(const EventStream&)            = delete;
        EventStream& operator=(const EventStream&) = delete;

        bool next();
        const Event& event() const;
        Event takeEvent();
        std::size_t nEvents() const;
        std::size_t index() const;

      private:
        bool nextFlat();
        bool nextVec();

        std::string   filepath_;
        TFile*        file_     = nullptr;
        bool          isVec_    = false;
        Long64_t      minBound_;
        Long64_t      maxBound_;
        Event         current_;
        std::size_t   index_   = 0;
        std::size_t   nEvents_ = 0;
        Long64_t      denseLo_ = 0;
        Long64_t      denseHi_ = -1;
        Long64_t      nextKey_ = 0;

        std::vector<std::unique_ptr<FlatReader>> flatReaders_;
        std::vector<std::unique_ptr<VecReader>>  vecReaders_;
    };

} // namespace Probe
