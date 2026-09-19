# High-Energy toolkit — the C++ half (09 §1).
#
#   cmake -S . -B build -G Ninja && cmake --build build
#   ctest --test-dir build
#
# Pythia is the one hard requirement. Every other component is AUTO: on when found, off when not, and a
# build with all of them off still produces a working `hep-run` (01 N5). The facade libraries below are
# INTERFACE libraries, one per namespace of 13 §2; they gain headers as the steps land.

cmake_minimum_required(VERSION 3.20)
project(hekit LANGUAGES CXX
        DESCRIPTION "Event generation, analysis and results for the High-Energy toolkit")

list(APPEND CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/cmake)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "" FORCE)
endif()
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

# ── options ──────────────────────────────────────────────────────────────────
# AUTO means "on if the dependency is found". ON demands it, OFF refuses it.
set(_auto_values AUTO ON OFF)
foreach(component RIVET HEPMC ONNX)
  set(HEKIT_WITH_${component} AUTO CACHE STRING "Build the ${component} component (AUTO/ON/OFF)")
  set_property(CACHE HEKIT_WITH_${component} PROPERTY STRINGS ${_auto_values})
endforeach()
# In-process Delphes is deferred (07, 13 §3: its global `class Event` clashes); external Delphes is a
# supervised process and needs no build option.
set(HEKIT_WITH_DELPHES OFF CACHE STRING "Build the in-process Delphes sink (deferred; AUTO/ON/OFF)")
set_property(CACHE HEKIT_WITH_DELPHES PROPERTY STRINGS ${_auto_values})

# hekit_component(<NAME> <package>…) — resolve one AUTO/ON/OFF option into HEKIT_<NAME> (0/1).
function(hekit_component name)
  set(wanted ${HEKIT_WITH_${name}})
  if(wanted STREQUAL "OFF")
    set(HEKIT_${name} 0 PARENT_SCOPE)
    message(STATUS "hekit: ${name} off (asked for)")
    return()
  endif()
  set(found TRUE)
  foreach(package IN LISTS ARGN)
    if(wanted STREQUAL "ON")
      find_package(${package} REQUIRED)
    else()
      find_package(${package} QUIET)
    endif()
    if(NOT ${package}_FOUND)
      set(found FALSE)
    endif()
  endforeach()
  if(found)
    set(HEKIT_${name} 1 PARENT_SCOPE)
    message(STATUS "hekit: ${name} on")
  else()
    set(HEKIT_${name} 0 PARENT_SCOPE)
    message(STATUS "hekit: ${name} off (not found: ${ARGN})")
  endif()
endfunction()

# ── dependencies ─────────────────────────────────────────────────────────────
find_package(Pythia8 REQUIRED)        # the one hard requirement (09 §1)
find_package(YODA REQUIRED)           # Results and Module always book YODA (D14)
find_package(TomlPlusPlus QUIET)      # Core::Spec reads the resolved spec
find_package(Threads REQUIRED)

hekit_component(RIVET Rivet FastJet)
hekit_component(HEPMC HepMC3)
hekit_component(ONNX OnnxRuntime)
hekit_component(DELPHES Delphes)

# HepMC3 compression is header-only plus a library: zlib always, zstd when present (09 §1, D-Q9).
set(HEKIT_STORE_COMPRESSION "")
if(HEKIT_HEPMC)
  find_package(ZLIB QUIET)
  if(ZLIB_FOUND)
    list(APPEND HEKIT_STORE_COMPRESSION gz)
  endif()
  find_library(HEKIT_ZSTD_LIBRARY NAMES zstd)
  find_path(HEKIT_ZSTD_INCLUDE_DIR zstd.h)
  if(HEKIT_ZSTD_LIBRARY AND HEKIT_ZSTD_INCLUDE_DIR)
    list(APPEND HEKIT_STORE_COMPRESSION zst)
  endif()
endif()
# A CMake list is semicolon-separated, which would split a compile definition, so join it once here.
string(JOIN "," HEKIT_COMPRESSION_TEXT ${HEKIT_STORE_COMPRESSION})
if(HEKIT_HEPMC)
  message(STATUS "hekit: HepMC compression: ${HEKIT_COMPRESSION_TEXT}")
