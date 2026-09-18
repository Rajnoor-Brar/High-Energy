# C++ tests (09 §3). Each test is a small executable that ctest runs; `check.hh` is the harness.
#
# The spikes in spikes/ are measurements, not tests, and are deliberately not registered.

set(HEKIT_CXX_TESTS core_sha256 core_signals status_roundtrip)
if(TARGET TomlPlusPlus::TomlPlusPlus)
  list(APPEND HEKIT_CXX_TESTS core_spec)        # the spec reader needs toml++
endif()

foreach(name IN LISTS HEKIT_CXX_TESTS)
  add_executable(test_${name} test_${name}.cc)
  target_link_libraries(test_${name} PRIVATE hekit_Status)
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
