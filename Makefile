# A thin wrapper around CMake, so `make` still does the obvious thing.
#
# Everything is built by CMake now (P2-S01); this file exists because `make` and `make test` are what
# hands reach for. It adds nothing of its own — each target is one cmake or ctest command, and
# `hep build` is the same thing with project-aware flags.
#
# The HEP environment comes first: `load_hep` (env/hep_env.sh).

SHELL := /bin/sh
.DEFAULT_GOAL := help

BUILD ?= build
JOBS  ?=
CMAKE_FLAGS ?=

.PHONY: help all configure build test slow analyses modules clean distclean

help:
	@echo "make                 build everything (configure first if needed)"
	@echo "make test            ctest: C++ checks and the Python suite"
	@echo "make slow            ctest -L slow: the equivalence gates and end-to-end runs"
	@echo "make analyses P=NAME build one project's Rivet plugins"
	@echo "make modules  P=NAME build one project's analysis modules"
	@echo "make clean           remove build products, keep the configuration"
	@echo "make distclean       remove $(BUILD) entirely"
	@echo
	@echo "BUILD=$(BUILD)   JOBS=$(JOBS)   (hep build does the same with project flags)"

all: build

$(BUILD)/CMakeCache.txt:
	cmake -S . -B $(BUILD) $(CMAKE_FLAGS)

configure:
	cmake -S . -B $(BUILD) $(CMAKE_FLAGS)

build: $(BUILD)/CMakeCache.txt
	cmake --build $(BUILD) $(if $(JOBS),-j $(JOBS),)

test: build
	ctest --test-dir $(BUILD) -LE slow --output-on-failure

slow: build
	ctest --test-dir $(BUILD) -L slow --output-on-failure

analyses: $(BUILD)/CMakeCache.txt
	@test -n "$(P)" || { echo "usage: make analyses P=PhotoProduction" >&2; exit 2; }
	cmake --build $(BUILD) --target rivet_$(P)

modules: $(BUILD)/CMakeCache.txt
	@test -n "$(P)" || { echo "usage: make modules P=PhotoProduction" >&2; exit 2; }
	cmake --build $(BUILD) --target modules_$(P)

clean:
	@test -d $(BUILD) && cmake --build $(BUILD) --target clean || echo "nothing to clean"

distclean:
	rm -rf $(BUILD)
