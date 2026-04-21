SHELL := /bin/sh
CXX ?= g++

BASE_CXXFLAGS := -O2 -march=native -std=c++17 -I./utils -I./modules
TOML_FLAGS   := $(shell pkg-config --cflags --libs tomlplusplus)

ROOT_FLAGS   := $(shell root-config --cflags --ldflags --glibs)
PYTHIA_FLAGS := $(shell pythia8-config --cxxflags --ldflags)

all:
	@echo "Usage: make <program> or make <program>.exe (source must be <program>.cc)"

# Build rule
%.exe: %.cc
	@$(CXX) $< -o $@ $(ROOT_FLAGS) $(PYTHIA_FLAGS) $(TOML_FLAGS) $(BASE_CXXFLAGS)
	@echo "$< --> $@"

# Allow `make myprog` to build `myprog.exe`
%: %.exe
	@true

.PHONY: clean
clean:
	@rm -f *.exe
	@echo "Executables removed"
