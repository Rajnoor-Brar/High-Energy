# Interim Makefile — builds the two things that are still built by hand:
#   make PhotoProduction/generator.exe     # sources/<project>/<name>.cc -> output/<project>/<name>.exe
#   make PhotoProduction/photo_eic.so      # Rivet plugin  -> output/<project>/Rivet_<name>.so (+ .info/.plot)
#
# CMake replaces this in P2-S01, and this file becomes a thin wrapper in P4-S06.
# Everything needs the HEP environment first: `load_hep` (env/hep_env.sh).

SHELL := /bin/sh
.DEFAULT_GOAL := help

CXX ?= g++

SOURCE_ROOT := sources
OUTPUT_ROOT := output

BASE_CXXFLAGS := -O2 -std=c++17

# Recursive (=), not immediate (:=): these shell out, so they must run only when a build needs them.
PYTHIA_FLAGS  = $(shell pythia8-config --cxxflags --ldflags)
HEPMC3_FLAGS  = $(shell HepMC3-config --cflags --libs)
GIT_SHA       = $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
GIT_DIRTY     = $(shell git diff --quiet 2>/dev/null && echo 0 || echo 1)
GIT_DEFINES   = -DGIT_SHA=\"$(GIT_SHA)\" -DGIT_DIRTY=$(GIT_DIRTY)

# Per-target link flags. Add a line per executable; the default covers a Pythia + HepMC3 generator.
# Rivet plugins need none: rivet-build supplies Rivet, YODA and FastJet itself.
LIBS_DEFAULT                          = $(PYTHIA_FLAGS) $(HEPMC3_FLAGS)
LIBS_PhotoProduction/generator.exe    = $(PYTHIA_FLAGS) $(HEPMC3_FLAGS)
TARGET_LIBS                           = $(if $(LIBS_$@),$(LIBS_$@),$(LIBS_DEFAULT))

COMPILE_DB ?= $(OUTPUT_ROOT)/compile_commands.json

.PHONY: help all test clean distclean compiledb FORCE

help:
	@echo "make <project>/<name>.exe    build an executable from $(SOURCE_ROOT)/<project>/<name>.cc"
	@echo "make <project>/<name>.so     build a Rivet plugin (+ copy its .info/.plot)"
	@echo "make test                    where the tests are"
	@echo "make clean                   remove built executables and plugins (keeps output/scratch)"
	@echo "make distclean               remove $(OUTPUT_ROOT) entirely"
	@echo "make compiledb TARGETS='...'  compile_commands.json via bear"

all: help

FORCE:

%.exe: FORCE
	@src="$(SOURCE_ROOT)/$(basename $@).cc"; \
	[ -f "$$src" ] || src="$(basename $@).cc"; \
	[ -f "$$src" ] || { echo "Missing source: $(SOURCE_ROOT)/$(basename $@).cc or $(basename $@).cc"; exit 2; }; \
	dest="$(OUTPUT_ROOT)/$(dir $@)$(notdir $@)"; \
	mkdir -p "$$(dirname "$$dest")"; \
	if [ ! -e "$$dest" ] || [ "$$src" -nt "$$dest" ] || [ Makefile -nt "$$dest" ]; then \
		$(CXX) "$$src" -o "$$dest" $(BASE_CXXFLAGS) $(TARGET_LIBS) $(GIT_DEFINES) || exit $$?; \
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
		if [ -f "$$meta" ]; then \
			cp -p "$$meta" "$$(dirname "$$dest")/" || { echo "Failed to copy $$meta"; exit 1; }; \
		fi; \
	done

test:
	@echo "Python tests:  pytest tests/golden        (legacy golden fixtures)"
	@echo "C++ tests:     none yet - ctest arrives with CMake in P2-S01"
	@echo "The archived C++ tests are in legacy/tests/ and are not built."

# Build products only; output/scratch holds the golden-fixture scratch areas.
clean:
	@find $(OUTPUT_ROOT) -mindepth 2 -maxdepth 2 \( -name '*.exe' -o -name 'Rivet_*.so' \) -print -delete 2>/dev/null || true

distclean:
	@rm -rf $(OUTPUT_ROOT)

compiledb:
	@test -n "$(TARGETS)" || { echo "Usage: make compiledb TARGETS='folder/a.exe folder/b.so'"; exit 2; }
	@mkdir -p $(dir $(COMPILE_DB))
	@bear --output $(COMPILE_DB) -- $(MAKE) $(TARGETS)
