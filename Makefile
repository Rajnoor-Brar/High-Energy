SHELL := /bin/sh
CXX ?= g++

BASE_CXXFLAGS := -O2 -march=native -std=c++17 -I./utils -I./modules
TOML_FLAGS   := $(shell pkg-config --cflags --libs tomlplusplus)

ROOT_FLAGS   := $(shell root-config --cflags --ldflags --glibs)
PYTHIA_FLAGS := $(shell pythia8-config --cxxflags --ldflags)

# ── Reproducibility defines ───────────────────────────────────────────────────
# Bake the git state into every binary so Meta::Record::integrity can report
# the exact source revision.  Falls back gracefully outside a git repo.
_GIT_SHA   := $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
_GIT_DIRTY := $(shell git diff --quiet 2>/dev/null && echo 0 || echo 1)
GIT_DEFINES := -DGIT_SHA=\"$(_GIT_SHA)\" -DGIT_DIRTY=$(_GIT_DIRTY)

all:
	@echo "Usage: make <program> or make <program>.exe (source must be <program>.cc)"

# Build rule
%.exe: %.cc
	@$(CXX) $< -o $@ $(ROOT_FLAGS) $(PYTHIA_FLAGS) $(TOML_FLAGS) $(BASE_CXXFLAGS) $(GIT_DEFINES)
	@echo "$< --> $@"

# Allow `make myprog` to build `myprog.exe`
%: %.exe
	@true

# ── Test targets ─────────────────────────────────────────────────────────────
# Tests that need the full driver stack (ROOT + Pythia8 + toml++)
TEST_EXES := tests/test_reconstructCandidates.exe tests/test_probe_parallel.exe tests/test_record_writer.exe tests/test_rootAnalysis_smoke.exe

tests/%.exe: tests/%.cc
	@$(CXX) $< -o $@ $(ROOT_FLAGS) $(PYTHIA_FLAGS) $(TOML_FLAGS) $(BASE_CXXFLAGS) $(GIT_DEFINES)
	@echo "$< --> $@"

# Fixture generator — ROOT only, no Pythia8
tests/fixtures/%.exe: tests/fixtures/%.cc
	@$(CXX) $< -o $@ $(ROOT_FLAGS) $(TOML_FLAGS) $(BASE_CXXFLAGS) $(GIT_DEFINES)
	@echo "$< --> $@"

.PHONY: test
test: $(TEST_EXES)
	@sh tests/run_all.sh

.PHONY: clean
clean:
	@rm -f *.exe tests/*.exe tests/fixtures/*.exe
	@echo "Executables removed"
