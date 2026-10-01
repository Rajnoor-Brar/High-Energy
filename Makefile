# Makefile — the v2 build (docs/06_Developer_Guide.md §2). `hep build` is `make all`.
#
#   make                        every module program, Rivet plugin and app
#   make <path>/<X>.exe         compile one source; the output lands where the convention says
#   make <path>/<x>.so          a Rivet plugin (…/Rivet/<x>.so, …/Rivet_<x>.so) or a shared library
#   make tests                  build the C++ tests       make test   build and run them, then pytest
#   make clean                  empty build/
#
# Conventions (§5.1):
#   utils/App_<X>.cc            → build/App_<X>.exe
#   utils/Apps/<X>/main.cc      → build/<X>.exe      (the folder's other files are headers it includes)
#   modules/<P>/<X>.cc          → build/<P>/<X>.exe  (-I modules/<P>)
#   modules/<P>/Rivet/<x>.cc    → build/Rivet/Rivet_<x>.so, with <x>.info/.plot/.yoda copied beside it
#   modules/<P>/Rivet_<x>.cc    → the same
#   tests/cxx/<X>.cc            → build/tests/<X>.exe
#   <dir>/<X>.cc                → build/<dir>/<X>.exe or build/<dir>/lib<X>.so, only when named
# A path with a component starting with `_` is parked: never built by `make all`.
#
# Linking (§5.2): a source names its libraries in a `// requires: pythia8 hepmc3 …` line near the
# top (`none` for none; a trailing `(…)` is a note). Without the line it gets every library that
# was found. Including "Module.hh" adds hepmc3 and toml. Flags come from build/flags.mk (§5.3).

SHELL := /bin/bash
.DEFAULT_GOAL := all
.SUFFIXES:
.DELETE_ON_ERROR:

BUILD    := build
CXX      ?= g++
CXXFLAGS ?= -O2
BASE      = -std=c++17 $(CXXFLAGS) -I utils

# ── flags: probed once, rewritten only when what they depend on changes (L22) ──────────────────
FLAGS_MK := $(BUILD)/flags.mk
ifneq ($(wildcard $(FLAGS_MK)),)
  include $(FLAGS_MK)
endif
FLAGS_KEY_NOW := $(shell utils/Env/flags.sh --key)
ifneq ($(FLAGS_KEY),$(FLAGS_KEY_NOW))
  $(shell utils/Env/flags.sh $(FLAGS_MK))
  include $(FLAGS_MK)
endif
KNOWN := pythia8 hepmc3 yoda root fastjet lhapdf rivet geant4 toml zstd zlib onnx delphes

