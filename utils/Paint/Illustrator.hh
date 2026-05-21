#pragma once

#include <ostream>
#include <stdexcept>
#include <string>
#include <utility>

#include "Paint/Book.hh"
#include "Paint/Render.hh"
#include "Paint/Resolve.hh"
#include "Paint/Types.hh"

namespace Paint {

    class Illustrator {
    public:
        explicit Illustrator(std::string configPath)
            : configPath_(std::move(configPath)) {}

        void load() {
            book_ = loadBook(configPath_);
            resolved_ = false;
        }

        void resolve() {
            plan_ = resolveBook(book_);
            resolved_ = true;
        }

        void dryRun(std::ostream& os) const {
            ensureResolved();
            printPlan(plan_, os);
        }

        void render() {
            ensureResolved();
            renderPlan(plan_);
        }

    private:
        void ensureResolved() const {
            if (!resolved_) {
                throw std::runtime_error("Paint::Illustrator: resolve() must be called before dryRun/render");
            }
        }

        std::string configPath_;
        PaintBook book_;
        RenderPlan plan_;
        bool resolved_{false};
    };

} // namespace Paint
