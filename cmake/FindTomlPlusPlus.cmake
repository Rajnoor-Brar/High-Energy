# toml++ reads the resolved spec in `Core::Spec` (13 §2). Header-only or shared, whichever is installed.
include(HekitDependency)

find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
  pkg_check_modules(_TOMLPP QUIET tomlplusplus)
endif()

find_path(TomlPlusPlus_INCLUDE_DIR toml++/toml.hpp HINTS ${_TOMLPP_INCLUDE_DIRS}
          PATHS /usr/include /usr/local/include)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(TomlPlusPlus
  REQUIRED_VARS TomlPlusPlus_INCLUDE_DIR
  FAIL_MESSAGE "toml++ not found - hep-run cannot read a resolved spec")

if(TomlPlusPlus_FOUND AND NOT TARGET TomlPlusPlus::TomlPlusPlus)
  add_library(TomlPlusPlus::TomlPlusPlus INTERFACE IMPORTED GLOBAL)
  target_include_directories(TomlPlusPlus::TomlPlusPlus SYSTEM INTERFACE ${TomlPlusPlus_INCLUDE_DIR})
  if(_TOMLPP_LIBRARIES)
    target_link_libraries(TomlPlusPlus::TomlPlusPlus INTERFACE ${_TOMLPP_LIBRARIES})
    target_link_directories(TomlPlusPlus::TomlPlusPlus INTERFACE ${_TOMLPP_LIBRARY_DIRS})
    target_compile_definitions(TomlPlusPlus::TomlPlusPlus INTERFACE TOML_HEADER_ONLY=0)
  endif()
endif()