endif()

# ── facade libraries (13 §2) ─────────────────────────────────────────────────
# One INTERFACE library per namespace, in dependency order: a lower layer never links a higher one.
# They carry no sources yet; P2-S03 onwards adds headers under utils/<Namespace>/.
set(HEKIT_FACADES Core Status Events Store Results ML Phys Source Module Sink Run)
foreach(facade IN LISTS HEKIT_FACADES)
  add_library(hekit_${facade} INTERFACE)
  target_include_directories(hekit_${facade} INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/utils)
  target_compile_features(hekit_${facade} INTERFACE cxx_std_17)
endforeach()

target_link_libraries(hekit_Core INTERFACE Threads::Threads)
if(TARGET TomlPlusPlus::TomlPlusPlus)
  target_link_libraries(hekit_Core INTERFACE TomlPlusPlus::TomlPlusPlus)
  target_compile_definitions(hekit_Core INTERFACE HEKIT_HAVE_TOMLPP=1)
endif()
target_link_libraries(hekit_Status INTERFACE hekit_Core)
target_link_libraries(hekit_Events INTERFACE hekit_Status Pythia8::Pythia8)
target_link_libraries(hekit_Results INTERFACE hekit_Events YODA::YODA)
target_link_libraries(hekit_Store INTERFACE hekit_Events)
target_link_libraries(hekit_Phys INTERFACE hekit_Events)
target_link_libraries(hekit_ML INTERFACE hekit_Events)
target_link_libraries(hekit_Source INTERFACE hekit_Events Pythia8::Pythia8)
target_link_libraries(hekit_Module INTERFACE hekit_Results)
target_link_libraries(hekit_Sink INTERFACE hekit_Results hekit_Store hekit_Module)
target_link_libraries(hekit_Run INTERFACE hekit_Sink hekit_Source)

if(HEKIT_HEPMC)
  target_link_libraries(hekit_Events INTERFACE HepMC3::HepMC3)
  target_compile_definitions(hekit_Events INTERFACE HEKIT_WITH_HEPMC=1)
  if("gz" IN_LIST HEKIT_STORE_COMPRESSION)
    # exactly the flags verified in P0-S00: header-only compression plus zlib
    target_compile_definitions(hekit_Store INTERFACE HEPMC3_USE_COMPRESSION HEPMC3_Z_SUPPORT=1)
    target_link_libraries(hekit_Store INTERFACE ZLIB::ZLIB)
  endif()
  if("zst" IN_LIST HEKIT_STORE_COMPRESSION)
    target_compile_definitions(hekit_Store INTERFACE HEPMC3_ZSTD_SUPPORT=1)
    target_include_directories(hekit_Store SYSTEM INTERFACE ${HEKIT_ZSTD_INCLUDE_DIR})
    target_link_libraries(hekit_Store INTERFACE ${HEKIT_ZSTD_LIBRARY})
  endif()
endif()
if(HEKIT_RIVET)
  target_link_libraries(hekit_Sink INTERFACE Rivet::Rivet FastJet::FastJet)
  target_compile_definitions(hekit_Sink INTERFACE HEKIT_WITH_RIVET=1)
  target_link_libraries(hekit_Phys INTERFACE FastJet::FastJet)
endif()
if(HEKIT_ONNX)
  target_link_libraries(hekit_ML INTERFACE OnnxRuntime::OnnxRuntime)
  target_compile_definitions(hekit_ML INTERFACE HEKIT_WITH_ONNX=1)
endif()
if(HEKIT_DELPHES)
  target_link_libraries(hekit_Sink INTERFACE Delphes::Delphes)
  target_compile_definitions(hekit_Sink INTERFACE HEKIT_WITH_DELPHES=1)
endif()

