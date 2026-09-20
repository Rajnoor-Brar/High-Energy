#pragma once

// ── ML/Types.hh ──────────────────────────────────────────────────────────────
// What an inference call is given and what it hands back (05 §6, 13 §2).
//
// Nothing here includes ONNX Runtime. A `Scratch` is two `std::vector<float>`s and `Floats` is a
// pointer and a length, so a module can build and hold its inputs in a build with `HEKIT_WITH_ONNX`
// off and only the call itself disappears. That is also what makes the "build with ONNX off" row
// cheap to keep green.
//
// **`Floats` is `std::span<const float>`**, which 05 §6 writes and C++17 does not have. It is the
// same thing with the same name for its members, so the day this project moves to C++20 the alias
// changes and nothing else does.
//
// **`Scratch` is per worker, and that is the whole concurrency design.** `Ort::Session::Run` is
// thread-safe; the buffers around it are not. One session is shared by every worker and each worker
// owns a `Scratch`, so there is nothing to lock and nothing to merge — the same shape as
// `Results::Worker`, for the same reason.

#include <cstddef>
#include <string>
#include <vector>

namespace ML {

    /// A read-only view of contiguous floats. What `std::span<const float>` will be under C++20.
    class Floats {
      public:
        Floats() = default;
        Floats(const float* data, std::size_t size) : data_(data), size_(size) {}
        explicit Floats(const std::vector<float>& values)
            : data_(values.data()), size_(values.size()) {}

        const float* data() const { return data_; }
        std::size_t size() const { return size_; }
        bool empty() const { return size_ == 0; }
        const float* begin() const { return data_; }
        const float* end() const { return data_ + size_; }
        float operator[](std::size_t index) const { return data_[index]; }

      private:
        const float* data_ = nullptr;
        std::size_t size_ = 0;
    };

    /// One worker's buffers, reused between events so only the first call allocates.
    struct Scratch {
        std::vector<float> input;
        std::vector<float> output;

        void reset() {
            input.clear();
            output.clear();
        }
    };

    /// How to open a model.
    struct Options {
        /// **One**, and deliberately. The run already has k workers; letting ONNX start its own pool
        /// inside each of them oversubscribes the machine and makes the timing unrepeatable.
        int intra_op_threads = 1;
        bool optimise = true;

        /// The names the caller expects. Empty means "whatever the model has", which is only
        /// allowed when it has exactly one of each — a model whose inputs got renamed between
        /// training and here is otherwise a silent wrong answer.
        std::string input;
        std::string output;
    };

    /// One tensor of a model's signature, as the file declares it.
    struct Signature {
        std::string name;
        std::vector<long long> dims;   ///< −1 where the model leaves it dynamic (the batch)
        std::size_t width = 0;         ///< the last dimension: one row's worth of numbers
    };

}  // namespace ML
