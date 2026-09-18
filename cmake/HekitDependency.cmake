# Turning `*-config` output into CMake targets.
#
# Pythia, Rivet, YODA, HepMC3, LHAPDF and FastJet ship `*-config` scripts rather than CMake package
# configs (09 §1), so each Find module here asks the script for its flags and hands them to
# `hekit_target_from_flags`, which splits them into include directories, link directories, libraries,
# definitions and anything else. A dependency that is not installed simply yields no target: a missing
# optional tool must never break the build (01 N5).

include_guard(GLOBAL)

# hekit_config_tool(<result> COMMAND <exe> <args…>)  — run a *-config script, or leave <result> unset.
function(hekit_config_tool result)
  cmake_parse_arguments(ARG "" "" "COMMAND" ${ARGN})
  list(GET ARG_COMMAND 0 executable)
  find_program(${executable}_EXECUTABLE NAMES ${executable})
  if(NOT ${executable}_EXECUTABLE)
    set(${result} "" PARENT_SCOPE)
    return()
  endif()
  list(REMOVE_AT ARG_COMMAND 0)
  execute_process(COMMAND ${${executable}_EXECUTABLE} ${ARG_COMMAND}
                  OUTPUT_VARIABLE output RESULT_VARIABLE status
                  OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
  if(NOT status EQUAL 0)
    set(${result} "" PARENT_SCOPE)
  else()
    set(${result} "${output}" PARENT_SCOPE)
  endif()
endfunction()

# hekit_target_from_flags(<target> COMPILE "<flags>" LINK "<flags>")
#
# Creates an imported interface target. Compiler flags that are neither -I nor -D are dropped on
# purpose: `-O2 -std=c++17` from a config script must not override the build type or the standard the
# project chose.
function(hekit_target_from_flags target)
  cmake_parse_arguments(ARG "" "COMPILE;LINK" "" ${ARGN})
  if(TARGET ${target})
    return()
  endif()
  add_library(${target} INTERFACE IMPORTED GLOBAL)

  separate_arguments(compile_flags UNIX_COMMAND "${ARG_COMPILE}")
  foreach(flag IN LISTS compile_flags)
    if(flag MATCHES "^-I(.+)$")
      target_include_directories(${target} SYSTEM INTERFACE ${CMAKE_MATCH_1})
    elseif(flag MATCHES "^-D(.+)$")
      target_compile_definitions(${target} INTERFACE ${CMAKE_MATCH_1})
    endif()
  endforeach()

  separate_arguments(link_flags UNIX_COMMAND "${ARG_LINK}")
  foreach(flag IN LISTS link_flags)
    if(flag MATCHES "^-L(.+)$")
      target_link_directories(${target} INTERFACE ${CMAKE_MATCH_1})
      # keep the runtime path, so a built binary finds the libraries without LD_LIBRARY_PATH
      target_link_options(${target} INTERFACE "LINKER:-rpath,${CMAKE_MATCH_1}")
    elseif(flag MATCHES "^-l(.+)$")
      target_link_libraries(${target} INTERFACE ${CMAKE_MATCH_1})
    elseif(flag MATCHES "^-Wl,")
      target_link_options(${target} INTERFACE ${flag})
    endif()
  endforeach()
endfunction()