# ── hep-run ──────────────────────────────────────────────────────────────────
add_executable(hep-run utils/apps/hep-run.cc)
target_link_libraries(hep-run PRIVATE hekit_Run)
if(NOT TARGET TomlPlusPlus::TomlPlusPlus)
  message(FATAL_ERROR "hep-run needs toml++ to read a resolved spec (install libtomlplusplus-dev)")
endif()
target_compile_definitions(hep-run PRIVATE
  HEKIT_VERSION="0.1.0"
  HEKIT_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
  HEKIT_COMPONENT_RIVET=${HEKIT_RIVET}
  HEKIT_COMPONENT_HEPMC=${HEKIT_HEPMC}
  HEKIT_COMPONENT_ONNX=${HEKIT_ONNX}
  HEKIT_COMPONENT_DELPHES=${HEKIT_DELPHES}
  HEKIT_COMPRESSION="${HEKIT_COMPRESSION_TEXT}")

# ── Rivet analyses, one target per project (09 §1) ───────────────────────────
# Built with `rivet-build`, exactly as the interim Makefile does, because that works and keeps the
# plugin ABI-compatible with the installed Rivet. Metadata is copied beside the library.
find_program(HEKIT_RIVET_BUILD rivet-build)
file(GLOB _analysis_dirs RELATIVE ${CMAKE_CURRENT_SOURCE_DIR}/analyses ${CMAKE_CURRENT_SOURCE_DIR}/analyses/*)
foreach(project IN LISTS _analysis_dirs)
  if(NOT IS_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/analyses/${project})
    continue()
  endif()
  file(GLOB _sources ${CMAKE_CURRENT_SOURCE_DIR}/analyses/${project}/*.cc)
  if(NOT _sources OR NOT HEKIT_RIVET_BUILD OR NOT HEKIT_RIVET)
    continue()
  endif()
  set(_outputs "")
  foreach(source IN LISTS _sources)
    get_filename_component(_name ${source} NAME_WE)
    set(_out ${CMAKE_BINARY_DIR}/analyses/${project}/Rivet_${_name}.so)
    set(_copies "")
    foreach(extension info plot yoda)
      if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/analyses/${project}/${_name}.${extension})
        list(APPEND _copies COMMAND ${CMAKE_COMMAND} -E copy_if_different
             ${CMAKE_CURRENT_SOURCE_DIR}/analyses/${project}/${_name}.${extension}
             ${CMAKE_BINARY_DIR}/analyses/${project}/${_name}.${extension})
      endif()
    endforeach()
    # a plugin that declares `Requires: ONNX` in its .info is built with the ONNX flags (09 §1)
    set(_extra "")
    if(HEKIT_ONNX AND EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/analyses/${project}/${_name}.info)
      file(READ ${CMAKE_CURRENT_SOURCE_DIR}/analyses/${project}/${_name}.info _info)
      if(_info MATCHES "Requires:.*ONNX")
        get_target_property(_onnx_include OnnxRuntime::OnnxRuntime INTERFACE_INCLUDE_DIRECTORIES)
        set(_extra -I${_onnx_include} ${OnnxRuntime_LIBRARY})
      endif()
    endif()
    add_custom_command(
      OUTPUT ${_out}
      COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_BINARY_DIR}/analyses/${project}
      COMMAND ${HEKIT_RIVET_BUILD} ${_out} ${source} ${_extra}
      ${_copies}
      DEPENDS ${source}
      COMMENT "rivet-build ${project}/${_name}"
      VERBATIM)
    list(APPEND _outputs ${_out})
  endforeach()
  add_custom_target(rivet_${project} ALL DEPENDS ${_outputs})
endforeach()

# ── user modules, one MODULE library per source (P8-S01) ─────────────────────
file(GLOB _module_dirs RELATIVE ${CMAKE_CURRENT_SOURCE_DIR}/modules ${CMAKE_CURRENT_SOURCE_DIR}/modules/*)
foreach(project IN LISTS _module_dirs)
  if(NOT IS_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/modules/${project})
    continue()
  endif()
  file(GLOB _sources ${CMAKE_CURRENT_SOURCE_DIR}/modules/${project}/*.cc)
  foreach(source IN LISTS _sources)
    get_filename_component(_name ${source} NAME_WE)
    add_library(hekit_${_name} MODULE ${source})
    target_link_libraries(hekit_${_name} PRIVATE hekit_Module)
    set_target_properties(hekit_${_name} PROPERTIES
      LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/modules/${project})
  endforeach()
endforeach()

# ── tests ────────────────────────────────────────────────────────────────────
include(CTest)
add_subdirectory(tests/cxx)

# The Python suite runs from ctest too, so `ctest` is the one command that checks everything.
find_program(HEKIT_PYTEST pytest)
if(HEKIT_PYTEST)
  add_test(NAME python COMMAND ${HEKIT_PYTEST} -q ${CMAKE_CURRENT_SOURCE_DIR}/tests/python
                                                  ${CMAKE_CURRENT_SOURCE_DIR}/tests/golden)
  set_tests_properties(python PROPERTIES LABELS "python")

  # The equivalence gate runs the real binary against the golden legacy outputs, so it is minutes
  # rather than seconds and carries the "slow" label: `ctest -L slow -R equivalence` (09 §3).
  add_test(NAME equivalence COMMAND ${HEKIT_PYTEST} -q
           ${CMAKE_CURRENT_SOURCE_DIR}/tests/integration/test_hep_run_vs_legacy.py)
  set_tests_properties(equivalence PROPERTIES LABELS "slow" TIMEOUT 3600)

  # `hep run` against the real binary, end to end (P3-S05).
  add_test(NAME e2e COMMAND ${HEKIT_PYTEST} -q
           ${CMAKE_CURRENT_SOURCE_DIR}/tests/integration/test_hep_run_e2e.py)
  set_tests_properties(e2e PROPERTIES LABELS "slow" TIMEOUT 3600)

  # `hep plot` against the intermediates ydmrg and ydplt produced (P4-S02).
  add_test(NAME plot_equivalence COMMAND ${HEKIT_PYTEST} -q
           ${CMAKE_CURRENT_SOURCE_DIR}/tests/integration/test_plot_vs_legacy.py)
  set_tests_properties(plot_equivalence PROPERTIES LABELS "slow" TIMEOUT 3600)

  # Replaying a store through the same sinks as fresh events (P5-S02).
  add_test(NAME store_replay COMMAND ${HEKIT_PYTEST} -q
           ${CMAKE_CURRENT_SOURCE_DIR}/tests/integration/test_store_replay.py)
  set_tests_properties(store_replay PROPERTIES LABELS "slow" TIMEOUT 3600)

  add_test(NAME sharded_rivet COMMAND ${HEKIT_PYTEST} -q
           ${CMAKE_CURRENT_SOURCE_DIR}/tests/integration/test_sharded_rivet.py)
  set_tests_properties(sharded_rivet PROPERTIES LABELS "slow" TIMEOUT 3600)

  add_test(NAME event_groups COMMAND ${HEKIT_PYTEST} -q
           ${CMAKE_CURRENT_SOURCE_DIR}/tests/integration/test_event_groups.py)
  set_tests_properties(event_groups PROPERTIES LABELS "slow" TIMEOUT 3600)

  add_test(NAME bench COMMAND ${HEKIT_PYTEST} -q
           ${CMAKE_CURRENT_SOURCE_DIR}/tests/integration/test_bench.py)
  set_tests_properties(bench PROPERTIES LABELS "slow" TIMEOUT 3600)

  # The analysis plugin's own defects and its re-entrant merge (P4-S05).
  add_test(NAME photo_eic COMMAND ${HEKIT_PYTEST} -q
           ${CMAKE_CURRENT_SOURCE_DIR}/tests/integration/test_photo_eic_plugin.py)
  set_tests_properties(photo_eic PROPERTIES LABELS "slow" TIMEOUT 3600)
endif()

string(JOIN " " _facade_text ${HEKIT_FACADES})
message(STATUS "hekit: facades ${_facade_text}")
message(STATUS "hekit: build type ${CMAKE_BUILD_TYPE}, C++${CMAKE_CXX_STANDARD}")
