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


SOURCE_ROOT := sources
OUTPUT_ROOT := output

BASE_CXXFLAGS := -O2 -std=c++17 -I./utils -I./modules

TOML_FLAGS    := $(shell pkg-config --cflags --libs tomlplusplus)
ROOT_FLAGS    := $(shell root-config --cflags --ldflags --glibs)
PYTHIA_FLAGS  := $(shell pythia8-config --cxxflags --ldflags)
HEPMC3_FLAGS  := $(shell HepMC3-config --cflags --libs)
FASTJET_FLAGS := $(shell fastjet-config --cxxflags --libs --plugins=yes)
YODA_FLAGS    := $(shell yoda-config --cxxflags --libs)
LHAPDF_FLAGS  := $(shell lhapdf-config --cppflags --ldflags)

ONNX_DIR      ?= $(ONNXRUNTIME_DIR)
ONNX_FLAGS    := -I$(ONNX_DIR)/include -L$(ONNX_DIR)/lib -lonnxruntime -Wl,-rpath,$(ONNX_DIR)/lib

DELPHES_DIR   ?= $(HEP_INSTALL)/delphes
DELPHES_FLAGS := -I$(DELPHES_DIR)/include -L$(DELPHES_DIR)/lib -lDelphes -Wl,-rpath,$(DELPHES_DIR)/lib

ALL_LIB_FLAGS := $(ROOT_FLAGS) $(PYTHIA_FLAGS) $(HEPMC3_FLAGS) \
                 $(FASTJET_FLAGS) $(YODA_FLAGS) $(LHAPDF_FLAGS) \
                 $(ONNX_FLAGS) $(DELPHES_FLAGS) $(TOML_FLAGS)

GIT_SHA     := $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
GIT_DIRTY   := $(shell git diff --quiet 2>/dev/null && echo 0 || echo 1)
GIT_DEFINES := -DGIT_SHA=\"$(GIT_SHA)\" -DGIT_DIRTY=$(GIT_DIRTY)

COMPILE_DB ?= $(OUTPUT_ROOT)/compile_commands.json
CLEAN_FILES ?=

%.exe:
	@src="$(SOURCE_ROOT)/$(basename $@).cc"; \
	[ -f "$$src" ] || src="$(basename $@).cc"; \
	[ -f "$$src" ] || { echo "Missing source: $(SOURCE_ROOT)/$(basename $@).cc or $(basename $@).cc"; exit 2; }; \
	dest="$(OUTPUT_ROOT)/$(dir $@)$(notdir $@)"; \
	mkdir -p "$$(dirname "$$dest")"; \
	if [ ! -e "$$dest" ] || [ "$$src" -nt "$$dest" ] || [ Makefile -nt "$$dest" ]; then \
		$(CXX) "$$src" -o "$$dest" $(BASE_CXXFLAGS) $(ALL_LIB_FLAGS) $(GIT_DEFINES) || exit $$?; \
		echo "$$src -> $$dest"; \
	fi