open     := (
req_line  = $(shell sed -n 's#^[[:space:]]*//[[:space:]]*requires:[[:space:]]*##p' $(1) | head -n1 | sed 's#[[:space:]]*$(open).*##')
uses_kit  = $(if $(shell grep -ls 'include[[:space:]]*"Module.hh"' $(1)),hepmc3 toml)
libs_of   = $(sort $(call uses_kit,$(1)) $(filter-out none,$(or $(call req_line,$(1)),$(FOUND))))
lib_flags = $(if $(filter $(2),$(FOUND)),$(FLAGS_$(2)),$(error $(1): requires '$(2)', $(if \
              $(filter $(2),$(KNOWN)),which utils/Env/flags.sh did not find (see $(FLAGS_MK)),\
              which is not a known library (known: $(KNOWN)))))
flags_of  = $(foreach l,$(call libs_of,$(1)),$(call lib_flags,$(1),$(l)))

# ── naming ──────────────────────────────────────────────────────────────────────────────────────
parked   = $(foreach s,$(1),$(if $(findstring /_,/$(s)),,$(s)))
proj_of  = $(word 2,$(subst /, ,$(1)))
is_rivet = $(or $(findstring /Rivet/,$(1)),$(filter Rivet_%,$(notdir $(1))))
ana_of   = $(patsubst Rivet_%,%,$(basename $(notdir $(1))))
out_of   = $(strip \
  $(if $(call is_rivet,$(1)),$(BUILD)/Rivet/Rivet_$(call ana_of,$(1)).so,\
  $(if $(filter utils/App_%.cc,$(1)),$(BUILD)/$(basename $(notdir $(1))).exe,\
  $(if $(filter utils/Apps/%/main.cc,$(1)),$(BUILD)/$(notdir $(patsubst %/,%,$(dir $(1)))).exe,\
  $(if $(filter modules/%,$(1)),$(BUILD)/$(call proj_of,$(1))/$(basename $(notdir $(1))).exe,\
  $(if $(filter tests/cxx/%,$(1)),$(BUILD)/tests/$(basename $(notdir $(1))).exe,\
  $(BUILD)/$(basename $(1)).exe))))))
lib_of   = $(BUILD)/$(patsubst ./%,%,$(dir $(1)))lib$(basename $(notdir $(1))).so
alias_of = $(if $(filter utils/Apps/%/main.cc,$(1)),$(patsubst %/,%,$(dir $(1))).exe,$(basename $(1))$(if $(call is_rivet,$(1)),.so,.exe))
incs_of  = $(if $(filter modules/%,$(1)),-I modules/$(call proj_of,$(1))) $(if $(filter utils/Apps/%,$(1)),-I $(dir $(1)))
side_of  = $(firstword $(wildcard $(dir $(1))$(call ana_of,$(1)).$(2) $(dir $(1))Rivet_$(call ana_of,$(1)).$(2)))
depfile  = $(BUILD)/deps/$(subst /,__,$(1)).d

# ── what exists ─────────────────────────────────────────────────────────────────────────────────
ROOT_CC    := $(call parked,$(wildcard modules/*/*.cc))
RIVET_SRCS := $(call parked,$(wildcard modules/*/Rivet/*.cc)) $(foreach s,$(ROOT_CC),$(if $(filter Rivet_%,$(notdir $(s))),$(s)))
PROG_SRCS  := $(foreach s,$(ROOT_CC),$(if $(filter Rivet_%,$(notdir $(s))),,$(s)))
APP_SRCS   := $(wildcard utils/App_*.cc) $(wildcard utils/Apps/*/main.cc)
TEST_SRCS  := $(wildcard tests/cxx/*.cc)

# Sources named on the command line, including ones outside the conventions (generator_comparison.cc)
goal_src   = $(if $(filter utils/Apps/%.exe,$(1)),$(1:.exe=)/main.cc,$(basename $(1)).cc)
GOALS      := $(filter %.exe %.so,$(MAKECMDGOALS))
$(foreach g,$(GOALS),$(if $(wildcard $(call goal_src,$(g))),,$(error $(g): no source $(call goal_src,$(g)))))
GOAL_SRCS  := $(foreach g,$(GOALS),$(call goal_src,$(g)))
SO_GOALS   := $(foreach g,$(filter %.so,$(GOALS)),$(if $(call is_rivet,$(g)),,$(call goal_src,$(g))))

EXE_SRCS   := $(sort $(PROG_SRCS) $(APP_SRCS) $(TEST_SRCS) $(foreach s,$(GOAL_SRCS),$(if $(call is_rivet,$(s)),,$(if $(filter $(s),$(SO_GOALS)),,$(s)))))
RIVETS     := $(sort $(RIVET_SRCS) $(foreach s,$(GOAL_SRCS),$(if $(call is_rivet,$(s)),$(s))))

# ── rules ───────────────────────────────────────────────────────────────────────────────────────
define exe_rule
$(call out_of,$(1)): $(1)
	@mkdir -p $$(@D) $(BUILD)/deps
	$$(CXX) $$(BASE) $(call incs_of,$(1)) -MMD -MP -MF $(call depfile,$(1)) $(1) -o $$@ $$(call flags_of,$(1))
.PHONY: $(call alias_of,$(1))
$(call alias_of,$(1)): $(call out_of,$(1))
endef

define so_rule
$(call lib_of,$(1)): $(1)
	@mkdir -p $$(@D) $(BUILD)/deps
	$$(CXX) $$(BASE) -fPIC -shared $(call incs_of,$(1)) -MMD -MP -MF $(call depfile,$(1)) $(1) -o $$@ $$(call flags_of,$(1))
.PHONY: $(basename $(1)).so
$(basename $(1)).so: $(call lib_of,$(1))
endef

# A Rivet plugin, and its .info/.plot/.yoda as real targets so an edit re-copies them (00/B44).
# rivet-build gets the shared-header paths (L20) and, when the .info says `Requires: ONNX`, ONNX. It runs a
# make of its own, so its line starts with `+`: that make shares our -j job slots.
define side_rule
$(BUILD)/Rivet/$(call ana_of,$(1)).$(2): $(call side_of,$(1),$(2))
	@mkdir -p $$(@D)
	cp $$< $$@
endef
define rivet_rule
$(call out_of,$(1)): $(1)
	@mkdir -p $$(@D) $(BUILD)/deps
	+rivet-build $$(abspath $$@) $(abspath $(1)) -I$(abspath utils) $(if $(filter modules/%,$(1)),-I$(abspath modules/$(call proj_of,$(1)))) \
	    -DHEKIT_WITH_HEPMC=1 -MMD -MP -MF$(abspath $(call depfile,$(1))) \
	    $(if $(shell grep -ls 'Requires:.*ONNX' $(call side_of,$(1),info) /dev/null),$$(FLAGS_onnx))
	@sed -i '1s|^[^:]*:[[:space:]]*[^[:space:]]*\.cc|$$@:|' $(call depfile,$(1))
$(foreach e,info plot yoda,$(if $(call side_of,$(1),$(e)),$(eval $(call side_rule,$(1),$(e)))))
.PHONY: $(call alias_of,$(1)) rivet_$(call ana_of,$(1))
$(call alias_of,$(1)) rivet_$(call ana_of,$(1)): $(call out_of,$(1)) $(foreach e,info plot yoda,$(if $(call side_of,$(1),$(e)),$(BUILD)/Rivet/$(call ana_of,$(1)).$(e)))
endef

$(foreach s,$(EXE_SRCS),$(eval $(call exe_rule,$(s))))
$(foreach s,$(SO_GOALS),$(eval $(call so_rule,$(s))))
$(foreach s,$(RIVETS),$(eval $(call rivet_rule,$(s))))

ALL := $(foreach s,$(PROG_SRCS) $(APP_SRCS),$(call out_of,$(s))) $(foreach s,$(RIVET_SRCS),rivet_$(call ana_of,$(s)))
TESTS := $(foreach s,$(TEST_SRCS),$(call out_of,$(s)))

# Herwig's repository (utils/Env/herwig): its own install made none, because its defaults need the
# CT14lo/CT14nlo PDF sets (L15). Built here, never in ~/HEP; a failure warns and leaves no file.
HERWIG := $(shell command -v Herwig 2>/dev/null)
ifneq ($(HERWIG),)
HERWIG_HOME := $(patsubst %/bin/Herwig,%,$(HERWIG))
$(BUILD)/Herwig/HerwigDefaults.rpo: $(HERWIG)
	@mkdir -p $(@D)
	@cd $(@D) && if Herwig init -L$(HERWIG_HOME)/lib/Herwig -i$(HERWIG_HOME)/share/Herwig \
	    --repo=$(abspath $@) defaults/HerwigDefaults.in > init.log 2>&1; then echo "── $@"; \
	  else rm -f $(abspath $@); echo "warning: Herwig's repository was not built: $$(tail -1 init.log)"; fi
ALL += $(BUILD)/Herwig/HerwigDefaults.rpo
endif

.PHONY: all tests test test-slow clean configure list
all: $(ALL)
tests: $(TESTS)
test: all tests
	@set -e; for t in $(TESTS); do echo "── $$t"; $$t; done
	python3 -m pytest -q -m "not slow"
test-slow: all
	python3 -m pytest -q -m slow
configure:
	utils/Env/flags.sh $(FLAGS_MK)
list:
	@printf '%s\n' $(ALL) $(TESTS)
clean:
	rm -rf $(BUILD)

-include $(wildcard $(BUILD)/deps/*.d)
