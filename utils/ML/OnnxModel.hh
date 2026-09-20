#pragma once

// ── ML/OnnxModel.hh ──────────────────────────────────────────────────────────
// One ONNX model, shared by every worker (05 §6, R11).
//
// **One session, many workers.** `Ort::Session::Run` is thread-safe, so the expensive thing — the
// loaded graph and its weights — is created once and every worker calls into it. What is *not*
// thread-safe is the buffers around the call, so those live in a `Scratch` the caller owns one of.
// The alternative, a session per worker, would load the weights k times and is what makes a model
// look like it does not fit in memory when it does.
//
// **The signature is checked when the model is opened**, not when it is run. A model with two inputs,
// a non-float tensor, or an input whose width does not match what the caller is about to feed it is
// a configuration mistake, and 06 §3.3's rule is that those cost a second rather than a run. The
// same goes for the names: `Options::input` is compared against the file, because a model whose
// input was renamed between training and here otherwise gives a confident wrong answer.
//
// **The hash goes into provenance.** Two runs that disagree and were "the same model" are the
// commonest way to lose a day; `sha256()` is over the file's bytes, so the summary records which
// weights actually answered.

#include <algorithm>
#include <array>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

#include "onnxruntime_cxx_api.h"

#include "Core/Errors.hh"
#include "Core/Sha256.hh"
#include "ML/Types.hh"

namespace ML {

    namespace detail {

        /// One `Ort::Env` for the process, kept alive by every model that uses it.
        ///
        /// A `shared_ptr` rather than a plain function-local static because the environment must
        /// outlive every session built from it, and static destruction order across translation
        /// units does not promise that. Each model holds a copy, so the last model out turns off
        /// the lights.
        inline std::shared_ptr<Ort::Env> environment() {
            static const std::shared_ptr<Ort::Env> shared =
                std::make_shared<Ort::Env>(ORT_LOGGING_LEVEL_WARNING, "hekit");
            return shared;
        }

        inline std::size_t widthOf(const std::vector<long long>& dims) {
            return dims.empty() ? 0 : static_cast<std::size_t>(dims.back() > 0 ? dims.back() : 0);
        }

        inline std::string shapeText(const std::vector<long long>& dims) {
            std::string text = "[";
            for (std::size_t index = 0; index < dims.size(); ++index) {
                if (index != 0) text += ", ";
                text += dims[index] < 0 ? std::string("?") : std::to_string(dims[index]);
            }
            return text + "]";
        }

    }  // namespace detail

    class OnnxModel {
      public:
        explicit OnnxModel(const std::filesystem::path& path, Options options = {})
            : path_(path.string()), options_(std::move(options)), environment_(detail::environment()) {
            if (!Core::isRegularFile(path_))
                throw Core::Error{Core::Exit::Config, "no ONNX model at " + path_,
                                  "[[sinks.module]].options names it; check the path"};
            sha256_ = Core::sha256File(path_);

            Ort::SessionOptions settings;
            settings.SetIntraOpNumThreads(std::max(1, options_.intra_op_threads));
            settings.SetInterOpNumThreads(1);
            settings.SetGraphOptimizationLevel(options_.optimise
                                                   ? GraphOptimizationLevel::ORT_ENABLE_ALL
                                                   : GraphOptimizationLevel::ORT_DISABLE_ALL);
            try {
                session_ = std::make_unique<Ort::Session>(*environment_, path_.c_str(), settings);
            } catch (const Ort::Exception& error) {
                throw Core::Error{Core::Exit::Config,
                                  std::string("ONNX Runtime could not load ") + path_ + ": " +
                                      error.what()};
            }

            input_ = describe(/*is_input=*/true);
            output_ = describe(/*is_input=*/false);
            requireNames();
        }

        /// One row, or several laid out end to end. The returned view lives in `scratch` and is
        /// valid until the next call with that same scratch.
        ///
        /// Rows rather than a batch argument because the width is the model's and the caller knows
        /// only how many it has: `in.size()` must be a whole number of rows, and saying so is a
        /// better error than a reshaped tensor that runs and means nothing.
        Floats run(Floats in, Scratch& scratch) const {
            const std::size_t width = features();
            if (width == 0)
                throw Core::Error{Core::Exit::Internal,
                                  "this model does not declare how wide its input is",
                                  "an input whose last dimension is dynamic cannot be fed by row"};
            if (in.empty() || in.size() % width != 0)
                throw Core::Error{Core::Exit::Config,
                                  "this model takes a multiple of " + std::to_string(width) +
                                      " floats, and was given " + std::to_string(in.size())};
            const std::int64_t rows = static_cast<std::int64_t>(in.size() / width);

            // Copied rather than pointed at: `CreateTensor` wants a non-const pointer, and a
            // `const_cast` on the caller's buffer would be a promise this code cannot make on ONNX
            // Runtime's behalf. The buffer is reused, so only the first call allocates.
            scratch.input.assign(in.begin(), in.end());
            scratch.output.assign(static_cast<std::size_t>(rows) * outputs(), 0.0f);

            const std::array<std::int64_t, 2> in_shape{rows, static_cast<std::int64_t>(width)};
            const std::array<std::int64_t, 2> out_shape{rows,
                                                        static_cast<std::int64_t>(outputs())};
            const Ort::MemoryInfo memory =
                Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);

