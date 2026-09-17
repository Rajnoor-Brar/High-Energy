SHELL := /bin/sh
.DEFAULT_GOAL := all

CXX ?= g++

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

.PHONY: all clean compiledb FORCE

all:
	@echo "make folder/file.exe"
	@echo "make folder/file.so"

FORCE:

%.exe: FORCE
	@src="$(SOURCE_ROOT)/$(basename $@).cc"; \
	[ -f "$$src" ] || src="$(basename $@).cc"; \
	[ -f "$$src" ] || { echo "Missing source: $(SOURCE_ROOT)/$(basename $@).cc or $(basename $@).cc"; exit 2; }; \
	dest="$(OUTPUT_ROOT)/$(dir $@)$(notdir $@)"; \
	mkdir -p "$$(dirname "$$dest")"; \
	if [ ! -e "$$dest" ] || [ "$$src" -nt "$$dest" ] || [ Makefile -nt "$$dest" ]; then \
		$(CXX) "$$src" -o "$$dest" $(BASE_CXXFLAGS) $(ALL_LIB_FLAGS) $(GIT_DEFINES) || exit $$?; \
		echo "$$src -> $$dest"; \
	fi

%.so: FORCE
	@src="$(SOURCE_ROOT)/$(basename $@).cc"; \
	[ -f "$$src" ] || src="$(basename $@).cc"; \
	[ -f "$$src" ] || { echo "Missing source: $(SOURCE_ROOT)/$(basename $@).cc or $(basename $@).cc"; exit 2; }; \
	dest="$(OUTPUT_ROOT)/$(dir $@)Rivet_$(notdir $@)"; \
	mkdir -p "$$(dirname "$$dest")"; \
	if [ ! -e "$$dest" ] || [ "$$src" -nt "$$dest" ] || [ Makefile -nt "$$dest" ]; then \
		rivet-build "$$dest" "$$src" $(BASE_CXXFLAGS) $(GIT_DEFINES) > /dev/null || exit $$?; \
		echo "$$src -> $$dest"; \
	fi; \
	for ext in info plot yoda; do \
		meta="$${src%.cc}.$$ext"; \
		[ -f "$$meta" ] && cp -p "$$meta" "$$(dirname "$$dest")/"; \
	done; true

compiledb:
	@test -n "$(TARGETS)" || { echo "Usage: make compiledb TARGETS='folder/a.exe folder/b.so'"; exit 2; }
	@mkdir -p $(dir $(COMPILE_DB))
	@bear --output $(COMPILE_DB) -- $(MAKE) $(TARGETS)

clean:
	@rm -f $(CLEAN_FILES)
	@rm -rf $(OUTPUT_ROOT)
