# C++ tests (09 §3). Each test is a small executable that ctest runs; `check.hh` is the harness.
#
# The spikes in spikes/ are measurements, not tests, and are deliberately not registered. They are
# built on demand: `cmake --build build --target store_compression`.

set(HEKIT_CXX_TESTS core_sha256 core_signals status_roundtrip run_rules results_writer)
list(APPEND HEKIT_CXX_TESTS store_queue)          # the replay queue needs only threads
if(HEKIT_HEPMC)
  list(APPEND HEKIT_CXX_TESTS store_writer)       # the event store needs HepMC3
endif()
if(HEKIT_WITH_RIVET)
  list(APPEND HEKIT_CXX_TESTS results_objects)    # a module's YODA objects need YODA
endif()
if(HEKIT_HEPMC AND HEKIT_RIVET)
  list(APPEND HEKIT_CXX_TESTS phys)              # four-vectors from HepMC3, jets from FastJet
endif()
if(TARGET TomlPlusPlus::TomlPlusPlus)
  list(APPEND HEKIT_CXX_TESTS core_spec)        # the spec reader needs toml++
endif()

foreach(name IN LISTS HEKIT_CXX_TESTS)
  add_executable(test_${name} test_${name}.cc)
  target_link_libraries(test_${name} PRIVATE hekit_Status)
  if(name STREQUAL "results_writer" OR name STREQUAL "results_objects")
    target_link_libraries(test_${name} PRIVATE hekit_Results)      # YODA
  elseif(name STREQUAL "store_writer" OR name STREQUAL "store_queue")
    target_link_libraries(test_${name} PRIVATE hekit_Store)        # HepMC3 (+ compression)
  elseif(name STREQUAL "phys")
    # `hekit_Phys` brings HepMC3 and FastJet; Pythia comes through it too, and the PDG row compares
    # the table against Pythia's own `ParticleData`.
    target_link_libraries(test_${name} PRIVATE hekit_Phys)
  endif()
  target_include_directories(test_${name} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
  add_test(NAME ${name} COMMAND test_${name})
  set_tests_properties(${name} PROPERTIES LABELS "cxx")
endforeach()

# hep-run's own behaviour: it reports what it can do, and refuses what it cannot.
add_test(NAME hep_run_capabilities COMMAND hep-run --capabilities)
set_tests_properties(hep_run_capabilities PROPERTIES
  PASS_REGULAR_EXPRESSION "\"spec_schema\": 2" LABELS "cxx")

add_test(NAME hep_run_usage COMMAND hep-run)
set_tests_properties(hep_run_usage PROPERTIES WILL_FAIL TRUE LABELS "cxx")

add_test(NAME hep_run_unknown_option COMMAND hep-run --nonsense)
set_tests_properties(hep_run_unknown_option PROPERTIES WILL_FAIL TRUE LABELS "cxx")


# ── spikes (measurements, built on demand, never run by ctest) ───────────────

if(TARGET hekit_Store AND HEKIT_HEPMC)
  add_executable(store_compression EXCLUDE_FROM_ALL spikes/store_compression.cc)
  target_link_libraries(store_compression PRIVATE hekit_Store Pythia8::Pythia8)
endif()
