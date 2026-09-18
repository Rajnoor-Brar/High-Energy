# C++ tests (09 §3). The unit tests of Core and Status arrive with them in P2-S03; for now this
# registers the one thing that exists: hep-run reports its capabilities and refuses the rest.

add_test(NAME hep_run_capabilities COMMAND hep-run --capabilities)
set_tests_properties(hep_run_capabilities PROPERTIES
  PASS_REGULAR_EXPRESSION "\"spec_schema\": 2" LABELS "cxx")

add_test(NAME hep_run_usage COMMAND hep-run)
set_tests_properties(hep_run_usage PROPERTIES WILL_FAIL TRUE LABELS "cxx")

add_test(NAME hep_run_unknown_option COMMAND hep-run --nonsense)
set_tests_properties(hep_run_unknown_option PROPERTIES WILL_FAIL TRUE LABELS "cxx")
