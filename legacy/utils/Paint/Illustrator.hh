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
            loaded_   = true;
            resolved_ = false;
        }

        void resolve() {
            if (!loaded_) load();
            plan_ = resolveBook(book_);
            resolved_ = true;
        }

        // dryRun/render lazily load + resolve, so the minimal driver is just
        // `Illustrator(path).render()`. Explicit load()/resolve() still work
        // for callers that want to separate config errors from render errors.
        void dryRun(std::ostream& os) {
            ensureResolved();
            printPlan(plan_, os);
        }

        void render() {
            ensureResolved();
            renderPlan(plan_);
        }

    private:
        void ensureResolved() {
            if (!resolved_) resolve();
        }

        std::string configPath_;
        PaintBook book_;
        RenderPlan plan_;
        bool loaded_{false};
        bool resolved_{false};
    };

} // namespace Paint