            Ort::Value input_tensor = Ort::Value::CreateTensor<float>(
                memory, scratch.input.data(), scratch.input.size(), in_shape.data(),
                in_shape.size());
            Ort::Value output_tensor = Ort::Value::CreateTensor<float>(
                memory, scratch.output.data(), scratch.output.size(), out_shape.data(),
                out_shape.size());

            const char* input_names[] = {input_.name.c_str()};
            const char* output_names[] = {output_.name.c_str()};
            try {
                session_->Run(Ort::RunOptions{nullptr}, input_names, &input_tensor, 1,
                              output_names, &output_tensor, 1);
            } catch (const Ort::Exception& error) {
                throw Core::Error{Core::Exit::Sink,
                                  std::string("ONNX Runtime failed on ") + path_ + ": " +
                                      error.what()};
            }
            return Floats{scratch.output.data(), scratch.output.size()};
        }

        std::size_t features() const { return input_.width; }
        std::size_t outputs() const { return output_.width; }
        const Signature& inputSignature() const { return input_; }
        const Signature& outputSignature() const { return output_; }

        /// The sha256 of the model file, for the run summary (07 §2).
        const std::string& sha256() const { return sha256_; }
        const std::string& path() const { return path_; }

        std::string describe() const {
            return path_ + " " + input_.name + detail::shapeText(input_.dims) + " -> " +
                   output_.name + detail::shapeText(output_.dims) + " (sha256 " +
                   sha256_.substr(0, 12) + ")";
        }

      private:
        Signature describe(bool is_input) const {
            const std::size_t count =
                is_input ? session_->GetInputCount() : session_->GetOutputCount();
            const char* side = is_input ? "input" : "output";
            if (count != 1)
                throw Core::Error{Core::Exit::Config,
                                  path_ + " has " + std::to_string(count) + " " + side +
                                      "s, and this interface takes exactly one",
                                  "a multi-input model needs its own wrapper, not a reshape here"};

            Ort::AllocatorWithDefaultOptions allocator;
            Signature found;
            found.name = is_input ? session_->GetInputNameAllocated(0, allocator).get()
                                  : session_->GetOutputNameAllocated(0, allocator).get();

            const Ort::TypeInfo info =
                is_input ? session_->GetInputTypeInfo(0) : session_->GetOutputTypeInfo(0);
            if (info.GetONNXType() != ONNX_TYPE_TENSOR)
                throw Core::Error{Core::Exit::Config,
                                  path_ + "'s " + side + " is not a tensor"};
            const auto tensor = info.GetTensorTypeAndShapeInfo();
            if (tensor.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT)
                throw Core::Error{Core::Exit::Config,
                                  path_ + "'s " + side + " is not float32",
                                  "export the model with float inputs; this interface does not cast"};
            const std::vector<std::int64_t> shape = tensor.GetShape();
            found.dims.assign(shape.begin(), shape.end());
            found.width = detail::widthOf(found.dims);
            if (found.width == 0)
                throw Core::Error{Core::Exit::Config,
                                  path_ + "'s " + side + " has a dynamic last dimension " +
                                      detail::shapeText(found.dims),
                                  "the batch may be dynamic; the width of a row may not"};
            return found;
        }

        void requireNames() const {
            if (!options_.input.empty() && options_.input != input_.name)
                throw Core::Error{Core::Exit::Config,
                                  path_ + " calls its input '" + input_.name + "', not '" +
                                      options_.input + "'"};
            if (!options_.output.empty() && options_.output != output_.name)
                throw Core::Error{Core::Exit::Config,
                                  path_ + " calls its output '" + output_.name + "', not '" +
                                      options_.output + "'"};
        }

        std::string path_;
        Options options_;
        std::shared_ptr<Ort::Env> environment_;
        std::unique_ptr<Ort::Session> session_;
        Signature input_;
        Signature output_;
        std::string sha256_;
    };

}  // namespace ML
